import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { Spin, App as AntApp } from 'antd'

// 页面组件（懒加载）
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const RiskMap = lazy(() => import('@/pages/RiskMap'))
const Simulator = lazy(() => import('@/pages/Simulator'))
const Compliance = lazy(() => import('@/pages/Compliance'))
const Remediation = lazy(() => import('@/pages/Remediation'))
const Reports = lazy(() => import('@/pages/Reports'))
const Login = lazy(() => import('@/pages/Login'))

import { useAuthStore } from '@/store/authStore'

// 加载中组件
function PageLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Spin size="large" />
    </div>
  );
}

// 路由守卫：未登录重定向到登录页
function ProtectedRoutes() {
  const token = useAuthStore((s) => s.token);
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return (
    <MainLayout />
  );
}

function App() {
  return (
    <AntApp>
      <Suspense fallback={<PageLoading />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoutes />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="risk-map" element={<RiskMap />} />
            <Route path="simulator" element={<Simulator />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="remediation" element={<Remediation />} />
            <Route path="reports" element={<Reports />} />
          </Route>
        </Routes>
      </Suspense>
    </AntApp>
  )
}

export default App
