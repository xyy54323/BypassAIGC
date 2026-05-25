from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


try:
    import fitz
except ImportError:  # pragma: no cover - handled at runtime for packaged builds
    fitz = None


VIP_AIGC_TEXT_COLORS = {0x5E30CC}
VIP_AIGC_TEXT_HEX_COLORS = {"#5E30CC"}
VIP_MIN_SEGMENT_TEXT_LENGTH = 12


@dataclass
class PaperPassReportSegment:
    page: int
    ai_percent: float
    risk_level: str
    risk_label: str
    text: str


@dataclass
class PaperPassReportResult:
    source_filename: str
    report_type: str
    report_id: Optional[str]
    title: Optional[str]
    author: Optional[str]
    submitted_at: Optional[str]
    overall_suspicion: Optional[float]
    weighted_suspicion: Optional[float]
    high_ratio: Optional[float]
    medium_ratio: Optional[float]
    low_ratio: Optional[float]
    undetected_ratio: Optional[float]
    word_count: Optional[int]
    paragraph_count: Optional[int]
    sentence_count: Optional[int]
    fragment_count: Optional[int]
    extracted_segment_count: int
    segments: List[PaperPassReportSegment]


def parse_aigc_detection_report(filename: str, content: bytes) -> PaperPassReportResult:
    if fitz is None:
        raise RuntimeError("缺少 PyMuPDF 依赖，无法解析 PDF 检测报告")

    safe_name = filename or "aigc-report.pdf"
    try:
        document = fitz.open(stream=io.BytesIO(content), filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF 文件无法打开，请确认上传的是有效的 AIGC 检测报告") from exc

    try:
        if document.page_count == 0:
            raise ValueError("PDF 文件没有可解析页面")

        first_page_text = document[0].get_text("text") or ""
        if "PaperPass" in first_page_text and "AIGC" in first_page_text:
            return _parse_paperpass_report(safe_name, document, first_page_text)
        if "SpeedAI" in first_page_text and "AIGC" in first_page_text:
            return _parse_speedai_report(safe_name, document, first_page_text)
        if _is_vip_original_comparison_report(first_page_text):
            return _parse_vip_original_comparison_report(safe_name, document, first_page_text)

        raise ValueError("当前仅支持 PaperPass、SpeedAI 或维普 AIGC 原文对照报告 PDF")
    finally:
        document.close()


def parse_paperpass_aigc_report(filename: str, content: bytes) -> PaperPassReportResult:
    return parse_aigc_detection_report(filename, content)


def _parse_paperpass_report(safe_name: str, document, first_page_text: str) -> PaperPassReportResult:
    segments = _extract_colored_segments(document)
    return PaperPassReportResult(
        source_filename=safe_name,
        report_type="PaperPass AIGC",
        report_id=_match_text(first_page_text, r"报告编号[:：]\s*([A-Za-z0-9]+)"),
        title=_match_text(first_page_text, r"论文题目[:：]\s*(.+)"),
        author=_match_text(first_page_text, r"论文作者[:：]\s*(.+)"),
        submitted_at=_match_text(first_page_text, r"提交时间[:：]\s*(.+)"),
        overall_suspicion=_extract_overall_suspicion(first_page_text, weighted=False),
        weighted_suspicion=_extract_overall_suspicion(first_page_text, weighted=True),
        high_ratio=_match_percent(first_page_text, r"高度疑似AIGC占全文比[:：]\s*([\d.]+)%"),
        medium_ratio=_match_percent(first_page_text, r"中度疑似AIGC占全文比[:：]\s*([\d.]+)%"),
        low_ratio=_match_percent(first_page_text, r"轻度疑似AIGC占全文比[:：]\s*([\d.]+)%"),
        undetected_ratio=_match_percent(first_page_text, r"不予检测文字占比[:：]\s*([\d.]+)%"),
        word_count=_match_int(first_page_text, r"论文字数[:：]\s*(\d+)"),
        paragraph_count=_match_int(first_page_text, r"段落个数[:：]\s*(\d+)"),
        sentence_count=_match_int(first_page_text, r"句子个数[:：]\s*(\d+)"),
        fragment_count=_match_int(first_page_text, r"片段个数[:：]\s*(\d+)"),
        extracted_segment_count=len(segments),
        segments=segments,
    )


def _parse_speedai_report(safe_name: str, document, first_page_text: str) -> PaperPassReportResult:
    segments = _extract_speedai_segments(document)
    return PaperPassReportResult(
        source_filename=safe_name,
        report_type="SpeedAI AIGC",
        report_id=_match_text(first_page_text, r"检测编号[:：]\s*([A-Za-z0-9-]+)"),
        title=_match_text(first_page_text, r"标题[:：]\s*(.+)"),
        author=_match_text(first_page_text, r"作者[:：]\s*(.+)"),
        submitted_at=_match_text(first_page_text, r"检测时间[:：]\s*(.+)"),
        overall_suspicion=_match_percent(first_page_text, r"疑似AIGC风险概率[:：]\s*([\d.]+)%"),
        weighted_suspicion=None,
        high_ratio=_match_percent(first_page_text, r"高风险文本（[^）]*）[:：]\s*\d+字，占比([\d.]+)%"),
        medium_ratio=_match_percent(first_page_text, r"中风险文本（[^）]*）[:：]\s*\d+字，占比([\d.]+)%"),
        low_ratio=_match_percent(first_page_text, r"低风险文本（[^）]*）[:：]\s*\d+字，占比([\d.]+)%"),
        undetected_ratio=_match_percent(first_page_text, r"无风险文本（[^）]*）[:：]\s*\d+字，占比([\d.]+)%"),
        word_count=_match_int(first_page_text, r"总字数[:：]\s*(\d+)"),
        paragraph_count=None,
        sentence_count=None,
        fragment_count=len(segments),
        extracted_segment_count=len(segments),
        segments=segments,
    )


def _parse_vip_original_comparison_report(
    safe_name: str,
    document,
    first_page_text: str,
) -> PaperPassReportResult:
    overall_suspicion = _extract_vip_overall_suspicion(first_page_text)
    segments = _extract_vip_aigc_segments(document, overall_suspicion)
    return PaperPassReportResult(
        source_filename=safe_name,
        report_type="维普 AIGC 原文对照报告",
        report_id=_extract_vip_report_id(first_page_text),
        title=_extract_vip_metadata_value(first_page_text, "题目"),
        author=_extract_vip_metadata_value(first_page_text, "作者"),
        submitted_at=_match_text(first_page_text, r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"),
        overall_suspicion=overall_suspicion,
        weighted_suspicion=None,
        high_ratio=None,
        medium_ratio=None,
        low_ratio=None,
        undetected_ratio=None,
        word_count=_match_int(first_page_text, r"论文字符数[:：]\s*(\d+)"),
        paragraph_count=None,
        sentence_count=None,
        fragment_count=len(segments),
        extracted_segment_count=len(segments),
        segments=segments,
    )


def _is_vip_original_comparison_report(text: str) -> bool:
    normalized = text or ""
    return (
        "原文对照报告" in normalized
        and "AIGC" in normalized
        and ("疑似AIGC生成" in normalized or "疑似AICG生成" in normalized)
    )


def _extract_vip_aigc_segments(
    document,
    overall_suspicion: Optional[float],
) -> List[PaperPassReportSegment]:
    segments: List[PaperPassReportSegment] = []
    seen = set()
    ai_percent = overall_suspicion if overall_suspicion is not None else 0.0

    for page_index in range(document.page_count):
        for line in _extract_vip_aigc_lines(document[page_index]):
            text = _normalize_report_line(line["text"])
            compact = re.sub(r"\s+", "", text)
            if len(compact) < VIP_MIN_SEGMENT_TEXT_LENGTH:
                continue
            if compact in seen:
                continue

            seen.add(compact)
            segments.append(
                PaperPassReportSegment(
                    page=page_index + 1,
                    ai_percent=ai_percent,
                    risk_level="medium",
                    risk_label="疑似AIGC生成",
                    text=text,
                )
            )

    return segments


def _extract_vip_aigc_lines(page) -> List[dict]:
    spans = []
    for span in page.get_texttrace():
        if not _is_vip_aigc_span(span):
            continue
        text = _extract_texttrace_span_text(span).strip()
        if not text:
            continue
        bbox = fitz.Rect(span.get("bbox"))
        spans.append(
            {
                "bbox": bbox,
                "text": text,
                "center_y": (bbox.y0 + bbox.y1) / 2,
            }
        )

    return _group_vip_spans_by_line(spans)


def _is_vip_aigc_span(span: dict) -> bool:
    color = span.get("color")
    if isinstance(color, int):
        return color in VIP_AIGC_TEXT_COLORS
    return _color_to_hex(color) in VIP_AIGC_TEXT_HEX_COLORS


def _extract_texttrace_span_text(span: dict) -> str:
    return "".join(chr(char[0]) for char in span.get("chars", []))


def _group_vip_spans_by_line(spans: List[dict]) -> List[dict]:
    grouped: List[dict] = []
    y_tolerance = 3.0

    for span in sorted(spans, key=lambda item: (item["center_y"], item["bbox"].x0)):
        target = None
        for line in grouped:
            if abs(span["center_y"] - line["center_y"]) <= y_tolerance:
                target = line
                break

        if target is None:
            grouped.append(
                {
                    "center_y": span["center_y"],
                    "spans": [span],
                }
            )
            continue

        target["spans"].append(span)
        target["center_y"] = sum(item["center_y"] for item in target["spans"]) / len(target["spans"])

    lines = []
    for line in sorted(grouped, key=lambda item: item["center_y"]):
        ordered_spans = sorted(line["spans"], key=lambda item: item["bbox"].x0)
        line_bbox = ordered_spans[0]["bbox"]
        for span in ordered_spans[1:]:
            line_bbox |= span["bbox"]
        lines.append(
            {
                "bbox": line_bbox,
                "text": _join_span_texts([item["text"] for item in ordered_spans]),
            }
        )

    return lines


def _join_span_texts(texts: List[str]) -> str:
    content = ""
    for text in texts:
        if not text:
            continue
        if content and _needs_space(content[-1], text[0]):
            content += " "
        content += text
    return content


def _extract_vip_report_id(text: str) -> Optional[str]:
    match = re.search(r"(?m)^([A-Za-z0-9]{10,})$", text or "")
    return match.group(1) if match else None


def _extract_vip_metadata_value(text: str, label: str) -> Optional[str]:
    lines = [
        _normalize_report_line(line)
        for line in (text or "").splitlines()
        if _normalize_report_line(line)
    ]
    for index, line in enumerate(lines):
        if not line.startswith(label):
            continue
        for candidate in reversed(lines[:index]):
            if _is_vip_metadata_candidate(candidate):
                return candidate
    return None


def _is_vip_metadata_candidate(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"\d+", text):
        return False
    if re.fullmatch(r"[\d.]+%", text):
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text):
        return False
    if re.fullmatch(r"[A-Za-z0-9]{10,}", text):
        return False
    return text not in {
        "NO.",
        "原文对照报告（PDF）·",
        "通用版",
        "检测结果",
        "结果分布",
        "题目：",
        "作者：",
        "检测所属单位：",
    }


def _extract_vip_overall_suspicion(text: str) -> Optional[float]:
    lines = [
        _normalize_report_line(line)
        for line in (text or "").splitlines()
        if _normalize_report_line(line)
    ]
    result_start = next((index for index, line in enumerate(lines) if line == "检测结果"), 0)
    for index, line in enumerate(lines[result_start:], start=result_start):
        if line != "人工撰写占比":
            continue
        for candidate in lines[index + 1 : index + 5]:
            match = re.fullmatch(r"([\d.]+)%", candidate)
            if match:
                return _to_float(match.group(1))

    match = re.search(r"疑似\s*AIGC\s*生成占比[:：]?\s*([\d.]+)%", text or "", re.IGNORECASE)
    return _to_float(match.group(1)) if match else None


def _extract_overall_suspicion(text: str, weighted: bool) -> Optional[float]:
    matches = re.findall(r"AIGC总体疑似度\(高\+中\+轻\)[:：]\s*([\d.]+)%([^\n]*)", text)
    for value, suffix in matches:
        is_weighted = "加权" in suffix
        if is_weighted == weighted:
            return _to_float(value)
    return None


def _extract_colored_segments(document) -> List[PaperPassReportSegment]:
    segments: List[PaperPassReportSegment] = []
    for page_index in range(document.page_count):
        page = document[page_index]
        labels = _extract_ai_labels(page)
        if not labels:
            continue

        highlight_rects = _extract_highlight_rects(page)
        labels = sorted(labels, key=lambda item: (item["bbox"].y0, item["bbox"].x0))

        for index, label in enumerate(labels):
            next_y = labels[index + 1]["bbox"].y0 if index + 1 < len(labels) else page.rect.height
            group_rects = [
                rect
                for rect in highlight_rects
                if rect.y0 >= label["bbox"].y0 - 1 and rect.y0 < next_y - 1
            ]
            text = _extract_text_in_rects(page, group_rects)
            if not text:
                continue

            risk_level, risk_label = _classify_risk(label["percent"])
            segments.append(
                PaperPassReportSegment(
                    page=page_index + 1,
                    ai_percent=label["percent"],
                    risk_level=risk_level,
                    risk_label=risk_label,
                    text=text,
                )
            )

    return segments


def _extract_speedai_segments(document) -> List[PaperPassReportSegment]:
    section_text = _extract_speedai_summary_section(document)
    if not section_text:
        return []

    lines = [
        _normalize_report_line(line)
        for line in section_text.splitlines()
        if _normalize_report_line(line)
    ]
    start_index = next(
        (index for index, line in enumerate(lines) if "片段汇总列表" in line),
        -1,
    )
    if start_index < 0:
        return []

    segments: List[PaperPassReportSegment] = []
    index = start_index + 1
    while index < len(lines):
        line = lines[index]
        if line in {"序号", "段落内容", "AI生成概率", "风险等级"}:
            index += 1
            continue
        if not re.fullmatch(r"\d+", line):
            index += 1
            continue

        row_number = int(line)
        index += 1
        text_lines: List[str] = []
        ai_percent: Optional[float] = None

        while index < len(lines):
            current = lines[index]
            percent_match = re.fullmatch(r"([\d.]+)\s*%", current)
            if percent_match:
                ai_percent = _to_float(percent_match.group(1))
                index += 1
                break
            if current in {"序号", "段落内容", "AI生成概率", "风险等级"}:
                index += 1
                continue
            if re.fullmatch(r"\d+", current) and text_lines:
                break
            text_lines.append(current)
            index += 1

        risk_text = ""
        if index < len(lines) and "风险" in lines[index]:
            risk_text = lines[index]
            index += 1

        text = _join_lines(text_lines)
        if text and ai_percent is not None:
            risk_level, risk_label = _classify_speedai_risk(ai_percent, risk_text)
            segments.append(
                PaperPassReportSegment(
                    page=row_number,
                    ai_percent=ai_percent,
                    risk_level=risk_level,
                    risk_label=risk_label,
                    text=text,
                )
            )

    return segments


def _extract_speedai_summary_section(document) -> str:
    parts = []
    for page_index in range(document.page_count):
        text = document[page_index].get_text("text") or ""
        if "原文内容" in text:
            before_original, _ = text.split("原文内容", 1)
            parts.append(before_original)
            break
        parts.append(text)

    combined = "\n".join(parts)
    if "片段汇总列表" not in combined:
        return ""
    return combined


def _normalize_report_line(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", text or "").strip()


def _extract_ai_labels(page) -> List[dict]:
    labels = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            match = re.search(r"AI\s*([\d.]+)\s*%", line_text, re.IGNORECASE)
            if match:
                labels.append(
                    {
                        "percent": _to_float(match.group(1)) or 0.0,
                        "bbox": fitz.Rect(line.get("bbox")),
                    }
                )
    return labels


def _extract_highlight_rects(page) -> List:
    rects = []
    for drawing in page.get_drawings():
        fill = _color_to_hex(drawing.get("fill"))
        if fill in {None, "#FFFFFF", "#000000", "#B0B0B0"}:
            continue

        rect = fitz.Rect(drawing.get("rect"))
        if rect.width < 40 or rect.height < 5:
            continue
        rects.append(rect)
    return sorted(rects, key=lambda item: (item.y0, item.x0))


def _extract_text_in_rects(page, rects: List) -> str:
    if not rects:
        return ""

    words = []
    for word in page.get_text("words"):
        x0, y0, x1, y1, text, *_ = word
        clean = text.strip()
        if not clean:
            continue

        word_rect = fitz.Rect(x0, y0, x1, y1)
        if not any(word_rect.intersects(rect) for rect in rects):
            continue

        words.append(
            {
                "bbox": word_rect,
                "text": clean,
                "center_y": (word_rect.y0 + word_rect.y1) / 2,
            }
        )

    ordered_lines = [_join_line_words(line) for line in _group_words_by_visual_line(words)]
    return _join_lines(ordered_lines)


def _group_words_by_visual_line(words: List[dict]) -> List[List[dict]]:
    lines: List[dict] = []
    y_tolerance = 4.0

    for word in sorted(words, key=lambda item: (item["center_y"], item["bbox"].x0)):
        target_line = None
        for line in lines:
            if abs(word["center_y"] - line["center_y"]) <= y_tolerance:
                target_line = line
                break

        if target_line is None:
            lines.append({"center_y": word["center_y"], "words": [word]})
            continue

        target_line["words"].append(word)
        target_line["center_y"] = sum(item["center_y"] for item in target_line["words"]) / len(target_line["words"])

    return [
        sorted(line["words"], key=lambda item: item["bbox"].x0)
        for line in sorted(lines, key=lambda item: item["center_y"])
    ]


def _join_line_words(words: List[dict]) -> str:
    content = ""
    for word in words:
        text = word["text"]
        if not content:
            content = text
            continue
        if _needs_space(content[-1], text[0]):
            content += " "
        content += text
    return content


def _join_lines(lines: List[str]) -> str:
    content = ""
    for line in lines:
        clean = line.strip()
        if not clean:
            continue
        if content and _needs_space(content[-1], clean[0]):
            content += " "
        content += clean
    return re.sub(r"\s+", " ", content).strip()


def _needs_space(left: str, right: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9]", left) and re.match(r"[A-Za-z0-9]", right))


def _classify_risk(percent: float) -> tuple[str, str]:
    if percent >= 70:
        return "high", "高度疑似"
    if percent >= 60:
        return "medium", "中度疑似"
    if percent >= 50:
        return "low", "轻度疑似"
    return "normal", "低疑似"


def _classify_speedai_risk(percent: float, risk_text: str) -> tuple[str, str]:
    risk_text = risk_text or ""
    if "高" in risk_text:
        return "high", risk_text
    if "中" in risk_text:
        return "medium", risk_text
    if "低" in risk_text:
        return "low", risk_text
    if "无" in risk_text:
        return "normal", risk_text
    if percent >= 90:
        return "high", "高风险"
    if percent >= 70:
        return "medium", "中风险"
    if percent >= 50:
        return "low", "低风险"
    return "normal", "无风险"


def _color_to_hex(color) -> Optional[str]:
    if not color:
        return None
    values = [max(0, min(255, int(round(item * 255)))) for item in color[:3]]
    return "#" + "".join(f"{value:02X}" for value in values)


def _match_text(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _match_percent(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE)
    return _to_float(match.group(1)) if match else None


def _match_int(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
