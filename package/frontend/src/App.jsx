import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import WorkspacePage from './pages/WorkspacePage';
import SessionDetailPage from './pages/SessionDetailPage';
import AdminDashboard from './pages/AdminDashboard';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: {
            background: '#363636',
            color: '#fff',
          },
          success: {
            duration: 3000,
            iconTheme: {
              primary: '#10B981',
              secondary: '#fff',
            },
          },
          error: {
            duration: 4000,
            iconTheme: {
              primary: '#EF4444',
              secondary: '#fff',
            },
          },
        }}
      />
      
      <Routes>
        <Route path="/" element={<WorkspacePage />} />
        <Route path="/access/:cardKey" element={<Navigate to="/" replace />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/workspace" element={<Navigate to="/" replace />} />
        <Route path="/session/:sessionId" element={<SessionDetailPage />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
