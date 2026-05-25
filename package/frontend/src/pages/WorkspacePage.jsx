import React, { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  FileText, History, Play, Upload, Copy, Download,
  Clock, AlertCircle, CheckCircle, Trash2, Info, FileUp, X, Settings,
  FileSearch, BarChart3
} from 'lucide-react';
import { optimizationAPI } from '../api';
import ConfigManager from '../components/ConfigManager';

const LOCAL_ADMIN_TOKEN = 'local-admin';

// 会话列表项组件 - 使用 memo 避免不必要重渲染
const SessionItem = memo(({ session, activeSession, onView, onDelete, onRetry }) => {
  const handleDelete = useCallback((e) => {
    e.stopPropagation();
    onDelete(session);
  }, [session, onDelete]);

  const handleRetry = useCallback((e) => {
    e.stopPropagation();
    if (session.status === 'failed') {
      onRetry(session);
    }
  }, [session, onRetry]);

  const handleView = useCallback(() => {
    onView(session.session_id);
  }, [session.session_id, onView]);

  return (
    <div
      onClick={handleView}
      className="group p-3 rounded-xl hover:bg-gray-50 transition-all cursor-pointer border border-transparent hover:border-gray-100 relative"
    >
      <div className="flex items-start justify-between mb-1.5 gap-2">
        <div className="flex items-center gap-1.5">
          {session.status === 'completed' && (
            <CheckCircle className="w-4 h-4 text-ios-green" />
          )}
          {session.status === 'processing' && (
            <div className="w-4 h-4 border-2 border-ios-blue border-t-transparent rounded-full animate-spin" />
          )}
          {session.status === 'failed' && (
            <AlertCircle className="w-4 h-4 text-ios-red" />
          )}
          {session.status === 'stopped' && (
            <AlertCircle className="w-4 h-4 text-orange-500" />
          )}
          <span className={`text-[13px] font-medium ${
            session.status === 'completed' ? 'text-black' :
            session.status === 'processing' ? 'text-ios-blue' :
            session.status === 'failed' ? 'text-ios-red' :
            session.status === 'stopped' ? 'text-orange-600' : 'text-ios-gray'
          }`}>
            {session.status === 'completed' && '已完成'}
            {session.status === 'processing' && '处理中'}
            {session.status === 'queued' && '排队中'}
            {session.status === 'failed' && '失败'}
            {session.status === 'stopped' && '已停止'}
          </span>
        </div>

        <span className="text-[11px] text-ios-gray/70 font-medium">
          {new Date(session.created_at).toLocaleDateString()}
        </span>
      </div>

      <p className="text-[13px] text-ios-gray leading-snug line-clamp-2 mb-2 pr-6">
        {session.preview_text || '暂无预览'}
      </p>

      {session.status === 'processing' && (
        <div className="w-full bg-gray-100 rounded-full h-1 mb-1">
          <div
            className="bg-ios-blue h-1 rounded-full"
            style={{ width: `${session.progress}%` }}
          />
        </div>
      )}

      {/* 操作按钮 */}
      <div className="flex items-center justify-between mt-1">
        {session.status === 'failed' && (
          <button
            onClick={handleRetry}
            className="px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200"
          >
            继续处理
          </button>
        )}
        <button
          onClick={handleDelete}
          className="p-1.5 text-gray-300 hover:text-ios-red hover:bg-red-50 rounded-lg transition-colors ml-auto"
          title="删除会话"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {session.status === 'failed' && session.current_position < session.total_segments && (
        <div className="text-[11px] text-ios-red bg-red-50 px-2 py-1 rounded mt-1">
          {session.error_message ? '发生错误' : '网络超时'}
        </div>
      )}
    </div>
  );
});

SessionItem.displayName = 'SessionItem';

const getDownloadFilenameFromHeaders = (headers, fallback) => {
  const disposition = headers?.['content-disposition'];
  if (!disposition) {
    return fallback;
  }

  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const asciiMatch = disposition.match(/filename="([^"]+)"/i);
  if (asciiMatch?.[1]) {
    return asciiMatch[1];
  }

  return fallback;
};

const readBlobErrorMessage = async (payload, fallback) => {
  if (!payload) {
    return fallback;
  }

  if (payload instanceof Blob) {
    try {
      const text = await payload.text();
      const data = JSON.parse(text);
      return data?.detail || fallback;
    } catch {
      return fallback;
    }
  }

  return payload?.detail || fallback;
};
const WorkspacePage = () => {
  const [text, setText] = useState('');
  const [processingMode, setProcessingMode] = useState('paper_polish_enhance');
  const [sessions, setSessions] = useState([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [selectedWordFile, setSelectedWordFile] = useState(null);
  const [isExtractingWord, setIsExtractingWord] = useState(false);
  const [isDownloadingMarkedWord, setIsDownloadingMarkedWord] = useState(false);
  const [extractedDocResult, setExtractedDocResult] = useState(null);
  const [optimizationSource, setOptimizationSource] = useState(null);
  const [selectedReportWordFile, setSelectedReportWordFile] = useState(null);
  const [selectedReportFile, setSelectedReportFile] = useState(null);
  const [isExtractingReport, setIsExtractingReport] = useState(false);
  const [isDownloadingReportMarkedWord, setIsDownloadingReportMarkedWord] = useState(false);
  const [aigcSegmentResult, setAigcSegmentResult] = useState(null);
  const [aigcReportResult, setAigcReportResult] = useState(null);
  const [activeView, setActiveView] = useState('aigc');
  const [activeAigcFeature, setActiveAigcFeature] = useState(null);
  const fileInputRef = useRef(null);
  const reportWordInputRef = useRef(null);
  const reportInputRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const view = new URLSearchParams(location.search).get('view');
    if (view === 'history' || view === 'aigc' || view === 'config') {
      setActiveView(view);
    }
  }, [location.search]);

  // 使用 useCallback 优化函数引用稳定性
  const loadSessions = useCallback(async () => {
    try {
      setIsLoadingSessions(true);
      const response = await optimizationAPI.listSessions();
      setSessions(response.data);

      // 查找正在处理的会话
      const processing = response.data.find(
        s => s.status === 'processing' || s.status === 'queued'
      );
      if (processing) {
        setActiveSession(processing.session_id);
      }
    } catch (error) {
      console.error('加载会话失败:', error);
    } finally {
      setIsLoadingSessions(false);
    }
  }, []);

  // loadQueueStatus 不依赖 activeSession，避免 useEffect 重复触发
  const loadQueueStatus = useCallback(async () => {
    try {
      const response = await optimizationAPI.getQueueStatus();
      setQueueStatus(response.data);
    } catch (error) {
      console.error('加载队列状态失败:', error);
    }
  }, []);

  const updateSessionProgress = useCallback(async (sessionId) => {
    try {
      const response = await optimizationAPI.getSessionProgress(sessionId);
      const progress = response.data;

      // 更新会话列表中的进度 - 只在数据有变化时更新
      setSessions(prev => {
        const target = prev.find(s => s.session_id === sessionId);
        if (target && target.progress === progress.progress && target.status === progress.status) {
          return prev; // 无变化，不触发重渲染
        }
        return prev.map(s =>
          s.session_id === sessionId ? { ...s, ...progress } : s
        );
      });

      // 如果会话完成,刷新列表
      if (progress.status === 'completed' || progress.status === 'failed') {
        setActiveSession(null);
        loadSessions();

        if (progress.status === 'completed') {
          toast.success('优化完成!');
        } else {
          toast.error(`优化失败: ${progress.error_message}`);
        }
      }
    } catch (error) {
      console.error('更新进度失败:', error);
    }
  }, [loadSessions]);

  // 初始加载 - 只在组件挂载时执行一次
  useEffect(() => {
    loadSessions();
    loadQueueStatus();
  }, [loadSessions, loadQueueStatus]);

  // 队列状态轮询 - 独立的 useEffect，避免与初始加载混淆
  useEffect(() => {
    const interval = setInterval(loadQueueStatus, 15000);
    return () => clearInterval(interval);
  }, [loadQueueStatus]);

  useEffect(() => {
    // 如果有活跃会话,每4秒更新进度（进一步降低频率）
    if (activeSession) {
      const interval = setInterval(() => {
        updateSessionProgress(activeSession);
      }, 4000);
      return () => clearInterval(interval);
    }
  }, [activeSession, updateSessionProgress]);

  const resetWordFileInput = useCallback(() => {
    setSelectedWordFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const handlePickWordFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleWordFileChange = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.docx')) {
      toast.error('请上传 .docx 文件');
      event.target.value = '';
      return;
    }

    setExtractedDocResult(null);
    setSelectedWordFile(file);
  }, []);

  const handleExtractWordBody = useCallback(async () => {
    if (!selectedWordFile) {
      toast.error('请先选择 DOCX 文件');
      return;
    }

    try {
      setIsExtractingWord(true);
      const response = await optimizationAPI.extractWordBody(selectedWordFile);
      const result = response.data;
      setExtractedDocResult(result);
      setText(result.extracted_text);
      setOptimizationSource({ type: 'full', extractionToken: result.extraction_token });
      toast.success(`正文提取完成，已识别 ${result.paragraph_count} 个段落并填入输入框`);
    } catch (error) {
      console.error('Word 正文提取失败:', error);
      toast.error(error.response?.data?.detail || 'Word 正文提取失败');
    } finally {
      setIsExtractingWord(false);
    }
  }, [selectedWordFile]);

  const handleCopyExtractedText = useCallback(async () => {
    const content = extractedDocResult?.extracted_text;
    if (!content) {
      toast.error('暂无可复制内容');
      return;
    }

    try {
      await navigator.clipboard.writeText(content);
      toast.success('识别结果已复制');
    } catch (error) {
      toast.error('复制失败，请手动选择文本复制');
    }
  }, [extractedDocResult]);

  const handleDownloadExtractedText = useCallback(() => {
    const content = extractedDocResult?.extracted_text;
    if (!content) {
      toast.error('暂无可下载内容');
      return;
    }

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = extractedDocResult.output_filename || '正文提取结果.txt';
    a.click();
    window.URL.revokeObjectURL(url);
  }, [extractedDocResult]);

  const handleDownloadMarkedWord = useCallback(async () => {
    if (!selectedWordFile) {
      toast.error('请保留原始 DOCX 文件后再下载标记版');
      return;
    }

    try {
      setIsDownloadingMarkedWord(true);
      const response = await optimizationAPI.downloadMarkedWord(selectedWordFile);
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = getDownloadFilenameFromHeaders(
        response.headers,
        extractedDocResult?.marked_output_filename || '正文提取标记版.docx'
      );
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success('标记版 DOCX 已下载');
    } catch (error) {
      console.error('下载标记 DOCX 失败:', error);
      const message = await readBlobErrorMessage(error.response?.data, '下载标记 DOCX 失败');
      toast.error(message);
    } finally {
      setIsDownloadingMarkedWord(false);
    }
  }, [extractedDocResult?.marked_output_filename, selectedWordFile]);

  const handleClearExtractedResult = useCallback(() => {
    setExtractedDocResult(null);
    setOptimizationSource(prev => prev?.type === 'full' ? null : prev);
  }, []);

  const resetReportWordFileInput = useCallback(() => {
    setSelectedReportWordFile(null);
    setAigcSegmentResult(null);
    setAigcReportResult(null);
    setOptimizationSource(prev => prev?.type === 'aigc' ? null : prev);
    if (reportWordInputRef.current) {
      reportWordInputRef.current.value = '';
    }
  }, []);

  const handlePickReportWordFile = useCallback(() => {
    reportWordInputRef.current?.click();
  }, []);

  const handleReportWordFileChange = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.docx')) {
      toast.error('请上传 .docx 文件');
      event.target.value = '';
      return;
    }

    setAigcSegmentResult(null);
    setAigcReportResult(null);
    setOptimizationSource(prev => prev?.type === 'aigc' ? null : prev);
    setSelectedReportWordFile(file);
  }, []);

  const resetReportFileInput = useCallback(() => {
    setSelectedReportFile(null);
    setAigcSegmentResult(null);
    setAigcReportResult(null);
    setOptimizationSource(prev => prev?.type === 'aigc' ? null : prev);
    if (reportInputRef.current) {
      reportInputRef.current.value = '';
    }
  }, []);

  const handlePickReportFile = useCallback(() => {
    reportInputRef.current?.click();
  }, []);

  const handleReportFileChange = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('请上传 .pdf 检测报告');
      event.target.value = '';
      return;
    }

    setAigcReportResult(null);
    setAigcSegmentResult(null);
    setOptimizationSource(prev => prev?.type === 'aigc' ? null : prev);
    setSelectedReportFile(file);
  }, []);

  const handleExtractAigcReport = useCallback(async () => {
    if (!selectedReportWordFile) {
      toast.error('请先选择原始 DOCX 文件');
      return;
    }
    if (!selectedReportFile) {
      toast.error('请先选择 AIGC 检测报告 PDF');
      return;
    }

    try {
      setIsExtractingReport(true);
      const response = await optimizationAPI.extractAigcSegments(selectedReportWordFile, selectedReportFile);
      const result = response.data;
      setAigcSegmentResult(result);
      setAigcReportResult(result.report);
      setText(result.extracted_text);
      setOptimizationSource({ type: 'aigc', extractionToken: result.extraction_token });
      toast.success(`AIGC片段提取完成，已匹配 ${result.paragraph_count || 0} 个 DOCX 段落`);
    } catch (error) {
      console.error('AIGC 疑似片段提取失败:', error);
      toast.error(error.response?.data?.detail || 'AIGC 疑似片段提取失败');
    } finally {
      setIsExtractingReport(false);
    }
  }, [selectedReportFile, selectedReportWordFile]);

  const handleClearAigcReport = useCallback(() => {
    setAigcReportResult(null);
    setAigcSegmentResult(null);
    setOptimizationSource(prev => prev?.type === 'aigc' ? null : prev);
  }, []);

  const handleDownloadReportMarkedWord = useCallback(async () => {
    if (!aigcSegmentResult?.extraction_token) {
      toast.error('请先提取疑似片段');
      return;
    }

    try {
      setIsDownloadingReportMarkedWord(true);
      const response = await optimizationAPI.downloadMarkedExtractedWord(aigcSegmentResult.extraction_token);
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = getDownloadFilenameFromHeaders(
        response.headers,
        aigcSegmentResult.marked_output_filename || '疑似片段标记版.docx'
      );
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success('AIGC片段标记版 DOCX 已下载');
    } catch (error) {
      console.error('下载 AIGC 片段标记 DOCX 失败:', error);
      const message = await readBlobErrorMessage(error.response?.data, '下载 AIGC 片段标记 DOCX 失败');
      toast.error(message);
    } finally {
      setIsDownloadingReportMarkedWord(false);
    }
  }, [aigcSegmentResult]);

  const handleStartOptimization = useCallback(async () => {
    if (!text.trim()) {
      toast.error('请输入要优化的文本');
      return;
    }

    if (isSubmitting) {
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await optimizationAPI.startOptimization({
        original_text: text,
        processing_mode: processingMode,
        extraction_token: optimizationSource?.extractionToken || null,
      });

      setActiveSession(response.data.session_id);
      toast.success('优化任务已启动');
      setText('');
      loadSessions();
    } catch (error) {
      toast.error('启动优化失败: ' + error.response?.data?.detail);
    } finally {
      setIsSubmitting(false);
    }
  }, [text, processingMode, isSubmitting, loadSessions, optimizationSource]);

  const handleSwitchView = useCallback((view) => {
    setActiveView(view);
    const viewRoute = view === 'aigc' ? '/' : `/?view=${view}`;
    navigate(viewRoute, { replace: true });
  }, [navigate]);

  const handleOpenAdmin = useCallback(() => {
    handleSwitchView('config');
  }, [handleSwitchView]);

  const handleSelectAigcFeature = useCallback((feature) => {
    const expectedSourceType = feature === 'full' ? 'full' : 'aigc';
    if (optimizationSource && optimizationSource.type !== expectedSourceType) {
      setText('');
      setOptimizationSource(null);
    }
    setActiveAigcFeature(feature);
  }, [optimizationSource]);

  const handleBackToAigcFeatures = useCallback(() => {
    setActiveAigcFeature(null);
  }, []);

  const handleDeleteSession = useCallback(async (session) => {
    const confirmDelete = window.confirm('确认删除该会话及其结果吗?');
    if (!confirmDelete) {
      return;
    }

    try {
      await optimizationAPI.deleteSession(session.session_id);
      if (activeSession === session.session_id) {
        setActiveSession(null);
      }
      toast.success('会话已删除');
      await loadSessions();
    } catch (error) {
      console.error('删除会话失败:', error);
      toast.error(error.response?.data?.detail || '删除会话失败');
    }
  }, [activeSession, loadSessions]);

  const handleViewSession = useCallback((sessionId) => {
    navigate(`/session/${sessionId}`);
  }, [navigate]);

  const handleRetrySegment = useCallback(async (session) => {
    if (session.status !== 'failed') {
      return;
    }

    const confirmRetry = window.confirm('检测到会话执行失败。是否继续处理未完成的段落?');
    if (!confirmRetry) {
      return;
    }

    try {
      const response = await optimizationAPI.retryFailedSegments(session.session_id);
      setActiveSession(session.session_id);
      toast.success(response.data?.message || '已重新继续处理未完成段落');
      await loadSessions();
    } catch (error) {
      console.error('重试失败:', error);
      toast.error(error.response?.data?.detail || '重试失败，请稍后再试');
    }
  }, [loadSessions]);

  // 使用 useMemo 缓存当前活跃会话的数据
  const currentActiveSessionData = useMemo(() => {
    return sessions.find(s => s.session_id === activeSession);
  }, [sessions, activeSession]);

  const sessionStats = useMemo(() => {
    return sessions.reduce(
      (acc, session) => {
        acc.total += 1;
        if (session.status === 'completed') acc.completed += 1;
        if (session.status === 'processing' || session.status === 'queued') acc.processing += 1;
        if (session.status === 'failed') acc.failed += 1;
        return acc;
      },
      { total: 0, completed: 0, processing: 0, failed: 0 }
    );
  }, [sessions]);

  const modeOptions = [
    { id: 'paper_polish', title: '轻度润色', desc: '让文字更自然' },
    { id: 'paper_enhance', title: '重点降AI', desc: '更明显地改写表达' },
    { id: 'paper_polish_enhance', title: '润色 + 降AI', desc: '先润色，再降低AI痕迹' },
  ];

  const featureOptions = [
    {
      id: 'full',
      title: '整篇提取优化',
      desc: '上传论文 DOCX，提取正文后整体优化。',
      icon: FileUp,
      tone: 'blue',
    },
    {
      id: 'aigc',
      title: 'AIGC片段优化',
      desc: '上传原文 DOCX 和 PaperPass、SpeedAI、维普检测报告，只优化检测出的疑似片段。',
      icon: FileSearch,
      tone: 'amber',
    },
  ];

  const formatPercent = (value) => (
    typeof value === 'number' ? `${value.toFixed(2)}%` : '--'
  );

  const formatMetricValue = (metric) => {
    if (metric?.format === 'number') {
      return typeof metric.value === 'number' ? metric.value.toLocaleString() : '--';
    }
    return formatPercent(metric?.value);
  };

  const getRiskBadgeClass = (level) => {
    if (level === 'high') return 'bg-red-50 text-red-700 border-red-100';
    if (level === 'medium') return 'bg-orange-50 text-orange-700 border-orange-100';
    if (level === 'low') return 'bg-violet-50 text-violet-700 border-violet-100';
    return 'bg-gray-50 text-gray-600 border-gray-100';
  };

  const getReportMetricCards = (report) => {
    const isSpeedAI = report?.report_type?.toLowerCase().includes('speedai');
    const isVip = report?.report_type?.includes('维普') || report?.report_type?.toLowerCase().includes('vip');
    const baseCards = [
      {
        label: '总体疑似度',
        value: report?.overall_suspicion,
        cardClass: 'bg-gray-50',
        valueClass: 'text-black',
        labelClass: 'text-gray-500',
      },
    ];

    if (isVip) {
      return [
        ...baseCards,
        {
          label: '疑似片段',
          value: report?.extracted_segment_count,
          format: 'number',
          cardClass: 'bg-violet-50',
          valueClass: 'text-violet-700',
          labelClass: 'text-violet-700/70',
        },
        {
          label: '论文字符数',
          value: report?.word_count,
          format: 'number',
          cardClass: 'bg-blue-50',
          valueClass: 'text-blue-700',
          labelClass: 'text-blue-700/70',
        },
      ];
    }

    if (isSpeedAI) {
      return [
        ...baseCards,
        {
          label: '高度占比',
          value: report?.high_ratio,
          cardClass: 'bg-red-50',
          valueClass: 'text-red-600',
          labelClass: 'text-red-600/70',
        },
        {
          label: '中度占比',
          value: report?.medium_ratio,
          cardClass: 'bg-orange-50',
          valueClass: 'text-orange-700',
          labelClass: 'text-orange-700/70',
        },
        {
          label: '轻度占比',
          value: report?.low_ratio,
          cardClass: 'bg-violet-50',
          valueClass: 'text-violet-700',
          labelClass: 'text-violet-700/70',
        },
      ];
    }

    return [
      ...baseCards,
      {
        label: '加权疑似度',
        value: report?.weighted_suspicion,
        cardClass: 'bg-blue-50',
        valueClass: 'text-blue-700',
        labelClass: 'text-blue-700/70',
      },
      {
        label: '中度占比',
        value: report?.medium_ratio,
        cardClass: 'bg-orange-50',
        valueClass: 'text-orange-700',
        labelClass: 'text-orange-700/70',
      },
      {
        label: '轻度占比',
        value: report?.low_ratio,
        cardClass: 'bg-violet-50',
        valueClass: 'text-violet-700',
        labelClass: 'text-violet-700/70',
      },
    ];
  };

  const getModeDescription = () => {
    if (processingMode === 'paper_polish') return '只做轻度润色，让句子更通顺自然。';
    if (processingMode === 'paper_enhance') return '直接进行重点降AI，适合已经润色过的内容。';
    return '先润色，再进行降AI处理，适合整篇论文稳妥优化。';
  };

  const getStageName = (stage) => {
    if (stage === 'polish') return '轻度润色';
    if (stage === 'enhance') return '重点降AI';
    return stage || '等待开始';
  };

  const renderHistoryList = (listClassName = 'space-y-3') => (
    <div className={listClassName}>
      {isLoadingSessions ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-6 h-6 border-2 border-ios-gray/30 border-t-ios-gray rounded-full animate-spin" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-16 space-y-3">
          <div className="w-12 h-12 bg-gray-50 rounded-lg flex items-center justify-center mx-auto text-gray-300">
            <History className="w-6 h-6" />
          </div>
          <p className="text-ios-gray text-sm">暂无会话记录</p>
        </div>
      ) : (
        sessions.map((session) => (
          <SessionItem
            key={session.id || session.session_id}
            session={session}
            activeSession={activeSession}
            onView={handleViewSession}
            onDelete={handleDeleteSession}
            onRetry={handleRetrySegment}
          />
        ))
      )}
    </div>
  );

  const renderActiveSessionCard = () => (
    <div
      role={currentActiveSessionData ? 'button' : undefined}
      tabIndex={currentActiveSessionData ? 0 : undefined}
      onClick={() => currentActiveSessionData && handleViewSession(currentActiveSessionData.session_id)}
      onKeyDown={(event) => {
        if (!currentActiveSessionData) {
          return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          handleViewSession(currentActiveSessionData.session_id);
        }
      }}
      title={currentActiveSessionData ? '查看当前任务详情' : undefined}
      className={`rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition-all ${
        currentActiveSessionData
          ? 'cursor-pointer hover:border-ios-blue/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-ios-blue/20'
          : ''
      }`}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[16px] font-semibold text-black flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${currentActiveSessionData ? 'bg-ios-blue animate-pulse' : 'bg-gray-300'}`} />
          当前任务
        </h2>
        {currentActiveSessionData ? (
          <span className="text-[12px] font-medium px-2 py-1 bg-blue-50 text-ios-blue rounded-md">
            查看详情
          </span>
        ) : (
          <span className="text-[12px] font-medium px-2 py-1 bg-gray-100 text-gray-500 rounded-md">
            空闲
          </span>
        )}
      </div>

      {currentActiveSessionData ? (
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-[13px] mb-2 font-medium">
              <span className="text-ios-gray">
                当前阶段：<span className="text-black">{getStageName(currentActiveSessionData.current_stage)}</span>
              </span>
              <span className="text-ios-blue">
                {Number(currentActiveSessionData.progress || 0).toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className="bg-ios-blue h-2 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${currentActiveSessionData.progress || 0}%` }}
              />
            </div>
          </div>

          <div className="flex justify-between items-center text-[13px]">
            <span className="text-ios-gray">
              进度：
              <span className="font-medium text-black">
                {(currentActiveSessionData.current_position || 0) + 1}
              </span>
              {' / '}
              {currentActiveSessionData.total_segments || 0} 段
            </span>

            {currentActiveSessionData.status === 'queued' && queueStatus?.your_position && (
              <div className="flex items-center gap-1.5 text-ios-orange">
                <Clock className="w-3.5 h-3.5" />
                <span>
                  排队第 {queueStatus.your_position} 位
                  (~{Math.ceil(queueStatus.estimated_wait_time / 60)}分)
                </span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-gray-50 px-4 py-8 text-center">
          <p className="text-[14px] font-medium text-gray-700">暂无运行中的任务</p>
          <p className="mt-1 text-[12px] text-gray-500">填写文本或上传 DOCX 后即可开始降 AIGC。</p>
        </div>
      )}
    </div>
  );


  return (
    <div className="min-h-screen bg-[#edf0f4] p-3 sm:p-5">
      <div className="mx-auto max-w-[1360px] min-h-[calc(100vh-24px)] sm:min-h-[calc(100vh-40px)] bg-white border border-gray-200 shadow-sm rounded-lg overflow-hidden flex flex-col">
        <header className="border-b border-gray-200 bg-white">
          <div className="min-h-[64px] flex flex-col gap-3 px-3 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-5">
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleSwitchView('aigc')}
                className={`h-10 px-4 rounded-md text-[15px] font-semibold transition-colors flex items-center gap-2 ${
                  activeView === 'aigc'
                    ? 'bg-black text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <FileText className="w-4 h-4" />
                降AIGC
              </button>
              <button
                onClick={() => handleSwitchView('history')}
                className={`h-10 px-4 rounded-md text-[15px] font-semibold transition-colors flex items-center gap-2 ${
                  activeView === 'history'
                    ? 'bg-black text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <History className="w-4 h-4" />
                历史记录
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              {queueStatus?.queue_length > 0 && (
                <div className="flex items-center gap-2 text-[13px]">
                  <div className="flex items-center gap-1.5 bg-orange-50 px-2.5 py-2 rounded-md">
                    <Clock className="w-3.5 h-3.5 text-ios-orange" />
                    <span className="text-ios-orange font-medium">
                      {queueStatus.queue_length} 排队
                    </span>
                  </div>
                </div>
              )}
              <button
                onClick={handleOpenAdmin}
                className={`h-10 px-4 rounded-md border text-[14px] font-semibold transition-colors flex items-center gap-2 ${
                  activeView === 'config'
                    ? 'border-black bg-black text-white'
                    : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                <Settings className="w-4 h-4" />
                管理配置
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 bg-[#f7f8fa] p-4 sm:p-6 overflow-y-auto">
          {activeView === 'aigc' ? (
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-5">
              <section className="space-y-5">
                <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <h1 className="text-[22px] font-semibold text-black tracking-tight">论文降AIGC</h1>
                      <p className="mt-1 text-[13px] text-gray-500">先选择功能入口，再上传 DOCX 或粘贴正文进行优化。</p>
                    </div>
                    <div className="rounded-md bg-blue-50 px-3 py-2 text-[13px] text-blue-700 flex items-start gap-2">
                      <Info className="w-4 h-4 mt-0.5 shrink-0" />
                      <span>{activeAigcFeature ? getModeDescription() : '请选择整篇提取优化或 AIGC 片段优化。'}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                  {activeAigcFeature ? (
                    <>
                      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <div className="text-[12px] font-medium text-gray-500">当前功能</div>
                          <h2 className="mt-1 text-[18px] font-semibold text-black">
                            {activeAigcFeature === 'full' ? '整篇提取优化' : 'AIGC片段优化'}
                          </h2>
                        </div>
                        <button
                          onClick={handleBackToAigcFeatures}
                          className="self-start sm:self-auto h-9 px-3 rounded-md border border-gray-200 bg-white text-[13px] font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                        >
                          切换功能
                        </button>
                      </div>

                  <div className="mb-5">
                    <label className="block text-[13px] font-medium text-gray-500 mb-2">
                      优化方式
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {modeOptions.map((mode) => (
                        <label
                          key={mode.id}
                          className={`flex items-start p-3.5 rounded-lg cursor-pointer transition-all border ${
                            mode.id === 'paper_polish_enhance' ? 'md:col-span-2' : ''
                          } ${
                            processingMode === mode.id
                              ? 'bg-blue-50 border-ios-blue ring-1 ring-ios-blue/20'
                              : 'bg-white border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="processingMode"
                            value={mode.id}
                            checked={processingMode === mode.id}
                            onChange={(e) => setProcessingMode(e.target.value)}
                            className="mr-3 mt-0.5 w-4 h-4 text-ios-blue focus:ring-ios-blue border-gray-300"
                          />
                          <div>
                            <div className={`font-semibold text-[14px] ${processingMode === mode.id ? 'text-ios-blue' : 'text-black'}`}>
                              {mode.title}
                            </div>
                            <div className="text-[12px] text-ios-gray mt-0.5">
                              {mode.desc}
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {activeAigcFeature === 'full' && (
                  <div className="mb-5 rounded-lg border border-blue-100 bg-blue-50/60 p-4 space-y-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-[15px] font-semibold text-ios-blue flex items-center gap-2">
                            <FileUp className="w-4 h-4" />
                            整篇提取优化
                          </h3>
                          <p className="text-[13px] text-gray-600 mt-1 leading-relaxed">
                            上传论文 DOCX 后，系统会提取正文，自动跳过摘要、目录、关键词、标题、图题和表题；提取后还可以下载标记版 DOCX。
                          </p>
                        </div>
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".docx"
                          onChange={handleWordFileChange}
                          className="hidden"
                        />
                      </div>

                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                        <div className="min-h-[44px] flex items-center rounded-lg bg-white/80 px-4 py-3 border border-white/80 lg:flex-1">
                          {selectedWordFile ? (
                            <div className="flex items-center justify-between w-full gap-3">
                              <div className="min-w-0">
                                <div className="text-[14px] font-medium text-black truncate">
                                  {selectedWordFile.name}
                                </div>
                                <div className="text-[12px] text-ios-gray mt-0.5">
                                  {(selectedWordFile.size / 1024 / 1024).toFixed(2)} MB
                                </div>
                              </div>
                              <button
                                onClick={resetWordFileInput}
                                className="p-1.5 rounded-md text-gray-400 hover:text-ios-red hover:bg-red-50 transition-colors"
                                title="移除文件"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          ) : (
                            <span className="text-[13px] text-ios-gray">仅支持上传 .docx 文件</span>
                          )}
                        </div>

                        <div className="flex gap-3">
                          <button
                            onClick={handlePickWordFile}
                            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-white text-black border border-gray-200 hover:bg-gray-50 transition-all text-[14px] font-medium"
                          >
                            <Upload className="w-4 h-4" />
                            选择 DOCX
                          </button>
                          <button
                            onClick={handleExtractWordBody}
                            disabled={!selectedWordFile || isExtractingWord}
                            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-ios-blue text-white disabled:bg-gray-300 disabled:cursor-not-allowed transition-all text-[14px] font-semibold"
                          >
                            {isExtractingWord ? (
                              <>
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                识别中...
                              </>
                            ) : (
                              <>
                                <FileText className="w-4 h-4" />
                                提取整篇内容
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {extractedDocResult && (
                        <div className="rounded-lg bg-white border border-white/90 p-4 space-y-3">
                          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                            <div className="space-y-1">
                              <div className="text-[14px] font-semibold text-black">
                                已提取 {extractedDocResult.paragraph_count} 个段落
                              </div>
                              <div className="text-[12px] text-ios-gray">
                                提取起始位置：{extractedDocResult.start_heading}
                              </div>
                              <div className="text-[12px] text-ios-gray">
                                  当前结果仅包含正文段落；摘要、关键词、标题、目录、图题和表题已过滤
                              </div>
                            </div>

                            <div className="flex flex-wrap gap-2">
                              <button
                                onClick={handleCopyExtractedText}
                                className="flex items-center gap-2 px-3 py-2 rounded-md bg-gray-100 hover:bg-gray-200 text-[13px] font-medium text-black transition-colors"
                              >
                                <Copy className="w-4 h-4" />
                                复制文本
                              </button>
                              <button
                                onClick={handleDownloadExtractedText}
                                className="flex items-center gap-2 px-3 py-2 rounded-md bg-gray-100 hover:bg-gray-200 text-[13px] font-medium text-black transition-colors"
                              >
                                <Download className="w-4 h-4" />
                                下载 TXT
                              </button>
                              <button
                                onClick={handleDownloadMarkedWord}
                                disabled={!selectedWordFile || isDownloadingMarkedWord}
                                className="flex items-center gap-2 px-3 py-2 rounded-md bg-blue-100 hover:bg-blue-200 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed text-[13px] font-medium text-ios-blue transition-colors"
                              >
                                {isDownloadingMarkedWord ? (
                                  <>
                                    <div className="w-4 h-4 border-2 border-ios-blue/30 border-t-ios-blue rounded-full animate-spin" />
                                    生成中...
                                  </>
                                ) : (
                                  <>
                                    <Download className="w-4 h-4" />
                                    下载标记 DOCX
                                  </>
                                )}
                              </button>
                              <button
                                onClick={handleClearExtractedResult}
                                className="flex items-center gap-2 px-3 py-2 rounded-md bg-red-50 hover:bg-red-100 text-[13px] font-medium text-ios-red transition-colors"
                              >
                                <X className="w-4 h-4" />
                                清空结果
                              </button>
                            </div>
                          </div>

                          <div className="rounded-md bg-gray-50 px-3 py-2 text-[12px] text-gray-600 leading-relaxed">
                            识别结果已经自动填入下面的输入框；下载标记版 DOCX 后，浅黄色段落就是本次实际提取到的正文，你可以据此核对遗漏内容。
                          </div>
                        </div>
                      )}
                  </div>
                  )}

                  {activeAigcFeature === 'aigc' && (
                  <div className="mb-5 rounded-lg border border-amber-100 bg-amber-50/50 p-4 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-[15px] font-semibold text-amber-700 flex items-center gap-2">
                          <FileSearch className="w-4 h-4" />
                          AIGC片段优化
                        </h3>
                        <p className="text-[13px] text-gray-600 mt-1 leading-relaxed">
                          先选择原始 DOCX，再选择对应的 PaperPass 或 SpeedAI PDF 检测报告；系统会把疑似片段填入下方文本框，只优化这些内容。
                        </p>
                      </div>
                      <input
                        ref={reportWordInputRef}
                        type="file"
                        accept=".docx"
                        onChange={handleReportWordFileChange}
                        className="hidden"
                      />
                      <input
                        ref={reportInputRef}
                        type="file"
                        accept=".pdf"
                        onChange={handleReportFileChange}
                        className="hidden"
                      />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      <div className="rounded-lg bg-white/80 p-3 border border-white/80">
                        <div className="text-[12px] font-semibold text-gray-500 mb-2">原始 DOCX</div>
                        <div className="min-h-[44px] flex items-center rounded-lg bg-white px-3 py-2 border border-gray-100">
                          {selectedReportWordFile ? (
                            <div className="flex items-center justify-between w-full gap-3">
                              <div className="min-w-0">
                                <div className="text-[14px] font-medium text-black truncate">
                                  {selectedReportWordFile.name}
                                </div>
                                <div className="text-[12px] text-ios-gray mt-0.5">
                                  {(selectedReportWordFile.size / 1024 / 1024).toFixed(2)} MB
                                </div>
                              </div>
                              <button
                                onClick={resetReportWordFileInput}
                                className="p-1.5 rounded-md text-gray-400 hover:text-ios-red hover:bg-red-50 transition-colors"
                                title="移除 DOCX"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          ) : (
                            <span className="text-[13px] text-ios-gray">仅支持上传 .docx 文件</span>
                          )}
                        </div>
                        <button
                          onClick={handlePickReportWordFile}
                          className="mt-3 w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white text-black border border-gray-200 hover:bg-gray-50 transition-all text-[14px] font-medium"
                        >
                          <Upload className="w-4 h-4" />
                          选择 DOCX
                        </button>
                      </div>

                      <div className="rounded-lg bg-white/80 p-3 border border-white/80">
                        <div className="text-[12px] font-semibold text-gray-500 mb-2">AIGC 检测报告 PDF</div>
                        <div className="min-h-[44px] flex items-center rounded-lg bg-white px-3 py-2 border border-gray-100">
                          {selectedReportFile ? (
                            <div className="flex items-center justify-between w-full gap-3">
                              <div className="min-w-0">
                                <div className="text-[14px] font-medium text-black truncate">
                                  {selectedReportFile.name}
                                </div>
                                <div className="text-[12px] text-ios-gray mt-0.5">
                                  {(selectedReportFile.size / 1024 / 1024).toFixed(2)} MB
                                </div>
                              </div>
                              <button
                                onClick={resetReportFileInput}
                                className="p-1.5 rounded-md text-gray-400 hover:text-ios-red hover:bg-red-50 transition-colors"
                                title="移除 PDF"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          ) : (
                            <span className="text-[13px] text-ios-gray">支持上传 PaperPass / SpeedAI .pdf 检测报告</span>
                          )}
                        </div>
                        <button
                          onClick={handlePickReportFile}
                          className="mt-3 w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white text-black border border-gray-200 hover:bg-gray-50 transition-all text-[14px] font-medium"
                        >
                          <Upload className="w-4 h-4" />
                          选择 PDF
                        </button>
                      </div>
                    </div>

                    <button
                      onClick={handleExtractAigcReport}
                      disabled={!selectedReportWordFile || !selectedReportFile || isExtractingReport}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-amber-600 text-white disabled:bg-gray-300 disabled:cursor-not-allowed transition-all text-[14px] font-semibold"
                    >
                      {isExtractingReport ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          提取中...
                        </>
                      ) : (
                        <>
                          <BarChart3 className="w-4 h-4" />
                          提取疑似片段
                        </>
                      )}
                    </button>

                    {aigcReportResult && (
                      <div className="rounded-lg bg-white border border-white/90 p-4 space-y-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div className="space-y-1">
                            <div className="text-[14px] font-semibold text-black">
                              {aigcReportResult.report_type} · {aigcReportResult.source_filename}
                            </div>
                            <div className="text-[12px] text-ios-gray">
                              报告编号：{aigcReportResult.report_id || '--'}
                            </div>
                            <div className="text-[12px] text-ios-gray">
                              论文题目：{aigcReportResult.title || '--'}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={handleDownloadReportMarkedWord}
                              disabled={!aigcSegmentResult?.extraction_token || isDownloadingReportMarkedWord}
                              className="self-start flex items-center gap-2 px-3 py-2 rounded-md bg-amber-100 hover:bg-amber-200 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed text-[13px] font-medium text-amber-700 transition-colors"
                            >
                              {isDownloadingReportMarkedWord ? (
                                <>
                                  <div className="w-4 h-4 border-2 border-amber-700/30 border-t-amber-700 rounded-full animate-spin" />
                                  生成中...
                                </>
                              ) : (
                                <>
                                  <Download className="w-4 h-4" />
                                  下载标记 DOCX
                                </>
                              )}
                            </button>
                            <button
                              onClick={handleClearAigcReport}
                              className="self-start flex items-center gap-2 px-3 py-2 rounded-md bg-red-50 hover:bg-red-100 text-[13px] font-medium text-ios-red transition-colors"
                            >
                              <X className="w-4 h-4" />
                              清空结果
                            </button>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                          {getReportMetricCards(aigcReportResult).map((metric) => (
                            <div key={metric.label} className={`rounded-md p-3 ${metric.cardClass}`}>
                              <div className={`text-[18px] font-semibold ${metric.valueClass}`}>
                                {formatMetricValue(metric)}
                              </div>
                              <div className={`text-[12px] ${metric.labelClass}`}>
                                {metric.label}
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="text-[13px] font-semibold text-black">
                              疑似片段 {aigcReportResult.extracted_segment_count || 0} / {aigcReportResult.fragment_count || '--'}
                            </div>
                            <div className="text-[12px] text-ios-gray">
                              已匹配 DOCX 段落 {aigcSegmentResult?.paragraph_count || 0} 个
                            </div>
                          </div>

                          {aigcReportResult.segments?.length > 0 ? (
                            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                              {aigcReportResult.segments.slice(0, 6).map((segment, index) => (
                                <div key={`${segment.page}-${index}`} className="rounded-md border border-gray-100 bg-gray-50 p-3">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <span className={`px-2 py-0.5 rounded border text-[12px] font-semibold ${getRiskBadgeClass(segment.risk_level)}`}>
                                      {segment.risk_label} AI {formatPercent(segment.ai_percent)}
                                    </span>
                                    <span className="text-[12px] text-ios-gray">第 {segment.page} 页</span>
                                  </div>
                                  <p className="text-[13px] text-gray-700 leading-relaxed line-clamp-3">
                                    {segment.text}
                                  </p>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="rounded-md bg-gray-50 px-3 py-2 text-[12px] text-gray-600">
                              已读取总体指标，但没有识别到正文页中的彩色疑似片段。
                            </div>
                          )}
                          <div className="rounded-md bg-amber-50 px-3 py-2 text-[12px] text-amber-700 leading-relaxed">
                            已将匹配到的 DOCX 段落填入下方文本框；下载标记版 DOCX 后，浅黄色段落就是本次实际优化并写回的位置。
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  )}

                  <div className="relative">
                    <textarea
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder="在此粘贴需要改写的论文正文..."
                      className="w-full h-72 px-4 py-3 bg-gray-50 rounded-lg focus:bg-white focus:ring-2 focus:ring-ios-blue/20 transition-all text-[16px] leading-relaxed text-black placeholder-gray-400 border border-gray-100 outline-none resize-none"
                    />
                    <div className="absolute bottom-3 right-3 text-[12px] text-ios-gray bg-white/90 px-2 py-1 rounded-md">
                      {text.length} 字
                    </div>
                  </div>

                  <div className="mt-5 flex justify-end">
                    <button
                      onClick={handleStartOptimization}
                      disabled={!text.trim() || activeSession || isSubmitting}
                      className="flex items-center gap-2 bg-ios-blue hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 px-8 rounded-lg transition-all active:scale-[0.98] shadow-sm text-[16px]"
                    >
                      {isSubmitting ? (
                        <>
                          <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          提交中...
                        </>
                      ) : (
                        <>
                          <Play className="w-5 h-5 fill-current" />
                          开始优化
                        </>
                      )}
                    </button>
                  </div>
                    </>
                  ) : (
                    <div className="space-y-5">
                      <div>
                        <h2 className="text-[18px] font-semibold text-black">选择要处理的内容</h2>
                        <p className="mt-1 text-[13px] text-gray-500">
                          选择一个入口后，再进行对应的上传、提取和优化。
                        </p>
                      </div>

                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {featureOptions.map((feature) => {
                          const FeatureIcon = feature.icon;
                          const isAmber = feature.tone === 'amber';
                          return (
                            <button
                              key={feature.id}
                              onClick={() => handleSelectAigcFeature(feature.id)}
                              className={`group text-left rounded-lg border bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-md ${
                                isAmber
                                  ? 'border-amber-100 hover:border-amber-300'
                                  : 'border-blue-100 hover:border-ios-blue/40'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-4">
                                <div className={`w-11 h-11 rounded-lg flex items-center justify-center ${
                                  isAmber ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-ios-blue'
                                }`}>
                                  <FeatureIcon className="w-5 h-5" />
                                </div>
                                <span className={`text-[12px] font-semibold px-2 py-1 rounded-md ${
                                  isAmber
                                    ? 'bg-amber-50 text-amber-700'
                                    : 'bg-blue-50 text-ios-blue'
                                }`}>
                                  进入
                                </span>
                              </div>
                              <h3 className="mt-4 text-[17px] font-semibold text-black">
                                {feature.title}
                              </h3>
                              <p className="mt-2 text-[13px] leading-relaxed text-gray-600">
                                {feature.desc}
                              </p>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </section>

              <aside className="space-y-5">
                {renderActiveSessionCard()}

                <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <History className="w-4 h-4 text-gray-500" />
                    <h2 className="text-[16px] font-semibold text-black">任务概览</h2>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-md bg-gray-50 p-3">
                      <div className="text-[20px] font-semibold text-black">{sessionStats.total}</div>
                      <div className="text-[12px] text-gray-500">全部记录</div>
                    </div>
                    <div className="rounded-md bg-blue-50 p-3">
                      <div className="text-[20px] font-semibold text-blue-700">{sessionStats.processing}</div>
                      <div className="text-[12px] text-blue-700/70">处理中</div>
                    </div>
                    <div className="rounded-md bg-emerald-50 p-3">
                      <div className="text-[20px] font-semibold text-emerald-700">{sessionStats.completed}</div>
                      <div className="text-[12px] text-emerald-700/70">已完成</div>
                    </div>
                    <div className="rounded-md bg-red-50 p-3">
                      <div className="text-[20px] font-semibold text-red-600">{sessionStats.failed}</div>
                      <div className="text-[12px] text-red-600/70">失败</div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleSwitchView('history')}
                    className="mt-4 w-full h-10 rounded-md border border-gray-200 bg-white text-[14px] font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    查看历史记录
                  </button>
                </div>
              </aside>
            </div>
          ) : activeView === 'history' ? (
            <section className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-100 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h1 className="text-[22px] font-semibold text-black tracking-tight">历史记录</h1>
                  <p className="mt-1 text-[13px] text-gray-500">查看、继续处理或删除已有降AIGC任务。</p>
                </div>
                <div className="flex items-center gap-2 text-[13px] text-gray-500">
                  <span>全部 {sessionStats.total}</span>
                  <span>已完成 {sessionStats.completed}</span>
                  <span>失败 {sessionStats.failed}</span>
                </div>
              </div>
              <div className="p-4 max-h-[calc(100vh-190px)] overflow-y-auto">
                {renderHistoryList('grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3')}
              </div>
            </section>
          ) : (
            <section className="space-y-5">
              <div className="rounded-lg border border-gray-200 bg-white px-5 py-4 shadow-sm">
                <h1 className="text-[22px] font-semibold text-black tracking-tight">管理配置</h1>
                <p className="mt-1 text-[13px] text-gray-500">配置润色、降AI模型和系统运行参数。</p>
              </div>
              <ConfigManager adminToken={LOCAL_ADMIN_TOKEN} />
            </section>
          )}
        </main>
      </div>
    </div>
  );
};

export default WorkspacePage;







