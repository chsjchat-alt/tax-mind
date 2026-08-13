import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

function MainLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 左侧固定侧边栏 */}
      <Sidebar />

      {/* 右侧主区域 */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* 顶部Header */}
        <Header />

        {/* 主内容区域 */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default MainLayout
