import { useState, useEffect, useMemo, useCallback } from 'react';
import { useEnterpriseStore } from '@/store';
import { reportApi } from '@/api';
import { determineSizeTier, generateSimulatedProfile } from '@/components/profile';
import { LoadingSpinner, EmptyState } from '@/components/common';
import { Button, Card, Tag, Descriptions, Divider, Switch, Tooltip, App } from 'antd';
import {
  FileTextOutlined, DownloadOutlined, ReloadOutlined,
  SafetyCertificateOutlined, WarningOutlined, CheckCircleOutlined,
  StarOutlined, StarFilled,
  AlertOutlined, RiseOutlined, KeyOutlined,
  ColumnHeightOutlined,
} from '@ant-design/icons';
import type { Report, ReportContent, RiskLevel } from '@/types';
import { RISK_COLORS, BIAS_LABELS } from '@/types';

function Reports() {
  const { message } = App.useApp();
  const { currentEnterprise } = useEnterpriseStore();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [includeProfile, setIncludeProfile] = useState(false);
  const [highlightedKeys, setHighlightedKeys] = useState<Set<string>>(new Set());

  const enterpriseId = currentEnterprise?.id;

  const fetchReport = () => {
    if (!enterpriseId) return;
    setLoading(true);
    reportApi.list(enterpriseId)
      .then((res) => {
        const reports = res.data.data?.reports || [];
        setReport(reports[0] || null);
      })
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!enterpriseId) { setReport(null); return; }
    fetchReport();
  }, [enterpriseId]);

  // ── 模拟画像（与 Profile 页面一致的行业×规模回退逻辑）──
  const simulatedProfile = useMemo(() => {
    if (!currentEnterprise) return null;
    const industry = currentEnterprise.industry || '批发零售';
    const revenue = currentEnterprise.revenue_annual ?? 5_000_000;
    const tier = determineSizeTier(revenue);
    return generateSimulatedProfile(industry, tier, currentEnterprise.id);
  }, [currentEnterprise]);

  // ── 画像数据一致性检查：后端≥3维度为0时降级到模拟数据 ──
  const profileScores = useMemo(() => {
    const profile = report?.content?.profile;
    if (!profile) return (simulatedProfile?.scores ?? {}) as Record<string, number>;
    const backendScores: Record<string, number> = {
      control_desire: profile.control_desire,
      loss_aversion: profile.loss_aversion,
      optimism_bias: profile.optimism_bias,
      control_illusion: profile.control_illusion,
      short_termism: profile.short_termism,
      defensiveness: profile.defensiveness,
    };
    const zeroCount = Object.values(backendScores).filter((v) => v === 0).length;
    if (zeroCount >= 3 && simulatedProfile) {
      return simulatedProfile.scores;
    }
    return backendScores;
  }, [report, simulatedProfile]);

  const profilePeerAverage = useMemo(() => {
    const profile = report?.content?.profile;
    return profile?.peer_average ?? simulatedProfile?.peerAverage ?? {};
  }, [report, simulatedProfile]);

  // ── 从实际展示的分数推导主导偏差（与 Profile 页面一致）──
  const dominantBiases = useMemo(() => {
    return Object.entries(profileScores)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 2)
      .map(([key]) => key);
  }, [profileScores]);

  const handleGenerate = async () => {
    if (!enterpriseId) return;
    setGenerating(true);
    try {
      const res = await reportApi.generate(enterpriseId, includeProfile);
      setReport(res.data.data);
      message.success('报告生成成功');
    } catch {
      message.error('报告生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    if (!report || !enterpriseId) return;
    try {
      const res = await reportApi.download(enterpriseId, includeProfile);
      const blob = res.data instanceof Blob
        ? res.data
        : new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report.title}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('PDF 下载成功');
    } catch {
      message.error('下载失败，请重试');
    }
  };

  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以查看报告" />;
  }

  if (loading || generating) {
    return <LoadingSpinner text={generating ? '正在生成报告...' : '加载报告...'} />;
  }

  if (!report) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-800">报告中心</h2>
        <p className="text-sm text-gray-500">{currentEnterprise.name}</p>

        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <FileTextOutlined className="text-6xl text-gray-300 mb-4" />
          <p className="text-gray-500 mb-6">暂无报告，请生成一份风险评估报告</p>
          <div className="flex items-center justify-center gap-3 mb-4">
            <span className="text-sm text-gray-600">包含心理画像</span>
            <Switch checked={includeProfile} onChange={setIncludeProfile} size="small" />
          </div>
          <Button type="primary" icon={<ReloadOutlined />} onClick={handleGenerate} loading={generating} size="large">
            生成报告
          </Button>
        </div>
      </div>
    );
  }

  const content: ReportContent = report.content;
  const risk = content.risk_assessment;
  const profile = content.profile;

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">报告中心</h2>
          <p className="text-sm text-gray-500 mt-1">
            {report.title}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            icon={<ReloadOutlined />}
            onClick={handleGenerate}
            loading={generating}
          >
            重新生成
          </Button>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleDownload}
          >
            下载报告
          </Button>
        </div>
      </div>

      {/* 报告生成时间 */}
      <div className="text-xs text-gray-400">
        生成时间：{report.generated_at?.slice(0, 19).replace('T', ' ')}
      </div>

      {/* 企业信息 */}
      <Card title="企业基本信息" className="rounded-xl" size="small">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="企业名称">{content.enterprise.name}</Descriptions.Item>
          <Descriptions.Item label="行业">{content.enterprise.industry}</Descriptions.Item>
          <Descriptions.Item label="年营收">
            {(content.enterprise.revenue_annual / 10000).toFixed(1)} 万元
          </Descriptions.Item>
          <Descriptions.Item label="员工人数">{content.enterprise.employee_count} 人</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* ═══════════════════════════════════════
          风险等级与评估建议
          ═══════════════════════════════════════ */}
      {risk ? (
        <div className="space-y-5">
          {/* ── 风险等级 Hero Banner ── */}
          <RiskHeroBanner
            level={(risk.level as RiskLevel) || 'low'}
            score={risk.score}
            fourFlowMatch={risk.four_flow_match}
            privateCardRatio={risk.private_card_ratio}
            costDeviation={risk.cost_deviation}
            enterpriseName={content.enterprise.name}
          />

          {/* ── 核心指标速览 ── */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1 h-4 rounded-full bg-blue-500" />
              <h3 className="text-sm font-semibold text-gray-700">核心指标速览</h3>
            </div>
            <MetricCards risk={risk} />
          </div>

          {/* ── 评估日期 ── */}
          {risk.date && (
            <p className="text-xs text-gray-400">评估日期：{risk.date.slice(0, 10)}</p>
          )}

          {/* ── 评估建议 ── */}
          {(() => {
            // 展平 recommendations 数据结构：分离 flags（风险标记）和 recommendations（整改建议）
            const rawRecs: Record<string, unknown> = risk.recommendations || {};
            const flatFlags: Record<string, string> = {};
            const flatRecs: Record<string, string> = {};

            Object.entries(rawRecs).forEach(([key, val]) => {
              if (!Array.isArray(val)) {
                // 非数组值（如字符串）直接归入建议
                if (typeof val === 'string' && val.trim()) {
                  flatRecs[key] = val;
                } else if (val && typeof val === 'object') {
                  try {
                    const str = JSON.stringify(val);
                    if (str && str.length > 2) flatRecs[key] = str;
                  } catch {}
                }
                return;
              }
              // 数组值：按 key 名分流
              if (key === 'flags') {
                val.forEach((item, i) => {
                  if (typeof item === 'string' && item.trim()) {
                    flatFlags[`flags_${i}`] = item;
                  }
                });
              } else {
                // 其他数组（如 recommendations）归入建议
                val.forEach((item, i) => {
                  if (typeof item === 'string' && item.trim()) {
                    flatRecs[`${key}_${i}`] = item;
                  }
                });
              }
            });

            const hasFlags = Object.keys(flatFlags).length > 0;
            const hasRecs = Object.keys(flatRecs).length > 0;

            // 只有 flag 没有建议 → 显示简化版标记列表
            if (hasFlags && !hasRecs) {
              return (
                <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                  <div className="flex items-center justify-between p-4 sm:p-5 bg-gradient-to-r from-red-50/80 to-white">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center">
                        <WarningOutlined className="text-red-600 text-sm" />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-800">评估建议</h3>
                        <p className="text-[11px] text-gray-400">
                          发现 {Object.keys(flatFlags).length} 项风险特征，暂无具体整改建议
                        </p>
                      </div>
                    </div>
                    <Tag color="red" className="text-[10px] leading-none px-1.5">
                      {Object.keys(flatFlags).length} 项
                    </Tag>
                  </div>
                  <div className="max-h-60 overflow-y-auto divide-y divide-gray-50">
                    {Object.entries(flatFlags).map(([key, text]) => (
                      <div key={key} className="flex items-start gap-3 p-3 hover:bg-gray-50/50">
                        <div className="flex-shrink-0 mt-0.5 w-2.5 h-2.5 rounded-full bg-red-500" />
                        <p className="text-sm text-gray-700 leading-relaxed flex-1 min-w-0">{text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            }

            // 有实际建议 → 合并 flags（归类为"风险标记"）和 recs（归类为"综合建议"）
            const allEntries = { ...flatFlags, ...flatRecs };
            return Object.keys(allEntries).length > 0 ? (
              <RecommendationPanel
                recommendations={allEntries}
                highlightedKeys={highlightedKeys}
                onToggleHighlight={(key) => setHighlightedKeys((prev) => {
                  const next = new Set(prev);
                  next.has(key) ? next.delete(key) : next.add(key);
                  return next;
                })}
              />
            ) : null;
          })()}
        </div>
      ) : (
        <Card className="rounded-xl">
          <p className="text-sm text-gray-400">未包含风险评估数据</p>
        </Card>
      )}

      {/* 心理画像 */}
      {profile ? (
        <Card
          title={
            <div className="flex items-center gap-2">
              <span>心理画像</span>
              <Tag color="purple">偏差指数: {profile.deviation_index}</Tag>
            </div>
          }
          className="rounded-xl"
          size="small"
        >
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
            {([
              { key: 'control_desire', val: profileScores.control_desire },
              { key: 'loss_aversion', val: profileScores.loss_aversion },
              { key: 'optimism_bias', val: profileScores.optimism_bias },
              { key: 'control_illusion', val: profileScores.control_illusion },
              { key: 'short_termism', val: profileScores.short_termism },
              { key: 'defensiveness', val: profileScores.defensiveness },
            ] as const).map(({ key, val }) => (
              <div key={key} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">{BIAS_LABELS[key] || key}</p>
                <p
                  className="text-lg font-bold"
                  style={{ color: val >= 70 ? RISK_COLORS.high : val >= 40 ? RISK_COLORS.medium : RISK_COLORS.low }}
                >
                  {val ?? '-'}
                  {profilePeerAverage[key] != null && (
                    <span className="text-xs font-normal text-gray-400 ml-1">
                      / {profilePeerAverage[key]}
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>

          {dominantBiases.length > 0 && (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-gray-500">主导偏差：</span>
              {dominantBiases.map((b) => (
                <Tag key={b} color="purple">{BIAS_LABELS[b] || b}</Tag>
              ))}
            </div>
          )}

          {profile.business_narrative && (
            <p className="text-xs text-gray-500 leading-relaxed mt-2 border-t pt-2">
              {profile.business_narrative.slice(0, 200)}
              {profile.business_narrative.length > 200 && '...'}
            </p>
          )}

          {profile.date && (
            <p className="text-xs text-gray-400">评估日期：{profile.date.slice(0, 10)}</p>
          )}
        </Card>
      ) : (
        <Card className="rounded-xl">
          <p className="text-sm text-gray-400">未包含心理画像数据（生成时可选择包含）</p>
        </Card>
      )}

      {/* 免责声明 */}
      <Divider />
      <Card className="rounded-xl bg-yellow-50 border-yellow-200">
        <p className="text-xs text-yellow-700 leading-relaxed">
          <strong>免责声明：</strong>{content.disclaimer || '本报告基于模拟数据生成，仅供演示参考，不构成任何税务或法律建议。'}
        </p>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════
// RiskHeroBanner — 风险等级英雄面板
// ═══════════════════════════════════════

const RISK_HERO_CONFIG: Record<string, {
  icon: typeof SafetyCertificateOutlined;
  label: string;
  description: string;
  pulseColor: string;
}> = {
  critical: {
    icon: WarningOutlined,
    label: '严重风险',
    description: '存在极高合规风险，必须立即启动全面整改与内部审查',
    pulseColor: 'rgba(220,38,38,0.18)',
  },
  high: {
    icon: WarningOutlined,
    label: '高风险',
    description: '存在显著合规风险，建议立即采取整改措施',
    pulseColor: 'rgba(239,68,68,0.15)',
  },
  medium_high: {
    icon: AlertOutlined,
    label: '中高风险',
    description: '多个指标接近高危阈值，建议重点关注并限期整改',
    pulseColor: 'rgba(249,115,22,0.13)',
  },
  medium: {
    icon: AlertOutlined,
    label: '中风险',
    description: '有部分指标偏离正常范围，建议持续关注并优先改进',
    pulseColor: 'rgba(245,158,11,0.12)',
  },
  low: {
    icon: CheckCircleOutlined,
    label: '低风险',
    description: '整体处于健康合规区间，按常规定期自查即可',
    pulseColor: 'rgba(16,185,129,0.10)',
  },
};

function RiskHeroBanner({
  level, score, fourFlowMatch, privateCardRatio, costDeviation, enterpriseName,
}: {
  level: RiskLevel;
  score: number;
  fourFlowMatch: number;
  privateCardRatio: number;
  costDeviation: number;
  enterpriseName: string;
}) {
  const cfg = RISK_HERO_CONFIG[level] ?? RISK_HERO_CONFIG.low;
  const color = RISK_COLORS[level] ?? RISK_COLORS.low;
  const Icon = cfg.icon;

  const flaggedCount = [
    { val: fourFlowMatch, thresh: 85, dir: 'gte' as const },
    { val: privateCardRatio, thresh: 20, dir: 'lte' as const },
    { val: costDeviation, thresh: 15, dir: 'lte' as const },
  ].filter(({ val, thresh, dir }) => dir === 'gte' ? val < thresh : val > thresh).length;

  // 五级风险等级 → Ant Design Tag color
  const tagColor: Record<string, string> = {
    low: 'green', medium: 'orange', medium_high: 'orange', high: 'red', critical: 'red',
  };
  // 五级风险等级 → 行动建议
  const tagText: Record<string, string> = {
    low: '保持日常监控', medium: '建议限期整改', medium_high: '建议优先整改', high: '建议立即处置', critical: '必须立即处置',
  };
  // 五级风险等级 → 底部警示文案
  const flaggedSuffix: Record<string, string> = {
    low: '整体在可控范围内。', medium: '建议优先优化偏离较大的指标。', medium_high: '建议制定整改计划并限期完成。',
    high: '强烈建议立即制定整改计划。', critical: '必须立即启动全面自查与整改。',
  };

  return (
    <div className="relative overflow-hidden rounded-2xl border-2 p-5 sm:p-6" style={{
      background: `linear-gradient(135deg, ${cfg.pulseColor} 0%, #ffffff 60%)`,
      borderColor: color + '40',
    }}>
      {/* 背景脉冲动画 */}
      <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full opacity-10 animate-pulse"
        style={{ backgroundColor: color }} />

      {/* 顶部：风险图标 + 等级文字 */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl text-white shadow-lg"
          style={{ backgroundColor: color }}>
          <Icon style={{ fontSize: 28 }} />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl sm:text-2xl font-bold" style={{ color }}>
              {cfg.label}
            </h2>
            <Tag color={tagColor[level] ?? 'green'}
              className="text-xs">
              {tagText[level] ?? '保持日常监控'}
            </Tag>
          </div>
          <p className="text-sm text-gray-500 mt-0.5">{cfg.description}</p>
        </div>
      </div>

      {/* 中段：综合评分 + 核心指标 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        {/* 综合评分 */}
        <div className="bg-white/70 rounded-xl border p-3 text-center"
          style={{ borderColor: color + '30' }}>
          <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-0.5">综合评分</p>
          <p className="text-3xl font-extrabold" style={{ color }}>{score}</p>
          <p className="text-[10px] text-gray-400">/ 100 分</p>
        </div>
        {/* 四流匹配 */}
        <IndicatorChip
          label="四流匹配"
          value={Math.round(fourFlowMatch)}
          unit="%"
          threshold={85}
          reverse={false}
        />
        {/* 私卡收款 */}
        <IndicatorChip
          label="私卡收款比"
          value={Math.round(privateCardRatio)}
          unit="%"
          threshold={20}
          reverse
        />
        {/* 成本偏离 */}
        <IndicatorChip
          label="成本偏离度"
          value={Math.round(costDeviation)}
          unit="%"
          threshold={15}
          reverse
        />
      </div>

      {/* 底部：警示摘要 */}
      {flaggedCount > 0 && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg mt-1"
          style={{ backgroundColor: color + '10' }}>
          <RiseOutlined style={{ color, fontSize: 14 }} />
          <p className="text-xs" style={{ color }}>
            <strong>{enterpriseName}</strong> 有 <strong>{flaggedCount}</strong> 项指标超出健康区间，
            {flaggedSuffix[level] ?? '整体在可控范围内。'}
          </p>
        </div>
      )}
    </div>
  );
}

// ── IndicatorChip — 单指标胶囊卡片 ──
function IndicatorChip({
  label, value, unit, threshold, reverse,
}: {
  label: string;
  value: number;
  unit: string;
  threshold: number;
  reverse: boolean; // true = 值越低越好
}) {
  const healthy = reverse ? value <= threshold : value >= threshold;
  const warn = reverse ? value <= threshold * 2.5 : value >= threshold * 0.75;
  const lvl: RiskLevel = healthy ? 'low' : warn ? 'medium_high' : 'high';
  const color = RISK_COLORS[lvl];
  const statusText = healthy ? '正常' : warn ? '偏移' : '异常';

  return (
    <Tooltip title={`健康阈值：${reverse ? '≤' : '≥'}${threshold}${unit}`}>
      <div className="bg-white/70 rounded-xl border p-3 hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200 cursor-default"
        style={{ borderColor: color + '30' }}>
        <div className="flex items-center justify-between mb-1">
          <p className="text-[10px] text-gray-400 uppercase tracking-wide">{label}</p>
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
            style={{ backgroundColor: color + '18', color }}>
            {statusText}
          </span>
        </div>
        <p className="text-xl font-bold" style={{ color }}>{value}
          <span className="text-xs font-normal ml-0.5" style={{ color: color + '99' }}>{unit}</span>
        </p>
      </div>
    </Tooltip>
  );
}

// ═══════════════════════════════════════
// MetricCards — 核心指标卡片网格
// ═══════════════════════════════════════

function MetricCards({ risk }: { risk: { score: number; four_flow_match: number; private_card_ratio: number; cost_deviation: number } }) {
  const items = [
    { label: '综合评分', value: risk.score, unit: '分', desc: '加权综合评估', thresh: 70, reverse: false, icon: SafetyCertificateOutlined },
    { label: '四流匹配度', value: Math.round(risk.four_flow_match), unit: '%', desc: '合同/发票/货/资金一致性', thresh: 85, reverse: false, icon: CheckCircleOutlined },
    { label: '私卡收款占比', value: Math.round(risk.private_card_ratio), unit: '%', desc: '个人账户对公流水比例', thresh: 20, reverse: true, icon: WarningOutlined },
    { label: '成本偏离指数', value: Math.round(risk.cost_deviation), unit: '%', desc: '相对行业基准的成本率偏差', thresh: 15, reverse: true, icon: RiseOutlined },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map((item) => {
        const healthy = item.reverse ? item.value <= item.thresh : item.value >= item.thresh;
        const warn = item.reverse ? item.value <= item.thresh * 2 : item.value >= item.thresh * 0.75;
        const lvl: RiskLevel = healthy ? 'low' : warn ? 'medium_high' : 'high';
        const color = RISK_COLORS[lvl];
        const Icon = item.icon;
        const tipText = `${item.reverse ? '健康值 ≤' : '健康值 ≥'}${item.thresh}${item.unit}`;

        return (
          <Tooltip key={item.label} title={tipText}>
            <div
              className="bg-white rounded-xl border p-4 hover:shadow-lg hover:-translate-y-1 transition-all duration-200 cursor-default group"
              style={{ borderLeftColor: color, borderLeftWidth: 3 }}
            >
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-400 font-medium">{item.label}</p>
                <div className="opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ color: color + '60' }}>
                  <Icon style={{ fontSize: 14 }} />
                </div>
              </div>
              <p className="text-2xl font-extrabold" style={{ color }}>{item.value}
                <span className="text-xs font-normal ml-0.5 text-gray-400">{item.unit}</span>
              </p>
              <p className="text-[10px] text-gray-400 mt-1">{item.desc}</p>
              {/* 微型进度条 */}
              <div className="mt-2 h-1 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(item.value, 100)}%`, backgroundColor: color }} />
              </div>
            </div>
          </Tooltip>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════
// RecommendationPanel — 评估建议面板
// ═══════════════════════════════════════

const REC_CATEGORIES: Record<string, { label: string; color: string; icon: typeof KeyOutlined }> = {
  four_flow_match: { label: '四流匹配', color: '#3B82F6', icon: KeyOutlined },
  private_card: { label: '资金合规', color: '#F59E0B', icon: KeyOutlined },
  cost_deviation: { label: '成本管控', color: '#8B5CF6', icon: KeyOutlined },
  tax_burden: { label: '税负优化', color: '#EF4444', icon: KeyOutlined },
  product_jaccard: { label: '进销项匹配', color: '#10B981', icon: KeyOutlined },
  invoice_bank: { label: '发票合规', color: '#EC4899', icon: KeyOutlined },
  large_transfer: { label: '大额转账', color: '#F97316', icon: KeyOutlined },
  flags: { label: '风险标记', color: '#DC2626', icon: KeyOutlined },
  __default: { label: '综合建议', color: '#6B7280', icon: KeyOutlined },
};

function getRecCategory(key: string) {
  // 去掉展平后缀（如 flags_0 → flags）
  const cleanKey = key.replace(/_\d+$/, '');
  for (const k of Object.keys(REC_CATEGORIES)) {
    if (k === '__default') continue;
    if (cleanKey.includes(k) || k.includes(cleanKey) || cleanKey.toLowerCase().includes(k.replace(/_/g, ''))) {
      return REC_CATEGORIES[k];
    }
  }
  return REC_CATEGORIES.__default;
}

function RecommendationPanel({
  recommendations, highlightedKeys, onToggleHighlight,
}: {
  recommendations: Record<string, unknown>;
  highlightedKeys: Set<string>;
  onToggleHighlight: (key: string) => void;
}) {
  const entries = Object.entries(recommendations);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const COLLAPSE_LENGTH = 120; // 超过此行数后显示展开按钮

  const toggleExpand = useCallback((key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) { next.delete(key); } else { next.add(key); }
      return next;
    });
  }, []);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 sm:p-5 bg-gradient-to-r from-blue-50/80 to-white">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
            <StarOutlined className="text-blue-600 text-sm" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-800">评估建议</h3>
            <p className="text-[11px] text-gray-400">
              {entries.length} 条建议 · {highlightedKeys.size > 0 ? `${highlightedKeys.size} 条已标记为重点` : '点击星标标记重点'}
            </p>
          </div>
        </div>
        {highlightedKeys.size > 0 && (
          <Tag color="gold" className="text-[10px] leading-none px-1.5">{highlightedKeys.size} 已标</Tag>
        )}
      </div>

      {/* 建议列表 */}
      <div className="divide-y divide-gray-50 max-h-[420px] overflow-y-auto">
        {entries.map(([key, val]) => {
          const cat = getRecCategory(key);
          const isHighlighted = highlightedKeys.has(key);
          const text = String(val);
          const isExpanded = expandedKeys.has(key);
          const needsCollapse = text.length > COLLAPSE_LENGTH;

          return (
            <div
              key={key}
              className={`group flex items-start gap-3 sm:gap-4 p-3 sm:p-4 transition-colors hover:bg-gray-50/50 ${
                isHighlighted ? 'bg-amber-50/50' : ''
              }`}
            >
              {/* 类别标签 */}
              <div className="flex-shrink-0 mt-0.5">
                <Tooltip title={cat.label}>
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: cat.color }} />
                </Tooltip>
              </div>

              {/* 建议内容 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                    style={{ backgroundColor: cat.color + '14', color: cat.color }}>
                    {cat.label}
                  </span>
                  {isHighlighted && (
                    <Tag color="gold" className="text-[10px] leading-none px-1.5">重点</Tag>
                  )}
                </div>
                <div className={`text-sm text-gray-700 leading-relaxed ${
                  !isExpanded && needsCollapse
                    ? 'relative max-h-[3.6em] overflow-hidden after:content-[\'\'] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-8 after:bg-gradient-to-t after:from-white after:to-transparent'
                    : ''
                }`}>
                  <p>{text}</p>
                </div>
                {/* 高亮标记 — 全局关键词 */}
                {isHighlighted && isExpanded && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {['立即', '尽快', '必须', '优先', '严重'].filter((kw) => text.includes(kw)).map((kw) => (
                      <span key={kw} className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                        {kw}
                      </span>
                    ))}
                  </div>
                )}
                {/* 展开/收起按钮 — 始终显示 */}
                <button
                  onClick={() => toggleExpand(key)}
                  className="mt-1 flex items-center gap-1 text-[10px] text-blue-500 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-all"
                  title={isExpanded ? '收起' : '展开全文'}
                >
                  <ColumnHeightOutlined className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  {isExpanded ? '收起' : needsCollapse ? `展开全文 (${text.length}字)` : `收起`}
                </button>
              </div>

              {/* 操作按钮 */}
              <button
                onClick={(e) => { e.stopPropagation(); onToggleHighlight(key); }}
                className="flex-shrink-0 p-1.5 rounded-lg hover:bg-gray-100 transition-colors opacity-30 group-hover:opacity-100"
                title={isHighlighted ? '取消标记' : '标记为重点'}
              >
                {isHighlighted
                  ? <StarFilled className="text-amber-500 text-sm" />
                  : <StarOutlined className="text-gray-400 text-sm" />
                }
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default Reports;
