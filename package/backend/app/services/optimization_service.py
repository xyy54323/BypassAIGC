import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import ChangeLog, CustomPrompt, OptimizationSegment, OptimizationSession, SessionHistory
from app.services.ai_service import (
    AIService,
    count_chinese_characters,
    count_text_length,
    get_compression_prompt,
    get_default_enhance_prompt,
    get_default_polish_prompt,
    normalize_forbidden_connectors,
    split_text_into_segments,
)
from app.services.concurrency import concurrency_manager
from app.services.stream_manager import stream_manager

MAX_ERROR_MESSAGE_LENGTH = 500


class OptimizationService:
    """优化处理服务"""

    def __init__(self, db: Session, session_obj: OptimizationSession):
        self.db = db
        self.session_obj = session_obj
        self.polish_service: Optional[AIService] = None
        self.enhance_service: Optional[AIService] = None
        self.compression_service: Optional[AIService] = None
        self.db_lock = asyncio.Lock()
        self._stage_total_segments = 0
        self._stage_completed_count = 0

    def _init_ai_services(self):
        """初始化 AI 服务"""
        try:
            self.polish_service = AIService(
                model=self.session_obj.polish_model or settings.POLISH_MODEL,
                api_key=self.session_obj.polish_api_key or settings.POLISH_API_KEY,
                base_url=self.session_obj.polish_base_url or settings.POLISH_BASE_URL,
            )
            self.enhance_service = AIService(
                model=self.session_obj.enhance_model or settings.ENHANCE_MODEL,
                api_key=self.session_obj.enhance_api_key or settings.ENHANCE_API_KEY,
                base_url=self.session_obj.enhance_base_url or settings.ENHANCE_BASE_URL,
            )
            self.compression_service = AIService(
                model=settings.COMPRESSION_MODEL,
                api_key=settings.COMPRESSION_API_KEY or settings.OPENAI_API_KEY,
                base_url=settings.COMPRESSION_BASE_URL or settings.OPENAI_BASE_URL,
            )
            print(f"[INFO] 所有 AI 服务初始化成功，会话: {self.session_obj.session_id}", flush=True)
        except Exception as exc:
            error_msg = f"AI 服务初始化失败: {str(exc)}"
            print(f"[ERROR] {error_msg}", flush=True)
            raise Exception(error_msg)

    async def start_optimization(self):
        """开始优化流程"""
        try:
            self._init_ai_services()

            async with self.db_lock:
                self.session_obj.error_message = None
                self.session_obj.failed_segment_index = None
                self.db.commit()

            acquired = await concurrency_manager.acquire(self.session_obj.session_id)
            if not acquired:
                async with self.db_lock:
                    self.session_obj.status = "queued"
                    self.db.commit()
                acquired = await concurrency_manager.acquire(self.session_obj.session_id)
                if not acquired:
                    raise Exception("等待并发权限超时")

            async with self.db_lock:
                self.session_obj.status = "processing"
                self.db.commit()

            await self._ensure_session_active()
            await self._ensure_segments_exist()

            processing_mode = self.session_obj.processing_mode or 'paper_polish_enhance'
            if processing_mode == 'paper_polish':
                await self._process_stage("polish")
            elif processing_mode == 'paper_enhance':
                await self._process_stage("enhance")
            elif processing_mode == 'paper_polish_enhance':
                await self._process_stage("polish")
                await self._process_stage("enhance")
            else:
                raise ValueError(f"不支持的处理模式: {processing_mode}")

            async with self.db_lock:
                self.session_obj.status = "completed"
                self.session_obj.completed_at = datetime.utcnow()
                self.session_obj.progress = 100.0
                self.session_obj.failed_segment_index = None
                self.session_obj.current_position = max(self.session_obj.total_segments - 1, 0) if self.session_obj.total_segments else 0
                self.db.commit()

        except Exception as exc:
            async with self.db_lock:
                self.db.refresh(self.session_obj)
                if self.session_obj.status == "stopped" or str(exc) == "会话已被用户停止":
                    self.session_obj.status = "stopped"
                    self.session_obj.error_message = self.session_obj.error_message or "用户手动停止"
                    self.db.commit()
                    return

                self.session_obj.status = "failed"
                self.session_obj.error_message = self._truncate_error_message(str(exc))
                self.db.commit()
            raise
        finally:
            await concurrency_manager.release(self.session_obj.session_id)
            self._cleanup_ai_services()

    def _cleanup_ai_services(self):
        self.polish_service = None
        self.enhance_service = None
        self.compression_service = None

    async def _ensure_segments_exist(self):
        async with self.db_lock:
            segments = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.session_id == self.session_obj.id
            ).order_by(OptimizationSegment.segment_index).all()

            if not segments:
                raw_segments = split_text_into_segments(self.session_obj.original_text or "")
                if not raw_segments:
                    raise Exception("未识别到可处理的段落，请检查输入内容")

                self.session_obj.total_segments = len(raw_segments)
                self.db.commit()

                for idx, segment_text in enumerate(raw_segments):
                    self.db.add(
                        OptimizationSegment(
                            session_id=self.session_obj.id,
                            segment_index=idx,
                            stage=self.session_obj.current_stage or "polish",
                            original_text=segment_text,
                            status="pending",
                        )
                    )
                self.db.commit()
            else:
                self.session_obj.total_segments = len(segments)
                self.db.commit()

    async def _ensure_session_active(self):
        async with self.db_lock:
            self.db.refresh(self.session_obj)
            if self.session_obj.status == "stopped":
                raise Exception("会话已被用户停止")

    async def _load_segment_snapshots(self) -> List[Dict[str, object]]:
        async with self.db_lock:
            segments = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.session_id == self.session_obj.id
            ).order_by(OptimizationSegment.segment_index).all()
            self.session_obj.total_segments = len(segments)
            self.db.commit()

            return [
                {
                    "id": segment.id,
                    "segment_index": segment.segment_index,
                    "original_text": segment.original_text,
                    "polished_text": segment.polished_text,
                    "enhanced_text": segment.enhanced_text,
                    "status": segment.status,
                    "is_title": bool(segment.is_title),
                    "source_doc_paragraph_index": segment.source_doc_paragraph_index,
                }
                for segment in segments
            ]

    async def _process_stage(self, stage: str):
        print(f"\n[STAGE START] Stage: {stage}, Session: {self.session_obj.session_id}", flush=True)

        async with self.db_lock:
            self.session_obj.current_stage = stage
            self.db.commit()

        prompt = self._get_prompt(stage)
        ai_service = self.polish_service if stage == "polish" else self.enhance_service
        snapshots = await self._load_segment_snapshots()
        total_segments = len(snapshots)
        if total_segments == 0:
            return

        pending_snapshots = await self._prepare_stage_snapshots(stage, snapshots)
        completed_count = self._count_stage_completed(snapshots, stage)
        self._stage_total_segments = total_segments
        self._stage_completed_count = completed_count
        await self._update_stage_progress(stage)

        if not pending_snapshots:
            async with self.db_lock:
                self.session_obj.failed_segment_index = None
                self.db.commit()
            return

        parallel_limit = max(int(getattr(settings, "MAX_PARALLEL_SEGMENTS_PER_SESSION", 1) or 1), 1)
        parallel_count = min(len(pending_snapshots), parallel_limit)
        chunks = self._partition_segments(pending_snapshots, parallel_count)

        results = await asyncio.gather(
            *[
                self._process_chunk(stage, prompt, ai_service, chunk, snapshots)
                for chunk in chunks
            ],
            return_exceptions=True,
        )

        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise errors[0]

        async with self.db_lock:
            self.session_obj.failed_segment_index = None
            self.db.commit()

    async def _prepare_stage_snapshots(self, stage: str, snapshots: List[Dict[str, object]]) -> List[Dict[str, object]]:
        pending_snapshots: List[Dict[str, object]] = []
        skip_threshold = max(settings.SEGMENT_SKIP_THRESHOLD, 0)

        for snapshot in snapshots:
            await self._ensure_session_active()

            if self._is_stage_completed(snapshot, stage):
                continue

            if snapshot.get("is_title"):
                await self._mark_segment_passthrough(snapshot, stage, mark_title=True)
                continue

            should_auto_skip = self._should_auto_skip(snapshot, skip_threshold)
            if should_auto_skip:
                await self._mark_segment_passthrough(snapshot, stage, mark_title=True)
                continue

            pending_snapshots.append(snapshot)

        return pending_snapshots

    def _should_auto_skip(self, snapshot: Dict[str, object], skip_threshold: int) -> bool:
        if snapshot.get("source_doc_paragraph_index") is not None:
            return False
        if skip_threshold <= 0:
            return False
        return count_text_length(str(snapshot.get("original_text") or "")) < skip_threshold

    def _is_stage_completed(self, snapshot: Dict[str, object], stage: str) -> bool:
        if stage == "polish":
            return snapshot.get("polished_text") is not None
        return snapshot.get("enhanced_text") is not None

    async def _mark_segment_passthrough(self, snapshot: Dict[str, object], stage: str, mark_title: bool):
        async with self.db_lock:
            segment = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.id == snapshot["id"]
            ).first()
            if not segment:
                raise Exception("段落不存在，无法更新处理状态")

            if mark_title:
                segment.is_title = True
                snapshot["is_title"] = True

            segment.stage = stage
            segment.status = "completed"
            segment.completed_at = datetime.utcnow()

            original_text = segment.original_text or ""
            if stage == "polish":
                segment.polished_text = original_text
                if segment.enhanced_text is None:
                    segment.enhanced_text = original_text
                snapshot["polished_text"] = original_text
                snapshot["enhanced_text"] = segment.enhanced_text
            else:
                if segment.polished_text is None:
                    segment.polished_text = original_text
                segment.enhanced_text = segment.polished_text or original_text
                snapshot["polished_text"] = segment.polished_text
                snapshot["enhanced_text"] = segment.enhanced_text

            snapshot["status"] = "completed"
            self.db.commit()

    async def _set_segment_processing(self, snapshot: Dict[str, object], stage: str):
        async with self.db_lock:
            segment = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.id == snapshot["id"]
            ).first()
            if not segment:
                raise Exception("段落不存在，无法开始处理")

            segment.stage = stage
            segment.status = "processing"
            self.db.commit()
            snapshot["status"] = "processing"

    async def _complete_segment(self, snapshot: Dict[str, object], stage: str, output_text: str):
        async with self.db_lock:
            segment = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.id == snapshot["id"]
            ).first()
            if not segment:
                raise Exception("段落不存在，无法保存处理结果")

            segment.stage = stage
            segment.status = "completed"
            segment.completed_at = datetime.utcnow()
            if stage == "polish":
                segment.polished_text = output_text
                snapshot["polished_text"] = output_text
            else:
                segment.enhanced_text = output_text
                snapshot["enhanced_text"] = output_text

            snapshot["status"] = "completed"
            self.db.commit()

    async def _process_chunk(
        self,
        stage: str,
        prompt: str,
        ai_service: AIService,
        chunk: List[Dict[str, object]],
        all_snapshots: List[Dict[str, object]],
    ):
        history, total_chars = self._build_chunk_history(all_snapshots, stage, int(chunk[0]["segment_index"]))
        request_interval = max(settings.API_REQUEST_INTERVAL, 0)

        for index_in_chunk, snapshot in enumerate(chunk):
            await self._ensure_session_active()
            segment_index = int(snapshot["segment_index"])
            input_text = self._get_input_text_for_stage(snapshot, stage)

            try:
                await self._set_segment_processing(snapshot, stage)
                output_text = await self._run_with_retry(
                    segment_index,
                    stage,
                    lambda snapshot=snapshot, history=list(history), input_text=input_text: self._execute_stage_call(
                        ai_service,
                        stage,
                        input_text,
                        prompt,
                        history,
                        int(snapshot["segment_index"]),
                    ),
                )

                await self._complete_segment(snapshot, stage, output_text)
                await self._record_change(segment_index, input_text, output_text, stage)
                await self._advance_stage_progress(stage)

                history.append({"role": "assistant", "content": output_text})
                total_chars += count_chinese_characters(output_text)

                if total_chars > settings.HISTORY_COMPRESSION_THRESHOLD:
                    print(f"\n[HISTORY COMPRESS] Triggering compression, Stage: {stage}", flush=True)
                    compressed_history = await self._compress_history(history, stage)
                    history = compressed_history
                    total_chars = sum(count_chinese_characters(msg.get("content", "")) for msg in history)
                    await stream_manager.broadcast(self.session_obj.session_id, {
                        "type": "history_compressed",
                        "stage": stage,
                        "message": f"历史会话已压缩（{stage} 阶段），节省上下文空间",
                        "new_char_count": total_chars,
                    })
                    await self._save_history(history, stage, total_chars)

                if request_interval > 0 and index_in_chunk < len(chunk) - 1:
                    print(f"[RATE LIMIT] 等待 {request_interval}s 后处理下一段落...", flush=True)
                    await asyncio.sleep(request_interval)

            except Exception as exc:
                await self._mark_stage_failure(segment_index, exc)
                raise

    async def _execute_stage_call(
        self,
        ai_service: AIService,
        stage: str,
        input_text: str,
        prompt: str,
        history: List[Dict[str, str]],
        segment_index: int,
    ) -> str:
        use_stream = settings.USE_STREAMING
        if stage == "polish":
            response = await ai_service.polish_text(input_text, prompt, history, stream=use_stream)
        else:
            response = await ai_service.enhance_text(input_text, prompt, history, stream=use_stream)

        if not use_stream:
            return response

        full_text = ""
        async for chunk in response:
            if not chunk:
                continue
            full_text += chunk
            await stream_manager.broadcast(self.session_obj.session_id, {
                "type": "content",
                "segment_index": segment_index,
                "stage": stage,
                "content": chunk,
                "full_text": full_text,
            })
        return normalize_forbidden_connectors(full_text)

    def _get_input_text_for_stage(self, snapshot: Dict[str, object], stage: str) -> str:
        if stage == "enhance":
            return str(snapshot.get("polished_text") or snapshot.get("original_text") or "")
        return str(snapshot.get("original_text") or "")

    def _build_chunk_history(
        self,
        snapshots: List[Dict[str, object]],
        stage: str,
        before_index: int,
    ) -> Tuple[List[Dict[str, str]], int]:
        history: List[Dict[str, str]] = []
        total_chars = 0

        for snapshot in snapshots:
            segment_index = int(snapshot["segment_index"])
            if segment_index >= before_index:
                break
            if snapshot.get("is_title"):
                continue

            stage_text = snapshot.get("polished_text") if stage == "polish" else snapshot.get("enhanced_text")
            if stage_text is None:
                continue

            content = str(stage_text)
            history.append({"role": "assistant", "content": content})
            total_chars += count_chinese_characters(content)

        return history, total_chars

    def _partition_segments(self, snapshots: List[Dict[str, object]], chunk_count: int) -> List[List[Dict[str, object]]]:
        if chunk_count <= 1 or len(snapshots) <= 1:
            return [snapshots]

        chunks: List[List[Dict[str, object]]] = []
        base_size = len(snapshots) // chunk_count
        remainder = len(snapshots) % chunk_count
        start = 0

        for chunk_index in range(chunk_count):
            size = base_size + (1 if chunk_index < remainder else 0)
            if size <= 0:
                continue
            chunk = snapshots[start:start + size]
            if chunk:
                chunks.append(chunk)
            start += size

        return chunks or [snapshots]

    async def _update_stage_progress(self, stage: str):
        async with self.db_lock:
            total_segments = max(self._stage_total_segments, 1)
            completed_count = min(self._stage_completed_count, total_segments)
            self.session_obj.current_position = max(completed_count - 1, 0) if completed_count > 0 else 0
            self.session_obj.progress = self._calculate_progress(stage, completed_count, total_segments)
            self.db.commit()

    async def _advance_stage_progress(self, stage: str):
        async with self.db_lock:
            self._stage_completed_count += 1
            total_segments = max(self._stage_total_segments, 1)
            completed_count = min(self._stage_completed_count, total_segments)
            self.session_obj.current_position = max(completed_count - 1, 0) if completed_count > 0 else 0
            self.session_obj.progress = self._calculate_progress(stage, completed_count, total_segments)
            self.db.commit()

    def _calculate_progress(self, stage: str, completed_count: int, total_segments: int) -> float:
        ratio = completed_count / max(total_segments, 1)
        processing_mode = self.session_obj.processing_mode or 'paper_polish_enhance'
        if processing_mode == 'paper_polish_enhance':
            if stage == "polish":
                return min(ratio * 50, 50.0)
            return min(50 + ratio * 50, 100.0)
        return min(ratio * 100, 100.0)

    def _count_stage_completed(self, snapshots: List[Dict[str, object]], stage: str) -> int:
        return sum(1 for snapshot in snapshots if self._is_stage_completed(snapshot, stage))

    async def _mark_stage_failure(self, segment_index: int, exc: Exception):
        async with self.db_lock:
            segment = self.db.query(OptimizationSegment).filter(
                OptimizationSegment.session_id == self.session_obj.id,
                OptimizationSegment.segment_index == segment_index,
            ).first()
            if segment:
                segment.status = "failed"

            if self.session_obj.failed_segment_index is None:
                self.session_obj.failed_segment_index = segment_index
            else:
                self.session_obj.failed_segment_index = min(self.session_obj.failed_segment_index, segment_index)

            self.session_obj.error_message = self._truncate_error_message(str(exc))
            self.db.commit()

    async def _run_with_retry(self, segment_index: int, stage: str, task):
        try:
            return await task()
        except Exception as exc:
            raise Exception(f"段落 {segment_index + 1} 在 {stage} 阶段失败: {str(exc)}")

    def _get_prompt(self, stage: str) -> str:
        db_stage = "polish" if stage == "polish" else "enhance"
        uid = self.session_obj.user_id
        if uid is not None:
            row = (
                self.db.query(CustomPrompt)
                .filter(
                    CustomPrompt.user_id == uid,
                    CustomPrompt.stage == db_stage,
                    CustomPrompt.is_active.is_(True),
                    CustomPrompt.is_default.is_(True),
                )
                .first()
            )
            if row and (row.content or "").strip():
                print(
                    f"[INFO] 使用用户默认提示词 stage={db_stage} prompt_id={row.id} name={row.name!r}",
                    flush=True,
                )
                return row.content.strip()

        if stage == "polish":
            return get_default_polish_prompt()
        return get_default_enhance_prompt()

    async def _compress_history(self, history: List[Dict[str, str]], stage: str) -> List[Dict[str, str]]:
        try:
            if len(history) == 1 and history[0].get("role") == "system":
                return history

            recent_messages = history[-3:] if len(history) > 3 else history
            compression_prompt = """你是一个专业的学术文本摘要助手。请压缩以下历史处理内容，提取关键信息：

1. 保留论文的主要术语、核心概念和关键数据
2. 总结已处理段落的主题和要点
3. 提取处理风格和改进方向的关键特征
4. 删除重复内容和冗余表述

要求：
- 压缩后内容不超过原内容的30%
- 保持学术性和专业性
- 只输出压缩后的摘要文本，不要添加任何解释和注释

历史处理内容："""

            compressed_summary = await self.compression_service.compress_history(
                recent_messages,
                compression_prompt,
            )
            return [{"role": "system", "content": f"之前处理的段落摘要：\n{compressed_summary}"}]
        except Exception as exc:
            print(f"[WARNING] 历史压缩失败: {str(exc)}, 将使用最近的消息代替", flush=True)
            return history[-2:] if len(history) > 2 else history

    async def _save_history(self, history: List[Dict[str, str]], stage: str, char_count: int):
        is_compressed = len(history) == 1 and history[0].get("role") == "system"
        if not is_compressed:
            return

        async with self.db_lock:
            existing = self.db.query(SessionHistory).filter(
                SessionHistory.session_id == self.session_obj.id,
                SessionHistory.stage == stage,
                SessionHistory.is_compressed.is_(True),
            ).first()

            if existing:
                existing.history_data = json.dumps(history, ensure_ascii=False)
                existing.character_count = char_count
                existing.created_at = datetime.utcnow()
            else:
                self.db.add(
                    SessionHistory(
                        session_id=self.session_obj.id,
                        stage=stage,
                        history_data=json.dumps(history, ensure_ascii=False),
                        is_compressed=True,
                        character_count=char_count,
                    )
                )
            self.db.commit()

    async def _record_change(self, segment_index: int, before: str, after: str, stage: str):
        changes = {
            "before_length": len(before),
            "after_length": len(after),
            "changed": before != after,
        }
        serialized_detail = json.dumps(changes, ensure_ascii=False)

        async with self.db_lock:
            existing_log = self.db.query(ChangeLog).filter(
                ChangeLog.session_id == self.session_obj.id,
                ChangeLog.segment_index == segment_index,
                ChangeLog.stage == stage,
            ).order_by(ChangeLog.created_at.desc()).first()

            if existing_log:
                existing_log.before_text = before
                existing_log.after_text = after
                existing_log.changes_detail = serialized_detail
            else:
                self.db.add(
                    ChangeLog(
                        session_id=self.session_obj.id,
                        segment_index=segment_index,
                        stage=stage,
                        before_text=before,
                        after_text=after,
                        changes_detail=serialized_detail,
                    )
                )
            self.db.commit()

    def _truncate_error_message(self, error_msg: str) -> str:
        if len(error_msg) <= MAX_ERROR_MESSAGE_LENGTH:
            return error_msg
        return error_msg[:MAX_ERROR_MESSAGE_LENGTH - 50] + "... [错误信息已截断]"
