import type { RiskLevel } from '@/types';

// 风险徽章
export function RiskBadge({ level }: { level: RiskLevel }) {
  const colors: Record<RiskLevel, string> = {
    low: 'bg-green-100 text-green-700 border-green-200',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    medium_high: 'bg-orange-100 text-orange-700 border-orange-200',
    high: 'bg-red-100 text-red-700 border-red-200',
    critical: 'bg-red-200 text-red-800 border-red-300',
  };
  const labels: Record<RiskLevel, string> = {
    low: '低风险',
    medium: '中风险',
    medium_high: '中高风险',
    high: '高风险',
    critical: '严重风险',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colors[level]}`}>
      {labels[level]}
    </span>
  );
}

// 统计卡片
export function StatCard({
  title, value, unit = '', trend, color = 'text-gray-900', onClick,
}: {
  title: string;
  value: string | number;
  unit?: string;
  trend?: string;
  color?: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 p-5 transition-shadow ${
        onClick ? 'hover:shadow-md cursor-pointer hover:border-primary/40' : 'hover:shadow-md'
      }`}
      onClick={onClick}
      {...(onClick ? { role: 'button', tabIndex: 0, onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } } } : {})}
    >
      <p className="text-sm text-gray-500 mb-1">{title}</p>
      <p className={`text-2xl font-bold ${color}`}>
        {value}{unit && <span className="text-sm font-normal ml-1">{unit}</span>}
      </p>
      {trend && <p className="text-xs text-gray-400 mt-1">{trend}</p>}
    </div>
  );
}

// 加载中
export function LoadingSpinner({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-400">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mb-3" />
      <span className="text-sm">{text}</span>
    </div>
  );
}

// 空状态
export function EmptyState({ text = '暂无数据', action }: { text?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-400">
      <svg className="w-16 h-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
      <span className="text-sm">{text}</span>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

// 表格横向滚动容器：窄屏下统一横向滚动，避免表格挤压变形
export function TableContainer({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      {children}
    </div>
  );
}
