/**
 * SSF 博弈状态四象限定位图
 *
 * 基于滑坡框架（Slippery Slope Framework）的二维可视化：
 *   X 轴 = 信任程度（对税务机关的尊重信任）
 *   Y 轴 = 权力感知（对税务机关执法能力的感知）
 *
 * 四个象限：
 *   Q1 (右上) 合法合规 — Nudge 维持
 *   Q2 (左上) 博弈对抗 — Budge 松动
 *   Q3 (左下) 放弃合规 — Trudge 跋涉
 *   Q4 (右下) 自愿遵从 — Nudge 强化
 */
import { useMemo, useState, useEffect, useCallback } from 'react';
import { Card, Tag, Tooltip, Spin, Empty, Segmented } from 'antd';
import {
  AimOutlined, ThunderboltOutlined, HeartOutlined,
  AlertOutlined, WarningOutlined,
} from '@ant-design/icons';
import type { SSFState, SSFHistoryPoint, SSFEnterprisePoint } from '@/types';
import { ssfApi } from '@/api';

// ── 象限配置 ──
const QUADRANTS = [
  {
    key: 'II', label: '博弈对抗', x: 50, y: 0, w: 50, h: 50,
    bgColor: '#FEF3C7', borderColor: '#F59E0B', textColor: '#92400E',
    icon: <WarningOutlined />, strategy: 'Budge 攻击性松动',
  },
  {
    key: 'I', label: '合法合规', x: 50, y: 0, w: 50, h: 50,
    bgColor: '#D1FAE5', borderColor: '#10B981', textColor: '#065F46',
    icon: <AimOutlined />, strategy: 'Nudge 助推维持',
  },
  {
    key: 'III', label: '放弃合规', x: 0, y: 50, w: 50, h: 50,
    bgColor: '#FEE2E2', borderColor: '#EF4444', textColor: '#991B1B',
    icon: <AlertOutlined />, strategy: 'Trudge 救助跋涉',
  },
  {
    key: 'IV', label: '自愿遵从', x: 50, y: 50, w: 50, h: 50,
    bgColor: '#DBEAFE', borderColor: '#3B82F6', textColor: '#1E40AF',
    icon: <HeartOutlined />, strategy: 'Nudge 强化权力',
  },
];

// SVG 配置
const SVG_SIZE = 360;
const PADDING = 40;
const PLOT_SIZE = SVG_SIZE - PADDING * 2;
const CENTER = PADDING + PLOT_SIZE / 2;

// 坐标转换
const toSvgX = (coord: number) => PADDING + (coord / 100) * PLOT_SIZE;
const toSvgY = (coord: number) => PADDING + PLOT_SIZE - (coord / 100) * PLOT_SIZE;

// ── 象限标注位置 ──
const Q_LABELS = [
  { key: 'I', x: toSvgX(75), y: toSvgY(85) },
  { key: 'II', x: toSvgX(25), y: toSvgY(85) },
  { key: 'III', x: toSvgX(25), y: toSvgY(15) },
  { key: 'IV', x: toSvgX(75), y: toSvgY(15) },
];

const NPT_LABELS: Record<string, { label: string; color: string }> = {
  nudge: { label: 'Nudge 助推', color: '#10B981' },
  budge: { label: 'Budge 松动', color: '#F59E0B' },
  trudge: { label: 'Trudge 跋涉', color: '#EF4444' },
};

interface SSFQuadrantChartProps {
  enterpriseId?: string;
  /** 从外部传入数据可跳过 API 请求 */
  ssfState?: SSFState | null;
  history?: SSFHistoryPoint[];
  /** 所有企业散点（用于对比视图） */
  allEnterprises?: SSFEnterprisePoint[];
  /** 是否显示全部企业散点 */
  showAllEnterprises?: boolean;
  /** 紧凑模式 */
  compact?: boolean;
  onStateLoaded?: (state: SSFState) => void;
}

export default function SSFQuadrantChart({
  enterpriseId,
  ssfState: externalState,
  history: externalHistory,
  allEnterprises: externalEnterprises,
  showAllEnterprises: externalShowAll,
  compact = false,
  onStateLoaded,
}: SSFQuadrantChartProps) {
  const [loading, setLoading] = useState(false);
  const [ssfState, setSsfState] = useState<SSFState | null>(externalState ?? null);
  const [history, setHistory] = useState<SSFHistoryPoint[]>(externalHistory ?? []);
  const [allEnterprises, setAllEnterprises] = useState<SSFEnterprisePoint[]>(externalEnterprises ?? []);
  const [showAll, setShowAll] = useState(externalShowAll ?? false);

  // ── 加载 SSF 数据 ──
  const loadSSF = useCallback(async () => {
    if (!enterpriseId) return;
    if (externalState) {
      setSsfState(externalState);
      setHistory(externalHistory ?? []);
      return;
    }
    setLoading(true);
    try {
      // 独立请求，任一失败不影响另一个
      const statePromise = ssfApi.getState(enterpriseId).then((res) => {
        const state = res.data.data?.current_state;
        if (state) {
          setSsfState(state);
          setHistory(res.data.data?.history ?? []);
          onStateLoaded?.(state);
        }
      }).catch(() => {});

      const summaryPromise = ssfApi.getSummary().then((res) => {
        const ents = res.data.data?.enterprises;
        if (ents) setAllEnterprises(ents);
      }).catch(() => {});

      await Promise.allSettled([statePromise, summaryPromise]);
    } finally {
      setLoading(false);
    }
  }, [enterpriseId, externalState, externalHistory, onStateLoaded]);

  useEffect(() => {
    loadSSF();
  }, [loadSSF]);

  // ── 当前企业数据点 ──
  const currentPoint = useMemo(() => {
    if (!ssfState) return null;
    return {
      x: toSvgX(ssfState.trust_coord),
      y: toSvgY(ssfState.power_coord),
      color: ssfState.quadrant_color,
      name: ssfState.enterprise_name,
      quadrant: ssfState.quadrant_name,
    };
  }, [ssfState]);

  // ── 历史轨迹线 ──
  const trajectoryPoints = useMemo(() => {
    if (history.length < 2) return '';
    const pts = history.map((h) => `${toSvgX(h.trust_coord)},${toSvgY(h.power_coord)}`);
    return pts.join(' ');
  }, [history]);

  // ── 空状态 ──
  if (!loading && !ssfState && !externalEnterprises) {
    return (
      <Card title="博弈状态定位" size="small">
        <Empty description="请选择企业以查看SSF博弈状态" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const size = compact ? 280 : SVG_SIZE;

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>博弈状态四象限定位</span>
          {allEnterprises.length > 0 && (
            <Segmented
              size="small"
              value={showAll ? 'all' : 'single'}
              onChange={(v) => setShowAll(v === 'all')}
              options={[
                { label: '当前企业', value: 'single', icon: <AimOutlined /> },
                { label: `全部(${allEnterprises.length})`, value: 'all', icon: <ThunderboltOutlined /> },
              ]}
            />
          )}
        </div>
      }
      size="small"
      style={compact ? { marginBottom: 0 } : undefined}
    >
      <Spin spinning={loading}>
        <div style={{ display: 'flex', flexDirection: compact ? 'column' : 'row', gap: 16, alignItems: 'flex-start' }}>
          {/* ═══ SVG 四象限图 ═══ */}
          <svg
            viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
            width={size}
            height={size}
            style={{ flexShrink: 0, borderRadius: 8, border: '1px solid #e5e7eb' }}
          >
            {/* 象限背景 */}
            {QUADRANTS.map((q) => (
              <g key={q.key}>
                <rect
                  x={q.x === 0 ? PADDING : CENTER}
                  y={q.y === 0 ? PADDING : CENTER}
                  width={PLOT_SIZE / 2}
                  height={PLOT_SIZE / 2}
                  fill={q.bgColor}
                  stroke={q.borderColor}
                  strokeWidth={0.5}
                  strokeDasharray="4 2"
                  opacity={0.6}
                />
                {/* 象限标签 */}
                <text
                  x={Q_LABELS.find((l) => l.key === q.key)?.x ?? 0}
                  y={(Q_LABELS.find((l) => l.key === q.key)?.y ?? 0) - 6}
                  textAnchor="middle"
                  fontSize={11}
                  fill={q.textColor}
                  fontWeight={600}
                  opacity={0.7}
                >
                  {q.label}
                </text>
                <text
                  x={Q_LABELS.find((l) => l.key === q.key)?.x ?? 0}
                  y={(Q_LABELS.find((l) => l.key === q.key)?.y ?? 0) + 8}
                  textAnchor="middle"
                  fontSize={9}
                  fill={q.textColor}
                  opacity={0.5}
                >
                  {q.strategy}
                </text>
              </g>
            ))}

            {/* 中心十字线 */}
            <line x1={CENTER} y1={PADDING} x2={CENTER} y2={PADDING + PLOT_SIZE}
                  stroke="#9CA3AF" strokeWidth={1} strokeDasharray="3 3" opacity={0.5} />
            <line x1={PADDING} y1={CENTER} x2={PADDING + PLOT_SIZE} y2={CENTER}
                  stroke="#9CA3AF" strokeWidth={1} strokeDasharray="3 3" opacity={0.5} />

            {/* 坐标轴 */}
            <line x1={PADDING} y1={PADDING + PLOT_SIZE} x2={PADDING + PLOT_SIZE} y2={PADDING + PLOT_SIZE}
                  stroke="#6B7280" strokeWidth={1.5} />
            <line x1={PADDING} y1={PADDING} x2={PADDING} y2={PADDING + PLOT_SIZE}
                  stroke="#6B7280" strokeWidth={1.5} />

            {/* 轴标签 */}
            <text x={SVG_SIZE / 2} y={SVG_SIZE - 6} textAnchor="middle" fontSize={11} fill="#6B7280" fontWeight={500}>
              信任程度 →
            </text>
            <text x={10} y={SVG_SIZE / 2} textAnchor="middle" fontSize={11} fill="#6B7280"
                  transform={`rotate(-90, 10, ${SVG_SIZE / 2})`} fontWeight={500}>
              权力感知 →
            </text>

            {/* 轴标注 */}
            <text x={toSvgX(25)} y={PADDING + PLOT_SIZE + 14} textAnchor="middle" fontSize={9} fill="#9CA3AF">低信任</text>
            <text x={toSvgX(75)} y={PADDING + PLOT_SIZE + 14} textAnchor="middle" fontSize={9} fill="#9CA3AF">高信任</text>
            <text x={PADDING - 10} y={toSvgY(25)} textAnchor="end" fontSize={9} fill="#9CA3AF">低权力</text>
            <text x={PADDING - 10} y={toSvgY(75)} textAnchor="end" fontSize={9} fill="#9CA3AF">高权力</text>

            {/* 历史轨迹线 */}
            {trajectoryPoints && !showAll && (
              <polyline
                points={trajectoryPoints}
                fill="none"
                stroke="#9CA3AF"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                opacity={0.6}
              />
            )}

            {/* 历史轨迹点 */}
            {!showAll && history.map((h, i) => (
              <circle
                key={i}
                cx={toSvgX(h.trust_coord)}
                cy={toSvgY(h.power_coord)}
                r={i === history.length - 1 ? 3 : 2}
                fill={i === history.length - 1 ? '#6B7280' : '#D1D5DB'}
                stroke="#fff"
                strokeWidth={0.5}
              />
            ))}

            {/* 全部企业散点 */}
            {showAll && allEnterprises.map((ent) => {
              const isCurrent = ent.enterprise_id === enterpriseId;
              return (
                <g key={ent.enterprise_id}>
                  <circle
                    cx={toSvgX(ent.trust_coord)}
                    cy={toSvgY(ent.power_coord)}
                    r={isCurrent ? 7 : 4}
                    fill={ent.quadrant_color}
                    stroke={isCurrent ? '#fff' : 'none'}
                    strokeWidth={isCurrent ? 2.5 : 0}
                    opacity={isCurrent ? 1 : 0.6}
                    style={{ cursor: 'pointer' }}
                  />
                  {isCurrent && (
                    <circle
                      cx={toSvgX(ent.trust_coord)}
                      cy={toSvgY(ent.power_coord)}
                      r={10}
                      fill="none"
                      stroke={ent.quadrant_color}
                      strokeWidth={1.5}
                      opacity={0.4}
                    />
                  )}
                  <title>{ent.enterprise_name} ({ent.quadrant_name})</title>
                </g>
              );
            })}

            {/* 当前企业高亮 */}
            {currentPoint && !showAll && (
              <>
                {/* 脉冲光圈 */}
                <circle
                  cx={currentPoint.x}
                  cy={currentPoint.y}
                  r={12}
                  fill="none"
                  stroke={currentPoint.color}
                  strokeWidth={2}
                  opacity={0.3}
                >
                  <animate attributeName="r" from={10} to={16} dur="1.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from={0.4} to={0} dur="1.5s" repeatCount="indefinite" />
                </circle>
                {/* 主圆点 */}
                <circle
                  cx={currentPoint.x}
                  cy={currentPoint.y}
                  r={8}
                  fill={currentPoint.color}
                  stroke="#fff"
                  strokeWidth={2.5}
                />
                {/* 企业名标签 */}
                <text
                  x={currentPoint.x}
                  y={currentPoint.y - 16}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#374151"
                  fontWeight={600}
                >
                  {currentPoint.name.length > 6 ? currentPoint.name.slice(0, 6) + '...' : currentPoint.name}
                </text>
              </>
            )}
          </svg>

          {/* ═══ 右侧信息卡片 ═══ */}
          {ssfState && !compact && (
            <div style={{ flex: 1, minWidth: 180 }}>
              {/* 当前位置 */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    backgroundColor: ssfState.quadrant_color,
                  }} />
                  <span style={{ fontWeight: 600, fontSize: 15, color: ssfState.quadrant_color }}>
                    {ssfState.quadrant_name}
                  </span>
                  <Tag color={ssfState.risk_trend === 'critical' ? 'red' : ssfState.risk_trend === 'volatile' ? 'orange' : ssfState.risk_trend === 'fragile' ? 'blue' : 'green'}>
                    {ssfState.risk_trend === 'stable_low' ? '稳定低风险' :
                     ssfState.risk_trend === 'volatile' ? '波动中' :
                     ssfState.risk_trend === 'critical' ? '高危' : '脆弱态'}
                  </Tag>
                </div>
                <p style={{ fontSize: 12, color: '#6B7280', margin: 0 }}>{ssfState.quadrant_subtitle}</p>
              </div>

              {/* NPT 策略配比 */}
              <div style={{ marginBottom: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>NPT 干预策略配比</span>
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  {(['nudge', 'budge', 'trudge'] as const).map((key) => {
                    const pct = Math.round(ssfState.npt_mix[key] * 100);
                    const cfg = NPT_LABELS[key];
                    return (
                      <Tooltip key={key} title={`${cfg.label}: ${pct}%`}>
                        <div style={{
                          flex: ssfState.npt_mix[key],
                          height: 20,
                          backgroundColor: cfg.color,
                          borderRadius: 4,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minWidth: pct > 15 ? 40 : 24,
                          fontSize: 10,
                          color: '#fff',
                          fontWeight: 600,
                          opacity: ssfState.primary_strategy === key ? 1 : 0.5,
                          border: ssfState.primary_strategy === key ? `2px solid ${cfg.color}` : 'none',
                        }}>
                          {cfg.label.split(' ')[0]}
                        </div>
                      </Tooltip>
                    );
                  })}
                </div>
              </div>

              {/* 主导策略 */}
              <div style={{
                padding: '8px 12px',
                backgroundColor: '#F9FAFB',
                borderRadius: 6,
                border: '1px solid #E5E7EB',
                marginBottom: 12,
              }}>
                <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 2 }}>主导策略</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                  {NPT_LABELS[ssfState.primary_strategy]?.label}
                </div>
                <div style={{ fontSize: 11, color: '#4B5563', marginTop: 2 }}>
                  {ssfState.strategy_brief}
                </div>
              </div>

              {/* 移动方向 */}
              <div style={{
                padding: '8px 12px',
                backgroundColor: ssfState.movement_description.startsWith('✅') ? '#F0FDF4' :
                                  ssfState.movement_description.startsWith('⚠') ? '#FFF7ED' : '#F9FAFB',
                borderRadius: 6,
                border: '1px solid #E5E7EB',
              }}>
                <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 2 }}>状态变化</div>
                <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.4 }}>
                  {ssfState.movement_description}
                </div>
                <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>
                  目标：{ssfState.target_direction}
                </div>
              </div>

              {/* 数据来源 */}
              <div style={{ marginTop: 8, fontSize: 10, color: '#9CA3AF' }}>
                <div>权力: {ssfState.power_source}</div>
                <div>信任: {ssfState.trust_source}</div>
              </div>
            </div>
          )}
        </div>
      </Spin>
    </Card>
  );
}
