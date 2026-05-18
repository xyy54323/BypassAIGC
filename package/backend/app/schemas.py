from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserCreate(BaseModel):
    """创建用户"""
    card_key: str
    access_link: str


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    card_key: str
    access_link: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime] = None
    usage_limit: int
    usage_count: int
    
    class Config:
        from_attributes = True


class ModelConfig(BaseModel):
    """模型配置"""
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class OptimizationCreate(BaseModel):
    """创建优化任务"""
    original_text: str
    processing_mode: str = Field(default='paper_polish_enhance',
                                  description='处理模式: paper_polish, paper_enhance, paper_polish_enhance')
    polish_config: Optional[ModelConfig] = None
    enhance_config: Optional[ModelConfig] = None
    extraction_token: Optional[str] = None


class SegmentResponse(BaseModel):
    """段落响应"""
    id: int
    segment_index: int
    stage: str
    original_text: str
    polished_text: Optional[str] = None
    enhanced_text: Optional[str] = None
    status: str
    is_title: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """会话响应"""
    id: int
    session_id: str
    current_stage: str
    status: str
    progress: float
    current_position: int
    total_segments: int
    original_char_count: int = 0
    preview_text: Optional[str] = None
    error_message: Optional[str] = None
    processing_mode: str = 'paper_polish_enhance'
    has_source_doc: bool = False
    source_doc_filename: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    """会话详细响应"""
    segments: List[SegmentResponse] = []


class QueueStatusResponse(BaseModel):
    """队列状态响应"""
    current_users: int
    max_users: int
    queue_length: int
    your_position: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # 秒


class ProgressUpdate(BaseModel):
    """进度更新"""
    session_id: str
    status: str
    progress: float
    current_position: int
    total_segments: int
    current_stage: str
    error_message: Optional[str] = None


class ChangeLogResponse(BaseModel):
    """变更对照响应"""
    id: int
    segment_index: int
    stage: str
    before_text: str
    after_text: str
    changes_detail: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ExportConfirmation(BaseModel):
    """导出确认"""
    session_id: str
    acknowledge_academic_integrity: bool
    export_format: str = Field(..., pattern="^(txt|docx|pdf)$")


class ExtractedBodyParagraphResponse(BaseModel):
    """提取出的正文段落"""
    source_index: int
    paragraph_type: str
    text: str


class DocxBodyExtractResponse(BaseModel):
    """Word 正文提取响应"""
    source_filename: str
    output_filename: str
    marked_output_filename: str
    extraction_token: str
    extracted_text: str
    start_heading: str
    paragraph_count: int
    heading_count: int
    body_count: int
    paragraphs: List[ExtractedBodyParagraphResponse]


class AigcReportSegmentResponse(BaseModel):
    """AIGC 检测报告疑似片段"""
    page: int
    ai_percent: float
    risk_level: str
    risk_label: str
    text: str


class AigcReportExtractResponse(BaseModel):
    """AIGC 检测报告解析响应"""
    source_filename: str
    report_type: str
    report_id: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    submitted_at: Optional[str] = None
    overall_suspicion: Optional[float] = None
    weighted_suspicion: Optional[float] = None
    high_ratio: Optional[float] = None
    medium_ratio: Optional[float] = None
    low_ratio: Optional[float] = None
    undetected_ratio: Optional[float] = None
    word_count: Optional[int] = None
    paragraph_count: Optional[int] = None
    sentence_count: Optional[int] = None
    fragment_count: Optional[int] = None
    extracted_segment_count: int
    segments: List[AigcReportSegmentResponse]


class AigcMatchedDocxExtractResponse(DocxBodyExtractResponse):
    """Word 与 AIGC 检测报告联合提取响应"""
    report: AigcReportExtractResponse
    matched_report_segment_count: int
    unmatched_report_segment_count: int


class MarkExtractedWordRequest(BaseModel):
    """按提取缓存生成标记版 Word"""
    extraction_token: str


class CardKeyGenerate(BaseModel):
    """生成卡密"""
    count: int = Field(1, ge=1, le=100)
    prefix: Optional[str] = None


class CardKeyResponse(BaseModel):
    """卡密响应"""
    card_key: str
    access_link: str
    created_at: datetime


class UserUsageUpdate(BaseModel):
    """更新用户使用限制"""
    usage_limit: int = Field(..., ge=0)  # 0 表示无限制
    reset_usage_count: bool = False


class PromptCreate(BaseModel):
    """创建提示词"""
    name: str
    stage: str = Field(..., pattern="^(polish|enhance)$")
    content: str
    is_default: bool = False


class PromptUpdate(BaseModel):
    """更新提示词"""
    name: Optional[str] = None
    content: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class PromptResponse(BaseModel):
    """提示词响应"""
    id: int
    user_id: Optional[int] = None
    name: str
    stage: str
    content: str
    is_default: bool
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True



