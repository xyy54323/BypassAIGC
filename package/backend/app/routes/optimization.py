import io
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session, defer
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.models import ChangeLog, OptimizationSegment, OptimizationSession, User
from app.schemas import (
    AigcMatchedDocxExtractResponse,
    AigcReportExtractResponse,
    AigcReportSegmentResponse,
    ChangeLogResponse,
    DocxBodyExtractResponse,
    ExportConfirmation,
    ExtractedBodyParagraphResponse,
    MarkExtractedWordRequest,
    OptimizationCreate,
    ProgressUpdate,
    QueueStatusResponse,
    SessionDetailResponse,
    SessionResponse,
)
from app.services.ai_service import split_text_into_segments
from app.services.concurrency import concurrency_manager
from app.services.docx_body_extractor import (
    build_marked_word_from_token,
    build_marked_word_from_word,
    build_result_word_from_source,
    build_session_paragraphs_from_text,
    extract_aigc_matched_body_from_word,
    extract_body_from_word,
    is_structured_heading_text,
    load_stored_word_source,
)
from app.services.optimization_service import OptimizationService
from app.services.paperpass_report_parser import parse_aigc_detection_report
from app.services.stream_manager import stream_manager
from app.services.user_access import check_usage_limit, get_current_user, increment_usage
from app.utils.auth import generate_session_id

router = APIRouter(prefix="/optimization", tags=["optimization"])


TXT_MEDIA_TYPE = "text/plain; charset=utf-8"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def run_optimization(session_id: int):
    """后台运行优化任务"""
    db = SessionLocal()
    try:
        session_obj = db.query(OptimizationSession).filter(
            OptimizationSession.id == session_id
        ).first()

        if not session_obj:
            return

        service = OptimizationService(db, session_obj)
        await service.start_optimization()
    finally:
        db.close()


def _build_download_response(content: bytes, media_type: str, filename: str, ascii_fallback: str) -> StreamingResponse:
    encoded_filename = quote(filename, safe="")
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}",
        },
    )


def _build_final_text(segments: List[OptimizationSegment]) -> str:
    return "\n\n".join(
        seg.enhanced_text or seg.polished_text or seg.original_text
        for seg in segments
    )


def _build_aigc_report_response(result) -> AigcReportExtractResponse:
    return AigcReportExtractResponse(
        source_filename=result.source_filename,
        report_type=result.report_type,
        report_id=result.report_id,
        title=result.title,
        author=result.author,
        submitted_at=result.submitted_at,
        overall_suspicion=result.overall_suspicion,
        weighted_suspicion=result.weighted_suspicion,
        high_ratio=result.high_ratio,
        medium_ratio=result.medium_ratio,
        low_ratio=result.low_ratio,
        undetected_ratio=result.undetected_ratio,
        word_count=result.word_count,
        paragraph_count=result.paragraph_count,
        sentence_count=result.sentence_count,
        fragment_count=result.fragment_count,
        extracted_segment_count=result.extracted_segment_count,
        segments=[
            AigcReportSegmentResponse(
                page=item.page,
                ai_percent=item.ai_percent,
                risk_level=item.risk_level,
                risk_label=item.risk_label,
                text=item.text,
            )
            for item in result.segments
        ],
    )


@router.post("/start", response_model=SessionResponse)
async def start_optimization(
    data: OptimizationCreate,
    background_tasks: BackgroundTasks,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """开始优化任务"""
    user = get_current_user(card_key, db)
    check_usage_limit(user)

    valid_modes = ['paper_polish', 'paper_enhance', 'paper_polish_enhance']
    if data.processing_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"无效的处理模式。支持的模式: {', '.join(valid_modes)}"
        )

    if data.processing_mode == 'paper_enhance':
        initial_stage = 'enhance'
    else:
        initial_stage = 'polish'

    stored_source = None
    prepared_segments = []

    if data.extraction_token:
        try:
            stored_source = load_stored_word_source(data.extraction_token)
            prepared_segments = [
                {
                    "text": item.text,
                    "is_title": is_structured_heading_text(item.text),
                    "source_doc_paragraph_index": item.source_index,
                }
                for item in build_session_paragraphs_from_text(data.extraction_token, data.original_text)
            ]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        prepared_segments = [
            {
                "text": segment_text,
                "is_title": is_structured_heading_text(segment_text),
                "source_doc_paragraph_index": None,
            }
            for segment_text in split_text_into_segments(data.original_text)
        ]

    if not prepared_segments:
        raise HTTPException(status_code=400, detail="未识别到可处理的段落，请检查输入内容")

    session_id = generate_session_id()
    session = OptimizationSession(
        user_id=user.id,
        session_id=session_id,
        original_text=data.original_text,
        processing_mode=data.processing_mode,
        current_stage=initial_stage,
        status="queued",
        progress=0.0,
        total_segments=len(prepared_segments),
        source_doc_token=stored_source.token if stored_source else None,
        source_doc_filename=stored_source.source_filename if stored_source else None,
        polish_model=data.polish_config.model if data.polish_config else None,
        polish_api_key=data.polish_config.api_key if data.polish_config else None,
        polish_base_url=data.polish_config.base_url if data.polish_config else None,
        enhance_model=data.enhance_config.model if data.enhance_config else None,
        enhance_api_key=data.enhance_config.api_key if data.enhance_config else None,
        enhance_base_url=data.enhance_config.base_url if data.enhance_config else None,
    )

    db.add(session)
    db.flush()

    for idx, item in enumerate(prepared_segments):
        db.add(
            OptimizationSegment(
                session_id=session.id,
                segment_index=idx,
                stage=initial_stage,
                original_text=item["text"],
                status="pending",
                is_title=item["is_title"],
                source_doc_paragraph_index=item["source_doc_paragraph_index"],
            )
        )

    increment_usage(user, db)
    db.commit()
    db.refresh(session)

    background_tasks.add_task(run_optimization, session.id)

    return session


@router.post("/extract-docx-body", response_model=DocxBodyExtractResponse)
async def extract_docx_body(
    file: UploadFile = File(...),
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """上传 DOCX 并提取摘要正文和正文段落。"""
    get_current_user(card_key, db)

    filename = file.filename or "uploaded.docx"
    suffix = Path(filename).suffix.lower()
    if suffix != ".docx":
        raise HTTPException(status_code=400, detail="仅支持上传 .docx 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    max_size_mb = settings.MAX_UPLOAD_FILE_SIZE_MB
    if max_size_mb > 0 and len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {max_size_mb}MB")

    try:
        result = extract_body_from_word(filename, content)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"正文提取失败: {str(exc)}") from exc

    paragraphs = [
        ExtractedBodyParagraphResponse(
            source_index=item.source_index,
            paragraph_type=item.paragraph_type,
            text=item.text,
        )
        for item in result.paragraphs
    ]

    heading_count = sum(1 for item in result.paragraphs if item.paragraph_type == "heading")
    body_count = len(result.paragraphs) - heading_count

    return DocxBodyExtractResponse(
        source_filename=result.source_filename,
        output_filename=result.output_filename,
        marked_output_filename=result.marked_output_filename,
        extraction_token=result.extraction_token,
        extracted_text=result.extracted_text,
        start_heading=result.start_heading,
        paragraph_count=len(result.paragraphs),
        heading_count=heading_count,
        body_count=body_count,
        paragraphs=paragraphs,
    )


@router.post("/mark-docx-body")
async def mark_docx_body(
    file: UploadFile = File(...),
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """上传 DOCX 并返回正文提取标记版 DOCX。"""
    get_current_user(card_key, db)

    filename = file.filename or "uploaded.docx"
    suffix = Path(filename).suffix.lower()
    if suffix != ".docx":
        raise HTTPException(status_code=400, detail="仅支持上传 .docx 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    max_size_mb = settings.MAX_UPLOAD_FILE_SIZE_MB
    if max_size_mb > 0 and len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {max_size_mb}MB")

    try:
        result = build_marked_word_from_word(filename, content)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"标记 Word 生成失败: {str(exc)}") from exc

    return _build_download_response(
        result.content,
        DOCX_MEDIA_TYPE,
        result.output_filename,
        "marked-body.docx",
    )


@router.post("/mark-extracted-word")
async def mark_extracted_word(
    data: MarkExtractedWordRequest,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """根据提取缓存返回标记版 DOCX。"""
    get_current_user(card_key, db)

    try:
        result = build_marked_word_from_token(data.extraction_token)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"标记 Word 生成失败: {str(exc)}") from exc

    return _build_download_response(
        result.content,
        DOCX_MEDIA_TYPE,
        result.output_filename,
        "marked-extracted.docx",
    )


@router.post("/extract-aigc-report", response_model=AigcReportExtractResponse)
async def extract_aigc_report(
    file: UploadFile = File(...),
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """上传 PaperPass、SpeedAI 或维普 AIGC 检测报告 PDF 并提取总体指标和疑似片段。"""
    get_current_user(card_key, db)

    filename = file.filename or "aigc-report.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="仅支持上传 .pdf 检测报告")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    max_size_mb = settings.MAX_UPLOAD_FILE_SIZE_MB
    if max_size_mb > 0 and len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {max_size_mb}MB")

    try:
        result = parse_aigc_detection_report(filename, content)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检测报告解析失败: {str(exc)}") from exc

    return _build_aigc_report_response(result)


@router.post("/extract-aigc-segments", response_model=AigcMatchedDocxExtractResponse)
async def extract_aigc_segments(
    word_file: UploadFile = File(...),
    report_file: UploadFile = File(...),
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """上传 DOCX 与 AIGC 检测报告 PDF，提取并缓存疑似片段对应的 DOCX 段落。"""
    get_current_user(card_key, db)

    word_filename = word_file.filename or "uploaded.docx"
    word_suffix = Path(word_filename).suffix.lower()
    if word_suffix != ".docx":
        raise HTTPException(status_code=400, detail="仅支持上传 .docx 文件")

    report_filename = report_file.filename or "aigc-report.pdf"
    report_suffix = Path(report_filename).suffix.lower()
    if report_suffix != ".pdf":
        raise HTTPException(status_code=400, detail="仅支持上传 .pdf 检测报告")

    word_content = await word_file.read()
    report_content = await report_file.read()
    if not word_content or not report_content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    max_size_mb = settings.MAX_UPLOAD_FILE_SIZE_MB
    if max_size_mb > 0:
        max_size = max_size_mb * 1024 * 1024
        if len(word_content) > max_size or len(report_content) > max_size:
            raise HTTPException(status_code=400, detail=f"单个文件大小不能超过 {max_size_mb}MB")

    try:
        report_result = parse_aigc_detection_report(report_filename, report_content)
        matched_result = extract_aigc_matched_body_from_word(
            word_filename,
            word_content,
            report_result.segments,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"疑似片段提取失败: {str(exc)}") from exc

    docx_result = matched_result.docx_result
    paragraphs = [
        ExtractedBodyParagraphResponse(
            source_index=item.source_index,
            paragraph_type=item.paragraph_type,
            text=item.text,
        )
        for item in docx_result.paragraphs
    ]

    heading_count = sum(1 for item in docx_result.paragraphs if item.paragraph_type == "heading")
    body_count = len(docx_result.paragraphs) - heading_count

    return AigcMatchedDocxExtractResponse(
        source_filename=docx_result.source_filename,
        output_filename=docx_result.output_filename,
        marked_output_filename=docx_result.marked_output_filename,
        extraction_token=docx_result.extraction_token,
        extracted_text=docx_result.extracted_text,
        start_heading=docx_result.start_heading,
        paragraph_count=len(docx_result.paragraphs),
        heading_count=heading_count,
        body_count=body_count,
        paragraphs=paragraphs,
        report=_build_aigc_report_response(report_result),
        matched_report_segment_count=matched_result.matched_report_segment_count,
        unmatched_report_segment_count=matched_result.unmatched_report_segment_count,
    )


@router.get("/status", response_model=QueueStatusResponse)
async def get_queue_status(
    session_id: str = None,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取队列状态"""
    get_current_user(card_key, db)

    status = await concurrency_manager.get_status(session_id)
    return QueueStatusResponse(**status)


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """列出用户的所有会话（支持分页）"""
    user = get_current_user(card_key, db)

    limit = min(limit, 100)

    results = db.query(
        OptimizationSession,
        func.length(OptimizationSession.original_text).label('original_char_count'),
        func.substring(OptimizationSession.original_text, 1, 50).label('preview_text')
    ).options(
        defer(OptimizationSession.original_text),
        defer(OptimizationSession.error_message)
    ).filter(
        OptimizationSession.user_id == user.id
    ).order_by(OptimizationSession.created_at.desc()).limit(limit).offset(offset).all()

    sessions = []
    for session, char_count, preview_text in results:
        session.original_char_count = char_count or 0
        session.preview_text = preview_text or ""
        sessions.append(session)

    return sessions


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取会话详情"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    segments = db.query(OptimizationSegment).filter(
        OptimizationSegment.session_id == session.id
    ).order_by(OptimizationSegment.segment_index).all()

    return SessionDetailResponse(
        id=session.id,
        session_id=session.session_id,
        current_stage=session.current_stage,
        status=session.status,
        progress=session.progress,
        current_position=session.current_position,
        total_segments=session.total_segments,
        original_char_count=len(session.original_text or ""),
        preview_text=(session.original_text or "")[:50],
        error_message=session.error_message,
        processing_mode=session.processing_mode,
        has_source_doc=session.has_source_doc,
        source_doc_filename=session.source_doc_filename,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
        segments=segments,
    )


@router.get("/sessions/{session_id}/progress", response_model=ProgressUpdate)
async def get_session_progress(
    session_id: str,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取会话进度"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return ProgressUpdate(
        session_id=session.session_id,
        status=session.status,
        progress=session.progress,
        current_position=session.current_position,
        total_segments=session.total_segments,
        current_stage=session.current_stage,
        error_message=session.error_message
    )


@router.get("/sessions/{session_id}/stream")
async def stream_session_progress(
    session_id: str,
    request: Request,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """流式获取会话进度和内容"""
    user = get_current_user(card_key, db)
    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    async def event_generator():
        queue = await stream_manager.connect(session_id)
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield message
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await stream_manager.disconnect(session_id, queue)

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/changes", response_model=List[ChangeLogResponse])
async def get_session_changes(
    session_id: str,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取会话的变更对照"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    latest_log_subquery = db.query(
        ChangeLog.segment_index,
        ChangeLog.stage,
        func.max(ChangeLog.id).label("latest_id")
    ).filter(
        ChangeLog.session_id == session.id
    ).group_by(
        ChangeLog.segment_index,
        ChangeLog.stage
    ).subquery()

    change_logs = db.query(ChangeLog).join(
        latest_log_subquery,
        and_(
            ChangeLog.segment_index == latest_log_subquery.c.segment_index,
            ChangeLog.stage == latest_log_subquery.c.stage,
            ChangeLog.id == latest_log_subquery.c.latest_id
        )
    ).filter(
        ChangeLog.session_id == session.id
    ).order_by(
        ChangeLog.segment_index,
        case((ChangeLog.stage == "polish", 0), else_=1)
    ).all()

    parsed_changes = []
    for change in change_logs:
        detail = None
        if change.changes_detail:
            try:
                detail = json.loads(change.changes_detail)
            except json.JSONDecodeError:
                detail = {"raw": change.changes_detail}

        parsed_changes.append(
            ChangeLogResponse(
                id=change.id,
                segment_index=change.segment_index,
                stage=change.stage,
                before_text=change.before_text,
                after_text=change.after_text,
                changes_detail=detail,
                created_at=change.created_at
            )
        )

    return parsed_changes


@router.post("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    confirmation: ExportConfirmation,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """导出优化结果"""
    if not confirmation.acknowledge_academic_integrity:
        raise HTTPException(status_code=400, detail="必须确认学术诚信承诺")

    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.status != "completed":
        raise HTTPException(status_code=400, detail="会话未完成")

    segments = db.query(OptimizationSegment).filter(
        OptimizationSegment.session_id == session.id
    ).order_by(OptimizationSegment.segment_index).all()

    final_text = _build_final_text(segments)

    if confirmation.export_format == "txt":
        filename = f"optimized_{session_id}.txt"
        return _build_download_response(
            final_text.encode("utf-8"),
            TXT_MEDIA_TYPE,
            filename,
            filename,
        )

    if confirmation.export_format == "docx":
        if not session.has_source_doc:
            raise HTTPException(status_code=400, detail="当前会话不是从 Word 提取正文创建的，无法导出 Word")

        final_paragraphs = [
            (seg.source_doc_paragraph_index, seg.enhanced_text or seg.polished_text or seg.original_text)
            for seg in segments
            if seg.source_doc_paragraph_index is not None
        ]
        if not final_paragraphs:
            raise HTTPException(status_code=400, detail="未找到可回写到 Word 的正文段落")

        try:
            result = build_result_word_from_source(session.source_doc_token, final_paragraphs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"生成优化结果 Word 失败: {str(exc)}") from exc

        return _build_download_response(
            result.content,
            DOCX_MEDIA_TYPE,
            result.output_filename,
            "optimized.docx",
        )

    raise HTTPException(status_code=501, detail="暂不支持此格式")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """删除会话"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    db.delete(session)
    db.commit()

    return {"message": "会话已删除"}


@router.post("/sessions/{session_id}/retry")
async def retry_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """重新尝试处理失败的会话，继续未完成的段落"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.status not in ["failed", "stopped"]:
        raise HTTPException(status_code=400, detail="仅可对失败或已停止的会话执行重试")

    old_error = session.error_message or "未知错误"
    session.status = "queued"
    session.error_message = f"[重试中] 上次失败原因: {old_error}"
    db.commit()

    background_tasks.add_task(run_optimization, session.id)

    return {"message": "已重新排队处理未完成段落"}


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: str,
    card_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """停止正在进行中的会话"""
    user = get_current_user(card_key, db)

    session = db.query(OptimizationSession).filter(
        OptimizationSession.session_id == session_id,
        OptimizationSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.status not in ["queued", "processing"]:
        raise HTTPException(status_code=400, detail="只能停止排队中或处理中的会话")

    session.status = "stopped"
    session.error_message = "用户手动停止"
    db.commit()

    return {"message": "会话已停止"}
