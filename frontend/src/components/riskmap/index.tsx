import { useState } from 'react';
import { Tooltip, Progress } from 'antd';
import {
  CaretDownOutlined, CaretUpOutlined,
  InfoCircleOutlined, EyeOutlined, FileTextOutlined,
} from '@ant-design/icons';
import { RISK_COLORS, RISK_LABELS } from '@/types';
import type { RiskLevel } from '@/types';

// ═══════════════════════════════════════
// RiskLegend - 风险图例说明
// ═══════════════════════════════════════
export function RiskLegend() {
  const items: { level: RiskLevel; threshold: string; desc: string }[] = [
    { level: 'high', threshold: '≥ 70', desc: '需立即关注，存在较高的税务稽查风险' },
    { level: 'medium', threshold: '40-69', desc: '建议优化，部分环节存在合规改进空间' },
    { level: 'low', threshold: '< 40', desc: '当前健康，各项指标在合理范围内' },
  ];

  return (
    <div className="flex flex-wrap items-center gap-4">
      <span className="text-xs text-gray-400 mr-1">图例：</span>
      {items.map(({ level, threshold, desc }) => (
        <Tooltip key={level} title={desc}>
          <div className="flex items-center gap-1.5 cursor-help">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: RISK_COLORS[level] }}
            />
            <span className="text-xs font-medium" style={{ color: RISK_COLORS[level] }}>
              {RISK_LABELS[level]}
            </span>
            <span className="text-xs text-gray-400">{threshold}</span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════
// LanguageToggle - 双轨语言切换
// ═══════════════════════════════════════
export type Language = 'business' | 'technical';

interface LanguageToggleProps {
  value: Language;
  onChange: (v: Language) => void;
}

export function LanguageToggle({ value, onChange }: LanguageToggleProps) {
  return (
    <div className="inline-flex bg-gray-100 rounded-lg p-0.5">
      <button
        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
          value === 'business'
            ? 'bg-white text-gray-800 shadow-sm'
            : 'text-gray-500 hover:text-gray-700'
        }`}
        onClick={() => onChange('business')}
      >
        <EyeOutlined className="mr-1" />
        老板视角
      </button>
      <button
        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
          value === 'technical'
            ? 'bg-white text-primary shadow-sm'
            : 'text-gray-500 hover:text-gray-700'
        }`}
        onClick={() => onChange('technical')}
      >
        <InfoCircleOutlined className="mr-1" />
        财务视角
      </button>
    </div>
  );
}

// ═══════════════════════════════════════
// RiskMapCard - 单个风险维度卡片
// ═══════════════════════════════════════
interface RiskMapCardProps {
  dimKey: string;
  dimName: string;
  score: number;
  level: RiskLevel;
  detail: string;
  technicalDetail: string;
  language: Language;
  isCritical?: boolean;
  riskReason?: string;
  policyRef?: string;
  policyBasis?: string;
}

export function RiskMapCard({
  dimName, score, level, detail, technicalDetail, language, isCritical = false,
  riskReason, policyRef, policyBasis,
}: RiskMapCardProps) {
  const [expanded, setExpanded] = useState(false);
  const color = RISK_COLORS[level];
  const label = RISK_LABELS[level];

  // 根据语言切换显示内容
  const displayText = language === 'business' ? detail : technicalDetail;
  const altText = language === 'business' ? technicalDetail : detail;
  const altLabel = language === 'business' ? '财务视角描述' : '老板视角描述';

  return (
    <div
      className={`
        bg-white rounded-xl border border-gray-200 p-4 transition-all duration-300
        ${expanded ? 'shadow-lg ring-1 ring-primary/20' : 'hover:shadow-md'}
        ${isCritical ? 'border-l-red-500' : ''}
        cursor-pointer select-none
      `}
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
      onClick={() => setExpanded(!expanded)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(!expanded); } }}
    >
      {/* 高压整体预警标记 */}
      {isCritical && (
        <div className="flex items-center gap-1.5 mb-3 -mt-1">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] text-red-500 font-medium">高危预警</span>
        </div>
      )}

      {/* 头部：维度名 + 风险圆点 + 展开箭头 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* 红/黄/绿圆点 — 始终使用维度自身等级颜色 */}
          <Tooltip title={`${label} - ${score}分`}>
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />
          </Tooltip>
          <h4 className="text-sm font-semibold truncate text-gray-700">
            {dimName}
          </h4>
          <span
            className="text-xs font-bold px-1.5 py-0.5 rounded-full shrink-0"
            style={{ backgroundColor: color + '18', color }}
          >
            {score}分
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Tooltip title={altText}>
            <InfoCircleOutlined
              className="text-xs text-gray-300 hover:text-primary transition-colors"
              onClick={(e) => e.stopPropagation()}
            />
          </Tooltip>
          {expanded
            ? <CaretUpOutlined className="text-xs text-gray-400" />
            : <CaretDownOutlined className="text-xs text-gray-400" />
          }
        </div>
      </div>

      {/* 进度条 — 始终使用维度自身等级颜色 */}
      <div onClick={(e) => e.stopPropagation()}>
        <Progress
          percent={score}
          strokeColor={color}
          showInfo={false}
          size="small"
          trailColor="#f1f5f9"
        />
      </div>

      {/* 当前语言描述 */}
      <p className="text-xs mt-2 leading-relaxed line-clamp-3 text-gray-600">
        {displayText || '暂无描述'}
      </p>

      {/* 展开后：显示另一语言描述 */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-100 animate-fadeIn">
          <p className="text-[10px] text-gray-400 mb-1">{altLabel}</p>
          <p className="text-xs leading-relaxed text-gray-500">
            {altText || '暂无描述'}
          </p>
        </div>
      )}

      {/* 政策依据折叠面板（后端 risk_engine 返回 policy_ref / risk_reason / policy_basis） */}
      {policyBasis && (
        <details
          className="mt-3 rounded-lg bg-slate-50/70 border border-slate-100 group"
          onClick={(e) => e.stopPropagation()}
        >
          <summary className="cursor-pointer text-[11px] font-medium text-slate-600 hover:text-slate-800 transition-colors select-none px-2.5 py-2 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5">
              <FileTextOutlined className="text-slate-400" />
              政策依据
            </span>
            <span className="text-[10px] text-slate-400 truncate">{policyRef}</span>
          </summary>
          <div className="px-2.5 pb-2.5">
            {riskReason && (
              <p className="text-[11px] leading-relaxed text-gray-600 mb-2">
                <span className="font-medium text-gray-500">风险成因：</span>
                {riskReason}
              </p>
            )}
            <p className="text-[11px] leading-relaxed text-gray-500">
              {policyBasis}
            </p>
          </div>
        </details>
      )}

      {/* 底部提示 */}
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[10px] text-gray-400">
          {expanded ? '点击收起' : '点击展开更多'}
        </span>
        <span className="text-[10px] font-medium" style={{ color }}>
          {label}
        </span>
      </div>
    </div>
  );
}
