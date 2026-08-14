import { useEffect, useState, useMemo } from 'react';
import { useEnterpriseStore, useRiskViewState } from '@/store';
import { complianceApi, enterpriseApi, riskScanApi } from '@/api';
import { RiskLegend, LanguageToggle, RiskMapCard } from '@/components/riskmap';
import SSFQuadrantChart from '@/components/ssf';
import { DualCostGauge, TaxBurdenElasticityChart } from '@/components/charts';
import { LoadingSpinner, EmptyState, TableContainer } from '@/components/common';
import { Button, Progress, Switch, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  RISK_COLORS, RISK_LABELS, AUDIT_PROBABILITY_CRITICAL,
  BUSINESS_MODEL_MAP, BUSINESS_MODEL_DESC,
} from '@/types';
import type { RiskLevel, BusinessModel, CostGaugeData, TaxBurdenElasticityData, ICRadarData, NBTInterventionResult, MatchDetailItem, RiskScoreTrajectory } from '@/types';
import type { Language } from '@/components/riskmap';

// ═══════════════════════════════════════
// 业务总述解析
// ═══════════════════════════════════════
interface StructuredNarrative {
  title: string;
  riskLevel: string;
  riskScore: number;
  riskFlags: string[];
  recommendations: string[];
}

function _parseRiskNarrative(raw: string): StructuredNarrative {
  const result: StructuredNarrative = {
    title: '',
    riskLevel: '',
    riskScore: 0,
    riskFlags: [],
    recommendations: [],
  };

  if (!raw) return result;

  const lines = raw.split('\n');

  // 标题（第一行，去掉「」）
  const titleMatch = lines[0]?.match(/「(.+?)」/);
  if (titleMatch) result.title = titleMatch[1];

  // 综合风险等级
  for (const line of lines) {
    const levelMatch = line.match(/综合风险等级[：:]\s*(.+)/);
    if (levelMatch) {
      result.riskLevel = levelMatch[1].trim();
      break;
    }
  }

  // 综合风险评分
  for (const line of lines) {
    const scoreMatch = line.match(/综合风险评分[：:]\s*(\d+)/);
    if (scoreMatch) {
      result.riskScore = parseInt(scoreMatch[1], 10);
      break;
    }
  }

  // 风险点与整改建议分段
  let inFlags = false;
  let inRecs = false;
  for (const line of lines) {
    if (line.startsWith('发现 ') && line.includes('个风险点')) {
      inFlags = true;
      inRecs = false;
      continue;
    }
    if (line.includes('整改建议')) {
      inFlags = false;
      inRecs = true;
      continue;
    }
    if (line.trim() === '') {
      if (inFlags && result.riskFlags.length > 0) inFlags = false;
      if (inRecs && result.recommendations.length > 0) inRecs = false;
      continue;
    }
    if (inFlags) {
      const cleaned = line.replace(/^\s*\d+\.\s*/, '').trim();
      if (cleaned) result.riskFlags.push(cleaned);
    }
    if (inRecs) {
      const cleaned = line.replace(/^\s*\d+\.\s*/, '').trim();
      if (cleaned) result.recommendations.push(cleaned);
    }
  }

  return result;
}

// ── 维度中文名映射 ──
const DIM_NAMES: Record<string, string> = {
  private_card_ratio: '私卡收款',
  cost_deviation: '成本偏离',
  tax_burden_deviation: '税负率偏离',
  four_flow_mismatch: '四流不匹配',
  four_flow_match: '四流匹配',             // 后端实际返回的 key
  invoice_bank_mismatch: '票银不匹配',
  large_personal_transfer: '大额公转私',
  input_output_imbalance: '进销项失衡',
};

// ── 从企业数据推导内控雷达数据 ──
function deriveICRadarData(
  enterprise: { industry: string; cost_rate_claimed: number; tax_rate_claimed: number; revenue_annual: number } | null,
  result: { overall_risk_level: string; overall_risk_score: number; dimension_scores: Record<string, number> } | null,
  nbtData: NBTInterventionResult | null,
  complianceReduction = 0,
  isFullyCompliant = false,
): ICRadarData {
  const industryCostRate = enterprise?.cost_rate_claimed ?? 85;
  const industryTaxRate = enterprise?.tax_rate_claimed ?? 3.5;

  const costScore = result?.dimension_scores?.['cost_deviation'] ?? 0;
  const estimatedDeviation = costScore >= 75 ? 30 : costScore >= 30 ? 15 : costScore > 0 ? 5 : 0;
  const actualCostRate = industryCostRate + (costScore > 0 ? estimatedDeviation : 0);
  const warningThreshold = Math.min(industryCostRate + 30, 100);

  const costGauge: CostGaugeData = {
    actualCostRate: Math.round(actualCostRate * 10) / 10,
    industryCostRate,
    warningThreshold,
    deviation: Math.round((actualCostRate - industryCostRate) * 10) / 10,
    severity: costScore >= 75 ? 'severe' : costScore >= 30 ? 'moderate' : 'normal',
  };

  const taxBurdenScore = result?.dimension_scores?.['tax_burden_deviation'] ?? 0;
  const actualTaxRate = Math.max(0.5, industryTaxRate - (taxBurdenScore > 50 ? 2.5 : taxBurdenScore > 20 ? 1.0 : 0.3));
  const elasticity: TaxBurdenElasticityData[] = [
    { period: 'Q1', revenueGrowth: 8.5, taxBurdenRate: Number((actualTaxRate * 0.85).toFixed(2)), expectedTaxBurden: industryTaxRate },
    { period: 'Q2', revenueGrowth: 12.3, taxBurdenRate: Number((actualTaxRate * 0.72).toFixed(2)), expectedTaxBurden: industryTaxRate },
    { period: 'Q3', revenueGrowth: 15.8, taxBurdenRate: Number((actualTaxRate * 0.58).toFixed(2)), expectedTaxBurden: industryTaxRate },
    { period: 'Q4', revenueGrowth: 18.2, taxBurdenRate: Number((actualTaxRate * 0.45).toFixed(2)), expectedTaxBurden: industryTaxRate },
  ];

  const nudgeRiskStatement = nbtData?.nudge?.risk_statement ?? '';
  const hasICFailure = nudgeRiskStatement.includes('预警') || nudgeRiskStatement.includes('94%') || taxBurdenScore >= 80;

  const riskLevel = isFullyCompliant ? 'low' : (result?.overall_risk_level ?? 'low');
  const rawAuditProb =
    riskLevel === 'critical' ? 0.95 :
    riskLevel === 'high' ? 0.80 :
    riskLevel === 'medium_high' ? 0.60 :
    riskLevel === 'medium' ? 0.45 :
    0.15;
  // 合规调整：降低稽查概率
  const predictedAuditProbability = Math.max(0.05, rawAuditProb * (1 - complianceReduction * 0.7));

  return {
    costGauge,
    taxBurdenElasticity: elasticity,
    internalControlFailureWarning: hasICFailure,
    predictedAuditProbability,
  };
}

// ── 老板视角：风险影响金额估算 ──
function estimateFinancialImpact(result: { overall_risk_level: string; overall_risk_score: number } | null, enterprise: { revenue_annual: number } | null, complianceReduction = 0) {
  const revenue = enterprise?.revenue_annual ?? 1000000;
  const score = result?.overall_risk_score ?? 0;
  const originalLevel = result?.overall_risk_level ?? 'low';
  const level = complianceReduction >= 0.45 ? 'low' : originalLevel;
  // 基于风险等级估算潜在补税+罚款金额
  const penaltyRate =
    level === 'critical' ? 0.40 :
    level === 'high' ? 0.25 :
    level === 'medium_high' ? 0.18 :
    score >= 40 ? 0.12 :
    0.04;
  return {
    estimatedTaxGap: Math.round(revenue * 0.05),
    estimatedPenalty: Math.round(revenue * penaltyRate),
    severeDimensionCount: 0, // filled below
  };
}

function RiskMap() {
  const { currentEnterprise } = useEnterpriseStore();
  const { result, isBusy, scanRisk, fetchLatest } = useRiskViewState();
  const [language, setLanguage] = useState<Language>('business');
  const [nbtData, setNbtData] = useState<NBTInterventionResult | null>(null);
  const [nbtLoading, setNbtLoading] = useState(false);
  // 合规调整数据（跨模块联动）
  const [complianceReduction, setComplianceReduction] = useState(0);
  const [isFullyCompliant, setIsFullyCompliant] = useState(false);
  // 匹配明细筛选：仅显示未匹配项
  const [onlyUnmatched, setOnlyUnmatched] = useState(false);
  // 整改前后评分演化轨迹（B3）
  const [trajectories, setTrajectories] = useState<RiskScoreTrajectory[]>([]);

  const enterpriseId = currentEnterprise?.id;

  useEffect(() => {
    if (!enterpriseId) return;
    fetchLatest(enterpriseId);
    // 同时获取合规调整数据
    enterpriseApi.detail(enterpriseId)
      .then((res) => {
        const compliance = (res.data.data as Record<string, unknown>)?.compliance as Record<string, unknown> | undefined;
        if (compliance) {
          setComplianceReduction(typeof compliance.reduction_pct === 'number' ? compliance.reduction_pct : 0);
          setIsFullyCompliant(Boolean(compliance.is_fully_compliant));
        }
      })
      .catch(() => {});
  }, [enterpriseId, fetchLatest]);

  // 整改/重评评分演化轨迹（A1：整改前后评分对照）
  useEffect(() => {
    if (!enterpriseId) return;
    riskScanApi.trajectory(enterpriseId)
      .then((res) => setTrajectories(res.data.data.trajectories ?? []))
      .catch(() => setTrajectories([]));
  }, [enterpriseId]);

  useEffect(() => {
    if (!enterpriseId || !result) return;
    setNbtLoading(true);
    complianceApi
      .nbtIntervention(enterpriseId, {
        enterprise_name: currentEnterprise?.name,
        industry: currentEnterprise?.industry,
        overall_risk_level: result.overall_risk_level,
        overall_risk_score: result.overall_risk_score,
        dimension_scores: result.dimension_scores,
      })
      .then((res) => setNbtData(res.data.data ?? null))
      .catch(() => setNbtData(null))
      .finally(() => setNbtLoading(false));
  }, [enterpriseId, result]); // eslint-disable-line react-hooks/exhaustive-deps

  const businessModel: BusinessModel = useMemo(
    () => BUSINESS_MODEL_MAP[currentEnterprise?.industry ?? ''] ?? 'asset_light',
    [currentEnterprise?.industry],
  );

  const icRadar = useMemo(
    () => deriveICRadarData(currentEnterprise ?? null, result, nbtData, complianceReduction, isFullyCompliant),
    [currentEnterprise, result, nbtData, complianceReduction, isFullyCompliant],
  );

  // ── 合规调整后的风险评分和等级 ──
  const adjustedRiskScore = useMemo(() => {
    if (!result?.overall_risk_score) return 0;
    if (isFullyCompliant) return 10;
    return Math.round(result.overall_risk_score * (1 - complianceReduction));
  }, [result, complianceReduction, isFullyCompliant]);

  const adjustedRiskLevel = useMemo((): RiskLevel => {
    if (isFullyCompliant) return 'low';
    if (!result?.overall_risk_level) return 'low';
    const score = adjustedRiskScore;
    if (score >= 80) return 'critical';
    if (score >= 60) return 'high';
    if (score >= 45) return 'medium_high';
    if (score >= 30) return 'medium';
    return 'low';
  }, [result, adjustedRiskScore, isFullyCompliant]);

  // ── 合规得分（A3：风险分 = 100 − 合规得分，双轨展示） ──
  const complianceScore = useMemo(() => Math.round(100 - adjustedRiskScore), [adjustedRiskScore]);
  const rawRiskScore = useMemo(
    () => Math.round(result?.overall_risk_score ?? 0),
    [result?.overall_risk_score],
  );

  const isCritical = useMemo(
    () =>
      !isFullyCompliant && (
        icRadar.internalControlFailureWarning ||
        icRadar.predictedAuditProbability >= AUDIT_PROBABILITY_CRITICAL ||
        adjustedRiskLevel === 'high' ||
        adjustedRiskLevel === 'critical'
      ),
    [icRadar, adjustedRiskLevel, isFullyCompliant],
  );

  // 老板视角财务影响估算（必须在所有 return 之前）
  const financialImpact = useMemo(
    () => {
      if (!result) return { estimatedTaxGap: 0, estimatedPenalty: 0, severeDimensionCount: 0 };
      const dimScores = result.dimension_scores ?? {};
      const entries = Object.entries(dimScores);
      const criticalCount = entries.filter(([, s]) => s >= 85).length;
      const highCount = entries.filter(([, s]) => s >= 70 && s < 85).length;
      const impact = estimateFinancialImpact(result, currentEnterprise, complianceReduction);
      impact.severeDimensionCount = highCount + criticalCount;
      return impact;
    },
    [result, currentEnterprise],
  );

  // ── 无企业 ──
  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以查看风险地图" />;
  }

  // ── 加载中 ──
  if (isBusy) {
    return <LoadingSpinner text="正在加载风险数据..." />;
  }

  // ── 无结果 ──
  if (!result) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-800">五维全景税务内控侦测面板</h2>
        <EmptyState text="尚未执行风险扫描，请先前往数据驾驶舱触发扫描" />
      </div>
    );
  }

  const { dimension_scores = {}, dim_details = {}, overall_risk_score } = result;

  // 四流匹配明细（后端 match_details）
  const matchDetails: MatchDetailItem[] = result.match_details ?? [];

  // 维度统计（五级分类）
  const dimEntries = Object.entries(dimension_scores);
  const criticalDims = dimEntries.filter(([, s]) => s >= 85);
  const highDims = dimEntries.filter(([, s]) => s >= 70 && s < 85);
  const mediumHighDims = dimEntries.filter(([, s]) => s >= 55 && s < 70);
  const mediumDims = dimEntries.filter(([, s]) => s >= 40 && s < 55);
  const lowDims = dimEntries.filter(([, s]) => s < 40);

  // ══════════════════════════════════════════
  // 顶栏 Banner（两个视角共用）
  // ══════════════════════════════════════════
  const topBanner = (
    <div
      className={`
        relative overflow-hidden rounded-2xl border p-5 sm:p-6
        ${isCritical
          ? 'bg-red-500 border-red-600'
          : businessModel === 'asset_heavy'
            ? 'bg-gradient-to-r from-slate-700 to-slate-800 border-slate-600'
            : 'bg-gradient-to-r from-blue-700 to-indigo-800 border-blue-600'
        }
      `}
    >
      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-2">
          <span className={`
            px-3 py-1 rounded-full text-xs font-bold
            ${isCritical ? 'bg-red-700 text-red-100' : 'bg-white/20 text-white'}
          `}>
            {businessModel === 'asset_heavy' ? '重资产制造' : '轻资产服务'}
          </span>
          <span className={`text-sm ${isCritical ? 'text-red-100' : 'text-white/70'}`}>
            {currentEnterprise.name} · {currentEnterprise.industry}
          </span>
        </div>
        <p className={`text-sm leading-relaxed max-w-2xl ${isCritical ? 'text-red-100' : 'text-white/80'}`}>
          {BUSINESS_MODEL_DESC[businessModel]}
        </p>
        {isCritical && (
          <div className="mt-3 flex items-center gap-2 bg-red-700/40 rounded-lg px-4 py-2.5">
            <span className="text-2xl">&#9888;</span>
            <div>
              <p className="text-sm font-bold text-white">
                {icRadar.internalControlFailureWarning ? '内控失效预警已触发' : '稽查概率超过80%高危阈值'}
              </p>
              <p className="text-xs text-red-200">
                预计稽查概率 {Math.round(icRadar.predictedAuditProbability * 100)}%，请立即关注风险指标
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // ══════════════════════════════════════════
  // 工具条（两个视角共用）
  // ══════════════════════════════════════════
  const toolbar = (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <RiskLegend />
      <div className="flex items-center gap-2">
        <Button
          type="default"
          size="small"
          onClick={() => enterpriseId && scanRisk(enterpriseId)}
          disabled={!enterpriseId || isBusy}
        >
          重新扫描
        </Button>
        <LanguageToggle value={language} onChange={setLanguage} />
      </div>
    </div>
  );

  // ══════════════════════════════════════════
  // 老板视角：风险全局概览
  // ══════════════════════════════════════════
  const bossOverviewCards = (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
      {/* 综合风险评分（合规调整后） */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:shadow-md transition-shadow">
        <p className="text-xs text-gray-400 mb-1">综合风险评分</p>
        <p className="text-3xl font-bold" style={{ color: RISK_COLORS[adjustedRiskLevel] }}>
          {adjustedRiskScore}
        </p>
        <span
          className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-bold text-white"
          style={{ backgroundColor: RISK_COLORS[adjustedRiskLevel] }}
        >
          {RISK_LABELS[adjustedRiskLevel]}
        </span>
        {adjustedRiskScore !== rawRiskScore && (
          <p className="text-[10px] text-gray-400 mt-1">原始风险分 {rawRiskScore}</p>
        )}
      </div>

      {/* 合规得分（A3：100 − 风险分） */}
      <div className="bg-white rounded-xl border border-emerald-200 p-4 text-center hover:shadow-md transition-shadow">
        <p className="text-xs text-gray-400 mb-1">合规得分</p>
        <p className="text-3xl font-bold text-emerald-600" data-testid="compliance-score">
          {complianceScore}
        </p>
        <span
          className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-bold"
          style={{ backgroundColor: '#10B98118', color: '#10B981' }}
        >
          {complianceScore >= 70 ? '合规良好' : complianceScore >= 40 ? '合规待提升' : '合规风险高'}
        </span>
        <p className="text-[10px] text-gray-400 mt-1">= 100 − 风险分{adjustedRiskScore !== rawRiskScore && `（调整后 ${adjustedRiskScore}）`}</p>
      </div>

      {/* 稽查概率 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:shadow-md transition-shadow">
        <p className="text-xs text-gray-400 mb-1">预计稽查概率</p>
        <p className={`text-3xl font-bold ${icRadar.predictedAuditProbability >= 0.8 ? 'text-red-500' : icRadar.predictedAuditProbability >= 0.4 ? 'text-amber-500' : 'text-emerald-500'}`}>
          {Math.round(icRadar.predictedAuditProbability * 100)}%
        </p>
        <span className="text-[10px] text-gray-400">未来12个月</span>
      </div>

      {/* 高危维度数 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:shadow-md transition-shadow">
        <p className="text-xs text-gray-400 mb-1">高危风险维度</p>
        <p className={`text-3xl font-bold ${highDims.length > 0 ? 'text-red-500' : 'text-emerald-500'}`}>
          {highDims.length}
        </p>
        <span className="text-[10px] text-gray-400">
          共 {dimEntries.length} 个维度
        </span>
      </div>

      {/* 估算财务影响 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 text-center hover:shadow-md transition-shadow">
        <p className="text-xs text-gray-400 mb-1">预估补税·罚款</p>
        <p className={`text-3xl font-bold ${overall_risk_score >= 40 ? 'text-red-500' : 'text-amber-500'}`}>
          {financialImpact.estimatedPenalty >= 10000
            ? `${(financialImpact.estimatedPenalty / 10000).toFixed(0)}万`
            : `${financialImpact.estimatedPenalty.toLocaleString()}`
          }
        </p>
        <span className="text-[10px] text-gray-400">
          基于风险评分估算
        </span>
      </div>
    </div>
  );

  // ══════════════════════════════════════════
  // 老板视角：核心风险聚焦（仅展示高危+中危）
  // ══════════════════════════════════════════
  const bossFocusedRisks = (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <div className="w-1 h-5 rounded-full bg-red-500" />
        <h3 className="text-base font-semibold text-gray-700">
          核心风险聚焦
          <span className="text-sm font-normal text-gray-400 ml-2">
            需优先关注的{((criticalDims.length > 0 ? 1 : 0) + (highDims.length > 0 ? 1 : 0))}个高危等级，共
            {criticalDims.length + highDims.length + mediumHighDims.length + mediumDims.length}个需关注维度
          </span>
        </h3>
      </div>
      {/* 严重风险维度 */}
      {criticalDims.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-red-600 font-bold mb-2 uppercase tracking-wide">
            ⛔ 立即处置 — 严重风险
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {criticalDims.map(([key, score]) => {
              const dimName = DIM_NAMES[key] || key;
              const dimDetail = dim_details[key] || { detail: '' };
              return (
                <BossRiskItem
                  key={key}
                  dimName={dimName}
                  score={score}
                  level="critical"
                  description={dimDetail.detail}
                  riskReason={dimDetail.risk_reason}
                  policyRef={dimDetail.policy_ref}
                  policyBasis={dimDetail.policy_basis}
                />
              );
            })}
          </div>
        </div>
      )}
      {/* 高危维度优先展示 */}
      {highDims.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-red-500 font-medium mb-2 uppercase tracking-wide">
            🔴 立即处理 — 高危
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {highDims.map(([key, score]) => {
              const dimName = DIM_NAMES[key] || key;
              const dimDetail = dim_details[key] || { detail: '' };
              return (
                <BossRiskItem
                  key={key}
                  dimName={dimName}
                  score={score}
                  level="high"
                  description={dimDetail.detail}
                  riskReason={dimDetail.risk_reason}
                  policyRef={dimDetail.policy_ref}
                  policyBasis={dimDetail.policy_basis}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* 中高风险维度 */}
      {mediumHighDims.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-orange-500 font-medium mb-2 uppercase tracking-wide">
            🟠 重点关注 — 中高危
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {mediumHighDims.map(([key, score]) => {
              const dimName = DIM_NAMES[key] || key;
              return (
                <div
                  key={key}
                  className="bg-white rounded-lg border border-gray-200 p-3 flex items-center justify-between hover:shadow-sm transition-shadow"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: RISK_COLORS.medium_high }} />
                    <span className="text-sm font-medium text-gray-700">{dimName}</span>
                  </div>
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: RISK_COLORS.medium_high + '18', color: RISK_COLORS.medium_high }}>
                    {score}分
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 中危维度 */}
      {mediumDims.length > 0 && (
        <div>
          <p className="text-xs text-amber-500 font-medium mb-2 uppercase tracking-wide">
            🟡 近期优化 — 中危
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {mediumDims.map(([key, score]) => {
              const dimName = DIM_NAMES[key] || key;
              return (
                <div
                  key={key}
                  className="bg-white rounded-lg border border-gray-200 p-3 flex items-center justify-between hover:shadow-sm transition-shadow"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: RISK_COLORS.medium }} />
                    <span className="text-sm font-medium text-gray-700">{dimName}</span>
                  </div>
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: RISK_COLORS.medium + '18', color: RISK_COLORS.medium }}>
                    {score}分
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 低危维度 — 已达标（折叠） */}
      {lowDims.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-emerald-500 font-medium uppercase tracking-wide">
            🟢 已达标 — {lowDims.length} 个维度处于健康状态
          </p>
        </div>
      )}
    </div>
  );

  // ══════════════════════════════════════════
  // 老板视角：决策建议
  // ══════════════════════════════════════════
  const bossActionGuidance = (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-100 p-5">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1 h-5 rounded-full bg-blue-600" />
        <h3 className="text-base font-semibold text-gray-800">决策建议</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-white rounded-lg border border-blue-100 p-3">
          <p className="text-sm font-medium text-blue-800 mb-1">合规整改优先级</p>
          <p className="text-xs text-gray-600">
            {adjustedRiskLevel === 'high' || adjustedRiskLevel === 'critical'
              ? '建议立即启动专项合规整改，优先处理四流匹配和私卡收款问题，30天内制定整改计划并执行。'
              : adjustedRiskLevel === 'medium' || adjustedRiskLevel === 'medium_high'
                ? '建议在下一季度前完成成本费用率优化和进销项匹配自查，聘请第三方财税顾问进行独立评估。'
                : '当前风险可控，建议保持季度的常态化合规审查，关注行业政策变化对企业税负的影响。'}
          </p>
        </div>
        <div className="bg-white rounded-lg border border-blue-100 p-3">
          <p className="text-sm font-medium text-blue-800 mb-1">税务筹划窗口</p>
          <p className="text-xs text-gray-600">
            {businessModel === 'asset_heavy'
              ? '充分利用加速折旧、研发加计扣除等重资产制造企业优惠政策，关注高新技术企业认定时机。'
              : '关注小微企业减半征收、服务类进项归集等轻资产服务企业专属政策，合理规划税前抵扣项。'}
          </p>
        </div>
      </div>
    </div>
  );

  // ══════════════════════════════════════════
  // 整改前后评分演化（A1）表格列
  // ══════════════════════════════════════════
  const trajectoryColumns: ColumnsType<RiskScoreTrajectory> = [
    {
      title: '评估日期',
      dataIndex: 'assessment_date',
      key: 'assessment_date',
      width: 100,
      render: (v: string) => (v ? v.slice(0, 10) : '—'),
    },
    {
      title: '整改前风险分',
      dataIndex: 'before_score',
      key: 'before_score',
      width: 100,
      align: 'center',
      render: (v: number | null) => (v != null ? v : '—'),
    },
    {
      title: '整改后风险分',
      dataIndex: 'after_score',
      key: 'after_score',
      width: 100,
      align: 'center',
      render: (v: number) => <span className="font-bold text-gray-800">{v}</span>,
    },
    {
      title: '分差',
      key: 'delta',
      width: 80,
      align: 'center',
      render: (_, row) => {
        if (row.before_score == null) return '—';
        const delta = Math.round((row.after_score - row.before_score) * 100) / 100;
        if (delta < 0) return <span className="text-emerald-600 font-medium">{delta} ↓</span>;
        if (delta > 0) return <span className="text-red-600 font-medium">+{delta} ↑</span>;
        return <span className="text-gray-400">0</span>;
      },
    },
    {
      title: '等级变化',
      dataIndex: 'level_jump',
      key: 'level_jump',
      width: 150,
      render: (v: string, row) => {
        const from = row.before_level ? RISK_LABELS[row.before_level] : '—';
        const to = RISK_LABELS[row.after_level] ?? row.after_level;
        return (
          <span className="text-xs">
            {from} → {to}
            {v === 'down' && <Tag color="success" className="ml-1">改善</Tag>}
            {v === 'up' && <Tag color="error" className="ml-1">恶化</Tag>}
            {v === 'same' && <Tag className="ml-1">持平</Tag>}
          </span>
        );
      },
    },
    {
      title: '来源',
      dataIndex: 'changed_by',
      key: 'changed_by',
      width: 90,
      render: (v: string) =>
        v === 'remediation' ? <Tag color="processing">整改完成</Tag> : <Tag>例行重评</Tag>,
    },
    {
      title: '原因',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
    },
  ];

  // ══════════════════════════════════════════
  return (
    <div className="space-y-6">
      {topBanner}
      {toolbar}

      {/* ────── 老板视角 ═══ */}
      {language === 'business' && (
        <>
          {/* 风险全局概览 — 4 个大 KPI 卡片 */}
          {bossOverviewCards}

          {/* 核心风险聚焦 — 高危 + 中危优先展示 */}
          {bossFocusedRisks}

          {/* 内控雷达（简化版 — 仅双轨仪表盘） */}
          <div className="rounded-2xl border border-gray-200 bg-white p-5">
            <h3 className="text-base font-semibold text-gray-700 mb-5">宏观内控雷达监测</h3>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="rounded-xl p-5 bg-gray-50">
                <h4 className="text-sm font-semibold mb-4 text-center text-gray-600">
                  实际成本费用率 vs 同行业最高警戒阈值
                </h4>
                <DualCostGauge data={icRadar.costGauge} isCritical={isCritical} />
              </div>
              <div className="rounded-xl p-5 bg-gray-50">
                <h4 className="text-sm font-semibold mb-4 text-center text-gray-600">
                  营业收入增长曲线 vs 增值税税负率下跌曲线
                </h4>
                <TaxBurdenElasticityChart data={icRadar.taxBurdenElasticity} isCritical={isCritical} />
              </div>
            </div>
          </div>

          {/* 业务总述 */}
          {result.business_narrative && (
            <BusinessOverview narrative={result.business_narrative} riskLevel={adjustedRiskLevel} />
          )}

          {/* 决策建议 */}
          {bossActionGuidance}

          {/* 整改前后评分演化（A1：整改/重评证据链） */}
          {trajectories.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-5 sm:p-6">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-5 rounded-full bg-blue-600" />
                <h3 className="text-base font-semibold text-gray-700">整改前后评分演化</h3>
                <span className="text-xs text-gray-400 ml-2">风险评分轨迹（整改完成 / 例行重评证据链）</span>
              </div>
              <TableContainer>
                <Table<RiskScoreTrajectory>
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 5, hideOnSinglePage: true }}
                  dataSource={trajectories}
                  columns={trajectoryColumns}
                  locale={{ emptyText: '暂无评分演化记录' }}
                />
              </TableContainer>
            </div>
          )}

          {/* 高压补充 — 损失框架 */}
          {isCritical && nbtData?.budge && (
            <div className="rounded-2xl border border-red-600 bg-red-500 p-5 sm:p-6">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-5 rounded-full bg-white" />
                <h3 className="text-base font-semibold text-white">损失框架对比分析</h3>
              </div>
              <div className="space-y-4">
                <div className="bg-red-600/40 rounded-xl p-4 border border-red-400/30">
                  <p className="text-sm text-white leading-relaxed whitespace-pre-line">
                    {nbtData.budge.loss_comparison}
                  </p>
                </div>
                <div className="bg-red-600/40 rounded-xl p-4 border border-red-400/30">
                  <h4 className="text-xs font-semibold text-red-200 mb-1 uppercase">破除逃避心理</h4>
                  <p className="text-sm text-red-100 leading-relaxed">
                    {nbtData.budge.rebuttal_narrative}
                  </p>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ────── 财务视角 ═══ */}
      {language === 'technical' && (
        <>
          {/* 财务风险明细总览 */}
          {/* 维度统计摘要 */}
          <div className="flex items-center gap-4 text-sm flex-wrap">
            {criticalDims.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS.critical }} />
                <span className="text-gray-600">{criticalDims.length} 个严重风险维度</span>
              </span>
            )}
            {highDims.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS.high }} />
                <span className="text-gray-600">{highDims.length} 个高风险维度</span>
              </span>
            )}
            {mediumHighDims.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS.medium_high }} />
                <span className="text-gray-600">{mediumHighDims.length} 个中高风险维度</span>
              </span>
            )}
            {mediumDims.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS.medium }} />
                <span className="text-gray-600">{mediumDims.length} 个中风险维度</span>
              </span>
            )}
            {lowDims.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLORS.low }} />
                <span className="text-gray-600">{lowDims.length} 个低风险维度</span>
              </span>
            )}
            <span className="text-xs text-gray-400 ml-auto">
              综合评分：<span className="font-bold" style={{ color: RISK_COLORS[adjustedRiskLevel] }}>{adjustedRiskScore}</span>
            </span>
          </div>

          {/* 宏观内控雷达监测区 — 完整版（含 NBT 预警） */}
          <div className="rounded-2xl border border-gray-200 bg-white p-5 sm:p-6">
            <h3 className="text-base font-semibold text-gray-700 mb-5">宏观内控雷达监测</h3>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="rounded-xl p-5 bg-gray-50">
                <h4 className="text-sm font-semibold mb-4 text-center text-gray-600">
                  实际成本费用率 vs 同行业最高警戒阈值
                </h4>
                <DualCostGauge data={icRadar.costGauge} isCritical={false} />
              </div>
              <div className="rounded-xl p-5 bg-gray-50">
                <h4 className="text-sm font-semibold mb-4 text-center text-gray-600">
                  营业收入增长曲线 vs 增值税税负率下跌曲线
                </h4>
                <TaxBurdenElasticityChart data={icRadar.taxBurdenElasticity} isCritical={false} />
              </div>
            </div>

            {isCritical && nbtData?.nudge && (
              <div className="mt-5 p-4 bg-red-50 rounded-xl border border-red-200">
                <p className="text-sm text-red-700 font-medium leading-relaxed">
                  {nbtData.nudge.risk_statement}
                </p>
                <p className="text-xs text-red-500 mt-2 leading-relaxed">
                  {nbtData.nudge.psychological_trigger}
                </p>
              </div>
            )}

            {nbtLoading && (
              <div className="mt-5 text-center">
                <span className="text-xs text-gray-400">正在加载行为干预分析...</span>
              </div>
            )}
          </div>

          {/* 7 维度技术详情网格 */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#64748b' }} />
              <h3 className="text-base font-semibold text-gray-700">七维度风险技术分析</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {dimEntries.length > 0 ? (
                dimEntries.map(([key, score]) => {
                  const level: RiskLevel = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low';
                  const dimName = DIM_NAMES[key] || key;
                  const dimDetail = dim_details[key] || { detail: '', technical_detail: '' };

                  return (
                    <RiskMapCard
                      key={key}
                      dimKey={key}
                      dimName={dimName}
                      score={score}
                      level={level}
                      detail={dimDetail.detail}
                      technicalDetail={dimDetail.technical_detail}
                      language="technical"
                      isCritical={isCritical}
                      riskReason={dimDetail.risk_reason}
                      policyRef={dimDetail.policy_ref}
                      policyBasis={dimDetail.policy_basis}
                    />
                  );
                })
              ) : (
                <div className="col-span-full">
                  <EmptyState text="暂无维度数据" />
                </div>
              )}
            </div>
          </div>

          {/* 四流匹配明细（可筛选未匹配项） */}
          <div className="rounded-2xl border border-gray-200 bg-white p-5 sm:p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#64748b' }} />
              <h3 className="text-base font-semibold text-gray-700">四流匹配明细</h3>
              <Switch
                className="ml-auto"
                checkedChildren="仅看未匹配"
                unCheckedChildren="全部明细"
                checked={onlyUnmatched}
                onChange={setOnlyUnmatched}
              />
            </div>
            <TableContainer>
              <Table<MatchDetailItem>
                rowKey={(record, index) => `${record.contract_no ?? record.invoice_no ?? 'row'}-${index}`}
                size="small"
                pagination={false}
                dataSource={
                  onlyUnmatched
                    ? matchDetails.filter((d) => d.match_status === 'unmatched')
                    : matchDetails
                }
                locale={{ emptyText: '暂无匹配明细数据' }}
                columns={[
                  {
                    title: '合同号',
                    dataIndex: 'contract_no',
                    key: 'contract_no',
                    render: (v: string | null | undefined) => v ?? '—',
                  },
                  {
                    title: '交易对手',
                    dataIndex: 'counterparty',
                    key: 'counterparty',
                    render: (v: string | null | undefined) => v ?? '—',
                  },
                  {
                    title: '合同金额',
                    dataIndex: 'contract_amount',
                    key: 'contract_amount',
                    align: 'right',
                    render: (v?: number) =>
                      typeof v === 'number' ? `¥${v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : '—',
                  },
                  {
                    title: '关联发票号',
                    dataIndex: 'invoice_no',
                    key: 'invoice_no',
                    render: (v: string | null | undefined) => v ?? '—',
                  },
                  {
                    title: '发票金额',
                    dataIndex: 'invoice_amount',
                    key: 'invoice_amount',
                    align: 'right',
                    render: (v?: number) =>
                      typeof v === 'number' && v > 0 ? `¥${v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : '—',
                  },
                  {
                    title: '差异金额',
                    dataIndex: 'diff_amount',
                    key: 'diff_amount',
                    align: 'right',
                    render: (v?: number) =>
                      typeof v === 'number' ? `¥${v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : '—',
                  },
                  {
                    title: '匹配状态',
                    dataIndex: 'match_status',
                    key: 'match_status',
                    width: 100,
                    render: (v?: string) =>
                      v === 'matched' ? <Tag color="success">已匹配</Tag> : <Tag color="error">未匹配</Tag>,
                  },
                ]}
              />
            </TableContainer>
          </div>

          {/* 财务影响量化分析 */}
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#64748b' }} />
              <h3 className="text-base font-semibold text-gray-700">财务影响量化分析</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-400 mb-1">预估补税额</p>
                <p className="text-2xl font-bold text-amber-600">
                  ¥{(financialImpact.estimatedTaxGap / 10000).toFixed(1)}万
                </p>
                <p className="text-[10px] text-gray-400 mt-1">基于申报收入5%估算</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-400 mb-1">预估罚款·滞纳金</p>
                <p className="text-2xl font-bold text-red-600">
                  ¥{(financialImpact.estimatedPenalty / 10000).toFixed(1)}万
                </p>
                <p className="text-[10px] text-gray-400 mt-1">
                  {overall_risk_score >= 70 ? '50%-5倍罚款 (高风险)' : overall_risk_score >= 40 ? '0.5-3倍罚款 (中风险)' : '0.5倍以下 (低风险)'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-400 mb-1">最大风险敞口</p>
                <p className="text-2xl font-bold text-red-700">
                  ¥{((financialImpact.estimatedTaxGap + financialImpact.estimatedPenalty) / 10000).toFixed(1)}万
                </p>
                <p className="text-[10px] text-gray-400 mt-1">补税 + 罚款合计</p>
              </div>
            </div>
          </div>

          {/* 损失框架（高压） */}
          {isCritical && nbtData?.budge && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-5 sm:p-6">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-5 rounded-full bg-red-500" />
                <h3 className="text-base font-semibold text-red-800">损失框架对比分析</h3>
              </div>
              <div className="space-y-3">
                <div className="bg-white rounded-xl p-4 border border-red-100">
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                    {nbtData.budge.loss_comparison}
                  </p>
                </div>
                <div className="bg-white rounded-xl p-4 border border-red-100">
                  <h4 className="text-xs font-semibold text-red-600 mb-1">破除逃避心理</h4>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    {nbtData.budge.rebuttal_narrative}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* 技术摘要 */}
          {result.technical_summary && (
            <div className="rounded-xl border border-gray-200 p-5" style={{ backgroundColor: '#f8fafc' }}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#64748b' }} />
                <h3 className="text-sm font-semibold text-gray-700">技术摘要</h3>
              </div>
              <pre className="text-xs text-gray-600 font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto max-h-96">
                {typeof result.technical_summary === 'string'
                  ? result.technical_summary
                  : JSON.stringify(result.technical_summary, null, 2)}
              </pre>
            </div>
          )}

          {/* ═══ SSF 博弈状态四象限定位 ═══ */}
          {enterpriseId && (
            <SSFQuadrantChart enterpriseId={enterpriseId} compact />
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// 业务总述组件
// ═══════════════════════════════════════
function BusinessOverview({ narrative, riskLevel }: { narrative: string; riskLevel: string }) {
  const parsed = useMemo(() => _parseRiskNarrative(narrative), [narrative]);

  const levelColor = RISK_COLORS[riskLevel as RiskLevel] || RISK_COLORS.low;
  const levelLabel = RISK_LABELS[riskLevel as RiskLevel] || riskLevel;

  // 风险等级对应的样式
  const isHigh = riskLevel === 'high' || riskLevel === 'critical';
  const headerGradient = isHigh
    ? 'from-red-600 to-rose-700'
    : riskLevel === 'medium' || riskLevel === 'medium_high'
      ? 'from-amber-500 to-orange-600'
      : 'from-emerald-500 to-teal-600';

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
      {/* ── 头部：企业名称 + 报告标题 ── */}
      <div className={`bg-gradient-to-r ${headerGradient} px-6 py-4`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="text-xs text-white/70 font-medium uppercase tracking-wide">
              财税合规风险评估报告
            </p>
            <h3 className="text-lg font-bold text-white mt-0.5">
              {parsed.title || '企业风险评估'}
            </h3>
          </div>
          <div className="flex items-center gap-3">
            <span className="px-3 py-1.5 bg-white/20 rounded-full text-sm font-bold text-white">
              {levelLabel}
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {/* ── 评分横幅 ── */}
        <div className="flex items-center gap-6 flex-wrap">
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-extrabold" style={{ color: levelColor }}>
              {parsed.riskScore || '—'}
            </span>
            <span className="text-sm text-gray-400">/ 100 分</span>
          </div>
          <div className="flex-1 min-w-[200px] max-w-md">
            <Progress
              percent={parsed.riskScore || 0}
              strokeColor={levelColor}
              trailColor="#f1f5f9"
              showInfo={false}
              size="small"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1.5">
              <span>低风险</span>
              <span className="font-medium text-gray-500">中等风险阈值 40</span>
              <span>高风险</span>
            </div>
          </div>
        </div>

        {/* ── 两栏：风险点 + 整改建议 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 风险点列表 */}
          <div className="bg-red-50/60 rounded-xl border border-red-100 p-4">
            <div className="flex items-center gap-2 mb-3">
              <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <h4 className="text-sm font-semibold text-red-700">
                {parsed.riskFlags.length > 0
                  ? `发现 ${parsed.riskFlags.length} 个风险点`
                  : '未发现明显风险点'}
              </h4>
            </div>
            {parsed.riskFlags.length > 0 ? (
              <ul className="space-y-2">
                {parsed.riskFlags.map((flag, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="mt-0.5 w-5 h-5 rounded-full bg-red-100 flex items-center justify-center shrink-0">
                      <span className="text-[10px] font-bold text-red-500">{i + 1}</span>
                    </span>
                    <span className="text-sm text-gray-700 leading-relaxed">{flag}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-emerald-700">经营状况良好，未发现明显财税合规风险。</p>
            )}
          </div>

          {/* 整改建议列表 */}
          <div className="bg-blue-50/60 rounded-xl border border-blue-100 p-4">
            <div className="flex items-center gap-2 mb-3">
              <svg className="w-4 h-4 text-blue-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <h4 className="text-sm font-semibold text-blue-700">
                {parsed.recommendations.length > 0
                  ? `${parsed.recommendations.length} 条整改建议`
                  : '整改建议'}
              </h4>
            </div>
            {parsed.recommendations.length > 0 ? (
              <ul className="space-y-2.5">
                {parsed.recommendations.map((rec, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="mt-0.5 w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                      <span className="text-[10px] font-bold text-blue-500">{i + 1}</span>
                    </span>
                    <span className="text-sm text-gray-700 leading-relaxed">{rec}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500">暂无具体整改建议，请持续关注风险指标变化。</p>
            )}
          </div>
        </div>

        {/* ── 纯文本原文（collapsible）── */}
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-gray-400 hover:text-gray-600 transition-colors select-none">
            查看完整评估原文
          </summary>
          <div className="mt-2 bg-slate-50 rounded-lg p-4 border border-slate-200">
            <pre className="text-xs text-slate-600 font-mono leading-relaxed whitespace-pre-wrap">
              {narrative}
            </pre>
          </div>
        </details>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// 老板视角高危风险条目组件
// ═══════════════════════════════════════
function BossRiskItem({
  dimName, score, level, description, riskReason, policyRef, policyBasis,
}: {
  dimName: string;
  score: number;
  level: RiskLevel;
  description: string;
  riskReason?: string;
  policyRef?: string;
  policyBasis?: string;
}) {
  const color = RISK_COLORS[level];
  return (
    <div
      className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
          <span className="text-sm font-semibold text-gray-700">{dimName}</span>
        </div>
        <span
          className="text-xs font-bold px-2 py-0.5 rounded-full"
          style={{ backgroundColor: color + '18', color }}
        >
          {score}分
        </span>
      </div>
      <p className="text-xs text-gray-500 line-clamp-2">{description || '暂无描述'}</p>
      {/* 简易进度条 */}
      <div className="mt-2 h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      {/* 政策依据折叠面板 */}
      {policyBasis && (
        <details
          className="mt-2.5 rounded-lg bg-slate-50/70 border border-slate-100 group"
        >
          <summary className="cursor-pointer text-[11px] font-medium text-slate-600 hover:text-slate-800 transition-colors select-none px-2.5 py-2 flex items-center justify-between gap-2">
            <span>政策依据</span>
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
    </div>
  );
}

export default RiskMap;
