import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Map,
  Brain,
  FlaskConical,
  Shield,
  ClipboardCheck,
  FileText,
} from 'lucide-react'

const menuItems = [
  { path: '/dashboard', label: '数据驾驶舱', icon: LayoutDashboard },
  { path: '/risk-map', label: '风险地图', icon: Map },
  { path: '/profile', label: '心理画像', icon: Brain },
  { path: '/simulator', label: '风险模拟', icon: FlaskConical },
  { path: '/compliance', label: '合规导航', icon: Shield },
  { path: '/remediation', label: '整改追踪', icon: ClipboardCheck },
  { path: '/reports', label: '报告中心', icon: FileText },
]

function Sidebar() {
  return (
    <aside className="w-60 bg-white border-r border-gray-200 flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-200">
        <span className="text-lg font-bold text-primary">税智·心判</span>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-4 overflow-y-auto">
        <ul className="space-y-1 px-3">
          {menuItems.map(({ path, label, icon: Icon }) => (
            <li key={path}>
              <NavLink
                to={path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`
                }
              >
                <Icon size={18} />
                <span>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* 底部版本信息 */}
      <div className="px-6 py-3 border-t border-gray-200 text-xs text-gray-400">
        v0.1.0 · 原型阶段
      </div>
    </aside>
  )
}

export default Sidebar
