import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Activity,
  BarChart3,
  Clock,
  Database,
  FileText,
  Home,
  Loader2,
  Settings,
  Shield,
  TrendingUp,
} from 'lucide-react';
import ConfigManager from '../components/ConfigManager';
import SessionMonitor from '../components/SessionMonitor';

const LOCAL_ADMIN_TOKEN = 'local-admin';

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [adminToken] = useState(localStorage.getItem('adminToken') || LOCAL_ADMIN_TOKEN);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [statistics, setStatistics] = useState(null);
  const [loadingStats, setLoadingStats] = useState(false);

  useEffect(() => {
    localStorage.setItem('adminToken', adminToken);
  }, [adminToken]);

  useEffect(() => {
    fetchStatistics();
    const interval = setInterval(fetchStatistics, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatistics = async () => {
    setLoadingStats(true);
    try {
      const response = await axios.get('/api/admin/statistics', {
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      setStatistics(response.data);
    } catch (error) {
      console.error('Error fetching statistics:', error);
    } finally {
      setLoadingStats(false);
    }
  };

  const tabs = [
    { id: 'dashboard', label: '数据面板', icon: BarChart3, color: 'blue' },
    { id: 'sessions', label: '会话监控', icon: Activity, color: 'blue' },
    { id: 'config', label: '系统配置', icon: Settings, color: 'amber' },
  ];

  const tabClass = (tab) => {
    const active = activeTab === tab.id;
    const activeColors = {
      blue: 'bg-blue-600 text-white shadow-lg shadow-blue-500/25',
      amber: 'bg-amber-600 text-white shadow-lg shadow-amber-500/25',
    };
    const hoverColors = {
      blue: 'text-gray-600 hover:text-blue-600 hover:bg-blue-50',
      amber: 'text-gray-600 hover:text-amber-600 hover:bg-amber-50',
    };
    return `group relative flex items-center gap-2.5 px-6 py-3 rounded-xl font-semibold transition-all duration-200 ${
      active ? activeColors[tab.color] : `bg-white border border-gray-200 ${hoverColors[tab.color]}`
    }`;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield className="w-8 h-8 text-blue-600" />
              <h1 className="text-2xl font-bold text-gray-800">管理后台</h1>
            </div>
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 px-4 py-2 bg-gray-900 hover:bg-black text-white rounded-lg transition-colors"
            >
              <Home className="w-5 h-5" />
              返回首页
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-2 overflow-x-auto py-3">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={tabClass(tab)}
                >
                  <Icon className="w-5 h-5" />
                  <span className="whitespace-nowrap">{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'dashboard' && (
          <section className="space-y-6">
            {loadingStats && !statistics ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : statistics ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-500 mb-1">总会话数</p>
                        <p className="text-3xl font-bold text-gray-900 tracking-tight">{statistics.sessions.total}</p>
                        <span className="inline-flex mt-2 text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
                          {statistics.sessions.today} 今日
                        </span>
                      </div>
                      <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                        <Database className="w-6 h-6 text-blue-600" />
                      </div>
                    </div>
                  </div>

                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-500 mb-1">处理字符数</p>
                        <p className="text-3xl font-bold text-gray-900 tracking-tight">
                          {statistics.processing.total_chars_processed.toLocaleString()}
                        </p>
                        <span className="inline-flex mt-2 text-xs font-medium text-gray-500 bg-gray-50 px-2 py-0.5 rounded-full">
                          累计
                        </span>
                      </div>
                      <div className="w-12 h-12 bg-sky-50 rounded-xl flex items-center justify-center">
                        <BarChart3 className="w-6 h-6 text-sky-600" />
                      </div>
                    </div>
                  </div>

                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-500 mb-1">处理耗时</p>
                        <p className="text-3xl font-bold text-gray-900 tracking-tight">
                          {Math.round(statistics.processing.avg_processing_time)}
                          <span className="text-sm font-normal text-gray-500 ml-1">秒</span>
                        </p>
                        <span className="inline-flex mt-2 text-xs font-medium text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full">
                          平均
                        </span>
                      </div>
                      <div className="w-12 h-12 bg-orange-50 rounded-xl flex items-center justify-center">
                        <Clock className="w-6 h-6 text-orange-600" />
                      </div>
                    </div>
                  </div>

                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-500 mb-1">失败会话</p>
                        <p className="text-3xl font-bold text-gray-900 tracking-tight">{statistics.sessions.failed}</p>
                        <span className="inline-flex mt-2 text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                          完成 {statistics.sessions.completed}
                        </span>
                      </div>
                      <div className="w-12 h-12 bg-emerald-50 rounded-xl flex items-center justify-center">
                        <Activity className="w-6 h-6 text-emerald-600" />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-10 h-10 bg-teal-50 rounded-lg flex items-center justify-center">
                        <FileText className="w-5 h-5 text-teal-600" />
                      </div>
                      <span className="text-xs font-medium text-gray-400">计数</span>
                    </div>
                    <p className="text-sm font-medium text-gray-500 mb-1">轻度润色</p>
                    <p className="text-2xl font-bold text-gray-900 tracking-tight">
                      {statistics.processing.paper_polish_count}
                    </p>
                  </div>

                  <div className="bg-white rounded-2xl shadow-ios p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-10 h-10 bg-rose-50 rounded-lg flex items-center justify-center">
                        <TrendingUp className="w-5 h-5 text-rose-600" />
                      </div>
                      <span className="text-xs font-medium text-gray-400">计数</span>
                    </div>
                    <p className="text-sm font-medium text-gray-500 mb-1">润色 + 降AI</p>
                    <p className="text-2xl font-bold text-gray-900 tracking-tight">
                      {statistics.processing.paper_polish_enhance_count}
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-white rounded-2xl shadow-ios p-10 text-center text-gray-500">
                暂无统计数据
              </div>
            )}
          </section>
        )}

        {activeTab === 'sessions' && <SessionMonitor adminToken={adminToken} />}
        {activeTab === 'config' && <ConfigManager adminToken={adminToken} />}
      </div>
    </div>
  );
};

export default AdminDashboard;
