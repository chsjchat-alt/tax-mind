import { useEffect } from 'react';
import { Building2, LogOut } from 'lucide-react';
import { Select, Spin, Button } from 'antd';
import { useEnterpriseStore } from '@/store';
import { useAuthStore } from '@/store/authStore';

function Header() {
  const {
    enterprises, currentEnterprise,
    listLoading, detailLoading, error,
    fetchEnterprises, selectEnterprise,
  } = useEnterpriseStore();
  const { username, logout } = useAuthStore();

  useEffect(() => {
    fetchEnterprises();
  }, [fetchEnterprises]);

  const options = enterprises.map((e) => ({
    value: e.id,
    label: `${e.name} · ${e.industry}`,
    riskLevel: e.risk_level,
  }));

  // 区分错误态与空数据，避免接口失败被误呈现为"暂无企业数据"
  const notFoundContent = error
    ? (
      <span
        className="text-xs text-red-500 cursor-pointer"
        onClick={(e) => { e.stopPropagation(); fetchEnterprises(); }}
      >
        加载失败，点击重试
      </span>
    )
    : '暂无企业数据';

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-2">
        <h1 className="text-base font-semibold text-gray-800">
          中小民企财税合规决策支持系统
        </h1>
        {currentEnterprise && (
          <span className="text-xs text-gray-400 ml-2">
            | {currentEnterprise.industry} · {currentEnterprise.employee_count}人
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Building2 size={16} className="text-gray-400" />
        {/* 仅列表加载时展示 Spin；切换企业（详情加载）保持选择器常驻 */}
        {listLoading ? (
          <Spin size="small" />
        ) : (
          <Select
            style={{ width: 260 }}
            placeholder="选择企业"
            value={currentEnterprise?.id ?? undefined}
            onChange={(id) => selectEnterprise(id)}
            options={options}
            showSearch
            loading={detailLoading}
            disabled={detailLoading}
            filterOption={(input, option) =>
              (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
            }
            notFoundContent={notFoundContent}
          />
        )}
        {username && (
          <>
            <span className="text-xs text-gray-500">{username}</span>
            <Button
              type="text"
              size="small"
              icon={<LogOut size={14} />}
              onClick={logout}
              title="退出登录"
            />
          </>
        )}
      </div>
    </header>
  );
}

export default Header;
