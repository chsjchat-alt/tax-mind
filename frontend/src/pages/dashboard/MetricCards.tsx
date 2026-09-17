/**
 * 驾驶舱核心指标卡片（可点击跳转）
 */
import { useNavigate } from 'react-router-dom';
import { Progress } from 'antd';
import {
  RightOutlined, SafetyCertificateOutlined, SwapOutlined,
  CheckSquareOutlined,
} from '@ant-design/icons';
import { RISK_COLORS, RISK_LABELS } from '@/types';
import type { RiskLevel } from '@/types';

interface MetricCardsProps {
  adjustedRiskLevel: RiskLevel;
  adjustedRiskScore: number;
  /** 原始风险评分（整改前口径，用于双栏展示） */
  originalRiskScore?: number;
  fourFlowMatchScore: number;
  pendingTasks: number;
}

/** 可点击卡片通用交互（键盘可达） */
function cardProps(navigate: ReturnType<typeof useNavigate>, path: string) {
  return {
    onClick: () => navigate(path),
    role: 'button' as const,
    tabIndex: 0,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        navigate(path);
      }
    },
  };
}

export default function MetricCards({
  adjustedRiskLevel, adjustedRiskScore, originalRiskScore, fourFlowMatchScore,
  pendingTasks,
}: MetricCardsProps) {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      {/* 卡片1：总体风险等级 → 风险地图 */}
      <div
        className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md cursor-pointer hover:border-primary/40 transition-all"
        {...cardProps(navigate, '/risk-map')}
      >
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-gray-500">总体风险等级</p>
          <RightOutlined className="text-gray-300 text-xs" />
        </div>
        <div className="flex items-center gap-3">
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{ backgroundColor: RISK_COLORS[adjustedRiskLevel] + '18' }}
          >
            <SafetyCertificateOutlined
              style={{ fontSize: 22, color: RISK_COLORS[adjustedRiskLevel] }}
            />
          </div>
          <div>
            <p className="text-xl font-bold" style={{ color: RISK_COLORS[adjustedRiskLevel] }}>
              {RISK_LABELS[adjustedRiskLevel]}
            </p>
            <p className="text-xs text-gray-400">{adjustedRiskScore.toFixed(0)} 分</p>
            {/* 双栏：原始分 / 整改后分（统一收口口径，缺失或相同时隐藏） */}
            {originalRiskScore != null && Math.round(originalRiskScore) !== Math.round(adjustedRiskScore) && (
              <p className="text-[10px] text-gray-400 mt-0.5">
                原始分 {Math.round(originalRiskScore)} → 整改后 {Math.round(adjustedRiskScore)}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* 卡片2：四流匹配度 → 风险地图 */}
      <div
        className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md cursor-pointer hover:border-primary/40 transition-all"
        {...cardProps(navigate, '/risk-map')}
      >
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-gray-500">四流匹配度</p>
          <RightOutlined className="text-gray-300 text-xs" />
        </div>
        <div className="flex items-center gap-3">
          <SwapOutlined
            className="text-xl"
            style={{
              color: fourFlowMatchScore >= 85 ? RISK_COLORS.low :
                     fourFlowMatchScore >= 55 ? RISK_COLORS.medium_high :
                     fourFlowMatchScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.high,
            }}
          />
          <div>
            <p className="text-xl font-bold">
              {Math.round(fourFlowMatchScore)}
              <span className="text-sm font-normal text-gray-400">%</span>
            </p>
            <Progress
              percent={Math.round(fourFlowMatchScore)}
              size="small"
              strokeColor={
                fourFlowMatchScore >= 85 ? RISK_COLORS.low :
                fourFlowMatchScore >= 55 ? RISK_COLORS.medium_high :
                fourFlowMatchScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.high
              }
              showInfo={false}
              style={{ width: 100 }}
            />
          </div>
        </div>
      </div>

      {/* 卡片4：待办整改任务 → 整改追踪 */}
      <div
        className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md cursor-pointer hover:border-primary/40 transition-all"
        {...cardProps(navigate, '/remediation')}
      >
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-gray-500">待办整改任务</p>
          <RightOutlined className="text-gray-300 text-xs" />
        </div>
        <div className="flex items-center gap-3">
          <CheckSquareOutlined
            className="text-xl"
            style={{ color: pendingTasks > 0 ? RISK_COLORS.medium : RISK_COLORS.low }}
          />
          <div>
            <p className="text-xl font-bold">{pendingTasks}</p>
            <p className="text-xs text-gray-400">
              {pendingTasks > 0 ? '有待处理任务' : '暂无待办'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
