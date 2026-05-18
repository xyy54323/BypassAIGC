import axios from 'axios';

// API 基础路径配置
// 开发环境和生产环境都使用 /api 前缀
// 后端路由在 main.py 中以 /api 为前缀注册
const getBaseURL = () => {
  return '/api';
};

const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000, // 默认30秒超时，各端点可单独覆盖
});

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Prompts API
export const promptsAPI = {
  getSystemPrompts: () => api.get('/prompts/system'),
  getUserPrompts: (stage = null) =>
    api.get('/prompts/', {
      params: stage ? { stage } : {},
    }),
  createPrompt: (data) => api.post('/prompts/', data),
  updatePrompt: (promptId, data) => api.put(`/prompts/${promptId}`, data),
  deletePrompt: (promptId) => api.delete(`/prompts/${promptId}`),
  setDefaultPrompt: (promptId) =>
    api.post(`/prompts/${promptId}/set-default`),
};

// Optimization API
export const optimizationAPI = {
  startOptimization: (data) => api.post('/optimization/start', data, {
    timeout: 60000, // 启动任务延长到60秒超时
  }),
  extractWordBody: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/optimization/extract-docx-body', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  extractAigcReport: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/optimization/extract-aigc-report', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  extractAigcSegments: (wordFile, reportFile) => {
    const formData = new FormData();
    formData.append('word_file', wordFile);
    formData.append('report_file', reportFile);
    return api.post('/optimization/extract-aigc-segments', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },
  downloadMarkedExtractedWord: (extractionToken) =>
    api.post('/optimization/mark-extracted-word', {
      extraction_token: extractionToken,
    }, {
      timeout: 120000,
      responseType: 'blob',
    }),
  downloadMarkedWord: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/optimization/mark-docx-body', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      responseType: 'blob',
    });
  },
  getQueueStatus: (sessionId = null) =>
    api.get('/optimization/status', {
      params: sessionId ? { session_id: sessionId } : {},
      timeout: 10000, // 10秒超时
    }),
  listSessions: () => api.get('/optimization/sessions', {
    timeout: 15000, // 15秒超时
  }),
  getSessionDetail: (sessionId) =>
    api.get(`/optimization/sessions/${sessionId}`, {
      timeout: 20000, // 20秒超时
    }),
  getSessionProgress: (sessionId) =>
    api.get(`/optimization/sessions/${sessionId}/progress`, {
      timeout: 10000, // 10秒超时
    }),
  getSessionChanges: (sessionId) =>
    api.get(`/optimization/sessions/${sessionId}/changes`, {
      timeout: 20000, // 20秒超时
    }),
  stopSession: (sessionId) =>
    api.post(`/optimization/sessions/${sessionId}/stop`, null, {
      timeout: 10000, // 10秒超时
    }),
  exportSession: (sessionId, confirmation) =>
    api.post(`/optimization/sessions/${sessionId}/export`, confirmation, {
      timeout: 120000,
      responseType: 'blob',
    }),
  deleteSession: (sessionId) =>
    api.delete(`/optimization/sessions/${sessionId}`, {
      timeout: 10000, // 10秒超时
    }),
  retryFailedSegments: (sessionId) =>
    api.post(`/optimization/sessions/${sessionId}/retry`, null, {
      timeout: 15000, // 15秒超时
    }),
  getStreamUrl: (sessionId) => {
    const baseUrl = api.defaults.baseURL || '/api';
    return `${baseUrl}/optimization/sessions/${sessionId}/stream`;
  },
};

// Health API
export const healthAPI = {
  checkModels: () => api.get('/health/models', {
    timeout: 15000, // 15秒超时
  }),
};

export default api;



