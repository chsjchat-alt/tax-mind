import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Tooltip, Legend,
} from 'recharts';
import { Progress, Tag } from 'antd';
import { RISK_COLORS } from '@/types';
import { useChartHeight } from '@/hooks/useChartHeight';

// ── 六维偏差中文名 ──
const BIAS_NAMES: Record<string, string> = {
  control_desire: '掌控欲',
  loss_aversion: '损失厌恶',
  optimism_bias: '乐观偏差',
  control_illusion: '控制错觉',
  short_termism: '短期主义',
  defensiveness: '防御心理',
};

// ── 同行业同规模企业平均偏差参考值（fallback，后端未返回时使用） ──
const DEFAULT_PEER_AVERAGE: Record<string, number> = {
  control_desire: 48,
  loss_aversion: 45,
  optimism_bias: 45,
  control_illusion: 38,
  short_termism: 48,
  defensiveness: 42,
};

const BIAS_DESCRIPTIONS: Record<string, string> = {
  control_desire: '过度集中决策权，不愿下放财权。企业主对每一笔支出亲自审批，导致"一言堂"式财务管理。',
  loss_aversion: '对损失的敏感度远高于对收益的预期。宁可维持现状承担合规风险，也不愿投入整改成本。',
  optimism_bias: '过度乐观地低估被稽查概率。"这么多年都没事，以后也不会有事"的侥幸心理。',
  control_illusion: '错误估计自己对税务系统的掌控能力。相信通过"关系"可以摆平一切问题。',
  short_termism: '过分关注短期现金流，忽视长期合规建设。常见于高增长高负债的成长型企业。',
  defensiveness: '对外部建议持抵触态度，将合规要求视为"找茬"。防御心理导致信息不透明。',
};

// ═══════════════════════════════════════
// 模拟企业画像数据生成器
// 按行业 + 规模精准匹配 profile_benchmarks.json，生成合理偏差的个体企业数据
// ═══════════════════════════════════════

/** 企业规模分级 */
export type SizeTier = 'small' | 'medium' | 'large';

/** 行业→六维基准值映射（来源：profile_benchmarks.json） */
const BENCHMARK_DATA: Record<string, Record<SizeTier, Record<string, number>>> = {
  '批发零售': {
    small:  { control_desire:52, loss_aversion:48, optimism_bias:50, control_illusion:40, short_termism:55, defensiveness:42 },
    medium: { control_desire:45, loss_aversion:42, optimism_bias:42, control_illusion:35, short_termism:48, defensiveness:38 },
    large:  { control_desire:40, loss_aversion:35, optimism_bias:35, control_illusion:30, short_termism:40, defensiveness:30 },
  },
  '制造': {
    small:  { control_desire:62, loss_aversion:55, optimism_bias:48, control_illusion:50, short_termism:42, defensiveness:52 },
    medium: { control_desire:55, loss_aversion:48, optimism_bias:40, control_illusion:45, short_termism:38, defensiveness:48 },
    large:  { control_desire:50, loss_aversion:42, optimism_bias:32, control_illusion:40, short_termism:32, defensiveness:42 },
  },
  '建筑': {
    small:  { control_desire:58, loss_aversion:60, optimism_bias:55, control_illusion:52, short_termism:50, defensiveness:48 },
    medium: { control_desire:52, loss_aversion:55, optimism_bias:48, control_illusion:48, short_termism:45, defensiveness:44 },
    large:  { control_desire:48, loss_aversion:50, optimism_bias:42, control_illusion:44, short_termism:40, defensiveness:40 },
  },
  '电商': {
    small:  { control_desire:48, loss_aversion:42, optimism_bias:55, control_illusion:35, short_termism:62, defensiveness:38 },
    medium: { control_desire:42, loss_aversion:38, optimism_bias:48, control_illusion:32, short_termism:55, defensiveness:35 },
    large:  { control_desire:38, loss_aversion:32, optimism_bias:40, control_illusion:28, short_termism:48, defensiveness:30 },
  },
  '餐饮服务': {
    small:  { control_desire:55, loss_aversion:52, optimism_bias:58, control_illusion:42, short_termism:52, defensiveness:55 },
    medium: { control_desire:48, loss_aversion:48, optimism_bias:50, control_illusion:38, short_termism:48, defensiveness:50 },
    large:  { control_desire:42, loss_aversion:42, optimism_bias:42, control_illusion:34, short_termism:42, defensiveness:44 },
  },
};

/**
 * 根据年营收判定规模梯度
 *   small:  < 500万
 *   medium: 500万 – 5000万
 *   large:  > 5000万
 */
export function determineSizeTier(revenueAnnual: number): SizeTier {
  if (revenueAnnual < 5_000_000) return 'small';
  if (revenueAnnual <= 50_000_000) return 'medium';
  return 'large';
}

/**
 * 生成符合企业行业×规模的模拟六维偏差画像
 *
 * 数据来源：profile_benchmarks.json 行业基准值，叠加 ±8 个体随机偏差
 * 偏差使用确定性伪随机（基于 enterprise_id hash），保证同一企业多次生成结果一致
 */
export function generateSimulatedProfile(
  industry: string,
  sizeTier: SizeTier,
  enterpriseId?: string,
): { scores: Record<string, number>; peerAverage: Record<string, number> } {
  // 1. 查找行业基准；未知行业 fallback 到批发零售
  const industryData = BENCHMARK_DATA[industry] ?? BENCHMARK_DATA['批发零售'];
  // 2. 查规模基准；未知规模 fallback 到 medium
  const tierKey = industryData[sizeTier] ? sizeTier : 'medium';
  const base = industryData[tierKey];

  // 3. 基于 enterprise_id 生成确定性伪随机偏移（-8 ~ +8）
  const seed = enterpriseId
    ? enterpriseId.split('').reduce((s, c) => s + c.charCodeAt(0), 0)
    : Date.now() % 1000;

  const scores: Record<string, number> = {};
  for (const dim of Object.keys(base)) {
    // 确定性伪随机：seed × dim hash → 0~1 之间
    const dimHash = dim.split('').reduce((s, c) => s + c.charCodeAt(0), 0);
    const pseudo = ((seed * dimHash * 127 + 31) % 9973) / 9973;
    const offset = Math.round((pseudo - 0.5) * 16); // ±8
    const raw = (base[dim] ?? 45) + offset;
    scores[dim] = Math.max(0, Math.min(100, raw));
  }

  // 4. 同行均值 = 基准值本身
  const peerAverage: Record<string, number> = { ...base };

  return { scores, peerAverage };
}

// ═══════════════════════════════════════
// BiasRadarChart - 六维偏差雷达图
// 紫色粗实线=本企业画像，灰色虚线=同行均值
// ═══════════════════════════════════════
interface BiasRadarChartProps {
  scores: Record<string, number>;
  /** 同行业同规模企业各维度平均分 */
  peerAverage?: Record<string, number>;
}

export function BiasRadarChart({ scores, peerAverage }: BiasRadarChartProps) {
  const avg = peerAverage ?? DEFAULT_PEER_AVERAGE;

  const data = Object.keys(BIAS_NAMES).map((key) => ({
    dimension: BIAS_NAMES[key],
    '您的企业': scores[key] ?? 0,
    '同行均值': avg[key] ?? DEFAULT_PEER_AVERAGE[key] ?? 45,
    fullMark: 100,
  }));

  // 视口自适应：窄屏/低视口收缩高度，避免溢出
  const chartHeight = useChartHeight(420);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis
          dataKey="dimension"
          tick={{ fontSize: 12, fill: '#475569' }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fontSize: 10, fill: '#94a3b8' }}
        />

        {/* 您的企业 —— 紫色粗实线 */}
        <Radar
          name="您的企业"
          dataKey="您的企业"
          stroke="#7C3AED"
          fill="#7C3AED"
          fillOpacity={0.18}
          strokeWidth={3}
        />

        {/* 同行均值 —— 灰色虚线 */}
        <Radar
          name="同行均值"
          dataKey="同行均值"
          stroke="#94a3b8"
          fill="#94a3b8"
          fillOpacity={0.05}
          strokeWidth={1.2}
          strokeDasharray="3 5"
        />

        <Tooltip
          formatter={(v: number, name: string) => [`${v}分`, name]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
          iconType="line"
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// ═══════════════════════════════════════
// BiasCard - 单偏差展示卡片
// ═══════════════════════════════════════
interface BiasCardProps {
  biasKey: string;
  score: number;
  isDominant?: boolean;
  /** 同行业同规模该维度的基准分值 */
  peerAvg?: number;
}

export function BiasCard({ biasKey, score, isDominant = false, peerAvg }: BiasCardProps) {
  const name = BIAS_NAMES[biasKey] || biasKey;
  const description = BIAS_DESCRIPTIONS[biasKey] || '';
  const industryAvg = peerAvg ?? (DEFAULT_PEER_AVERAGE[biasKey] || 0);
  const diff = score - industryAvg;

  const level = score >= 70 ? 'high' as const : score >= 40 ? 'medium' as const : 'low' as const;
  const color = RISK_COLORS[level];

  return (
    <div
      className={`
        bg-white rounded-xl border p-4 transition-all
        ${isDominant ? 'ring-2 ring-purple-300 shadow-lg' : 'border-gray-200 hover:shadow-md'}
      `}
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: color }}
          />
          <h4 className="text-sm font-semibold text-gray-700">{name}</h4>
          {isDominant && (
            <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full font-medium">
              主导偏差
            </span>
          )}
        </div>
        <span
          className="text-xs font-bold px-1.5 py-0.5 rounded-full"
          style={{ backgroundColor: color + '18', color }}
        >
          {score}分
        </span>
      </div>

      {/* 进度条 + 行业对比 */}
      <Progress percent={score} strokeColor={color} showInfo={false} size="small" />

      <div className="flex items-center justify-between mt-1.5 mb-2">
        <span className="text-[10px] text-gray-400">
          同行业同规模平均 {industryAvg} 分
        </span>
        <span
          className={`text-[10px] font-medium ${diff > 0 ? 'text-red-500' : 'text-green-500'}`}
        >
          {diff > 0 ? '+' : ''}{diff.toFixed(0)} vs 平均
        </span>
      </div>

      {/* 描述 */}
      <p className="text-xs text-gray-600 leading-relaxed">
        {description}
      </p>
    </div>
  );
}

// ═══════════════════════════════════════
// ProfileSummary - 画像总结卡
// ═══════════════════════════════════════
interface ProfileSummaryProps {
  deviationIndex: number;
  dominantBiases: string[];
  businessNarrative: string;
  enterpriseName: string;
  baseline?: number;
}

function _cleanNarrative(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/[═╤╧]/g, '')
    .replace(/[🔴🟡🟢] /g, '')
    .replace(/█|░/g, '')
    .replace(/^\s*\d+\/\d+\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function _extractComboInterpretation(raw: string): string | null {
  if (!raw) return null;
  const m = raw.match(/决策模式解读[：:]\s*(.+?)(?:\n|$)/);
  return m ? m[1].trim() : null;
}

function _extractDimScores(raw: string): { name: string; score: number; desc: string; level: 'high' | 'medium' | 'low' }[] {
  if (!raw) return [];
  const section = raw.split('六维得分详情')[1]?.split('══')[0] || '';
  const items: { name: string; score: number; desc: string; level: 'high' | 'medium' | 'low' }[] = [];
  const re = /([\u4e00-\u9fa5]+)\s+(\d{1,3})\/100\s+(.+)/g;
  let m;
  while ((m = re.exec(section)) !== null) {
    const score = parseInt(m[2], 10);
    items.push({
      name: m[1].trim(),
      score,
      desc: m[3].trim(),
      level: score >= 70 ? 'high' as const : score >= 40 ? 'medium' as const : 'low' as const,
    });
  }
  return items;
}

function _extractInterventions(raw: string): { bias: string; text: string }[] {
  if (!raw) return [];
  const section = raw.split('心理干预建议')[1]?.split('──')[0] || '';
  const items: { bias: string; text: string }[] = [];
  const re = /◆\s*(.+?)[：:]\s*\n\s*(.+?)(?=\n◆|\n\n|$)/gs;
  let m;
  while ((m = re.exec(section)) !== null) {
    items.push({ bias: m[1].trim(), text: m[2].trim() });
  }
  return items;
}

export function ProfileSummary({
  deviationIndex,
  dominantBiases,
  businessNarrative,
  enterpriseName,
  baseline = 43,
}: ProfileSummaryProps) {
  const aboveBaseline = deviationIndex > baseline;
  const diffFromBaseline = Math.abs(deviationIndex - baseline);
  const level = deviationIndex >= 70 ? 'high' as const
    : deviationIndex >= 40 ? 'medium' as const
    : 'low' as const;
  const color = RISK_COLORS[level];

  const decisionModeLabel = level === 'high' ? '高风险决策模式'
    : level === 'medium' ? '中等风险决策模式'
    : '相对理性决策模式';

  const dominantNames = dominantBiases
    .map((b) => BIAS_NAMES[b] || b)
    .filter(Boolean);

  // 叙事衍生内容（仅在 businessNarrative 非空时计算）
  const comboNarrative = businessNarrative ? _extractComboInterpretation(businessNarrative) : null;
  const dimScores = businessNarrative ? _extractDimScores(businessNarrative) : [];
  const interventions = businessNarrative ? _extractInterventions(businessNarrative) : [];

  // 生成一句话洞察
  const oneLiner = level === 'high'
    ? `${enterpriseName}的财税决策受认知偏差影响显著，需重点关注${dominantNames.slice(0, 2).join('和')}两类心理倾向。`
    : level === 'medium'
    ? `${enterpriseName}在${dominantNames.slice(0, 2).join('和')}方面存在一定偏差，建议主动干预。`
    : `${enterpriseName}整体决策模式较为理性，认知偏差在可控范围内。`;

  return (
    <div
      className="relative overflow-hidden rounded-2xl border-2 p-6 sm:p-8"
      style={{ borderColor: color + '40', backgroundColor: color + '06' }}
    >
      {/* 顶部装饰线 */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{ backgroundColor: color }}
      />

      <div className="space-y-6">
        {/* ── 标题区 ── */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-lg font-bold text-gray-800">
              {enterpriseName} · 决策心理画像
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              基于行为经济学六维偏差模型自动分析
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Tag color={level === 'high' ? 'red' : level === 'medium' ? 'orange' : 'green'}>
              {decisionModeLabel}
            </Tag>
            <span className="text-3xl font-extrabold" style={{ color }}>
              {deviationIndex}
            </span>
            <span className="text-xs text-gray-400">/100</span>
          </div>
        </div>

        {/* ── 偏差指数进度条 ── */}
        <div className="bg-white/80 rounded-xl border border-gray-100 p-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-gray-500">综合偏差指数</span>
            <span className={`text-xs font-semibold ${aboveBaseline ? 'text-red-600' : 'text-green-600'}`}>
              {aboveBaseline ? '高于' : '低于'}同行业均值 {baseline}（{aboveBaseline ? '+' : '-'}{diffFromBaseline.toFixed(0)} 分）
            </span>
          </div>
          <Progress percent={deviationIndex} strokeColor={color} showInfo={false} size="small" />
          <div className="flex justify-between text-[10px] text-gray-400 mt-1">
            <span>0</span>
            <span className="font-semibold text-gray-500">基线 {baseline}</span>
            <span>100</span>
          </div>
        </div>

        {/* ── 主导偏差标签 ── */}
        {dominantNames.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-gray-500">主导偏差</span>
            {dominantNames.map((name, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 bg-purple-50 border border-purple-200 text-purple-700 px-3 py-1 rounded-full text-xs font-medium"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
                {name}
              </span>
            ))}
          </div>
        )}

        {/* ═══════════════════════════════════════
            「这意味着」— 叙事化决策心理解读
            —— 仅在 businessNarrative 非空时显示 ═══════════════════════════════════════ */}
        {businessNarrative && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          {/* 头部 */}
          <div className="flex items-center gap-2.5 px-5 py-3.5 bg-gradient-to-r from-purple-50 via-indigo-50 to-white border-b border-gray-100">
            <svg className="w-5 h-5 text-purple-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span className="text-sm font-bold text-gray-700">这意味着</span>
          </div>

          <div className="p-5 space-y-5">
            {/* 1. 一句话洞察 */}
            <div className="flex items-start gap-3">
              <div className="mt-0.5 w-1 h-1 rounded-full bg-purple-400 shrink-0" style={{ marginTop: 7 }} />
              <p className="text-sm text-gray-700 leading-relaxed">
                {oneLiner}
              </p>
            </div>

            {/* 2. 决策模式解读（组合偏差叙事） */}
            {comboNarrative && (
              <div className="relative bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200/80 rounded-xl p-5">
                {/* 左侧装饰条 */}
                <div className="absolute left-0 top-3 bottom-3 w-1 bg-amber-400 rounded-r-full" />
                <div className="pl-3">
                  <p className="text-[11px] font-semibold text-amber-600 uppercase tracking-wide mb-2">
                    决策模式解读
                  </p>
                  <p className="text-sm text-amber-900 leading-relaxed">
                    {comboNarrative}
                  </p>
                </div>
              </div>
            )}

            {/* 3. 六维偏差得分概览 —— 横向紧凑进度条 */}
            {dimScores.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  六维偏差得分
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {dimScores.map((dim) => {
                    const dimColor = RISK_COLORS[dim.level];
                    const barBg = dim.level === 'high' ? 'bg-red-50' : dim.level === 'medium' ? 'bg-orange-50' : 'bg-green-50';
                    return (
                      <div
                        key={dim.name}
                        className={`${barBg} rounded-lg px-3.5 py-2.5 border border-gray-100 flex items-center gap-3`}
                      >
                        <span className="text-xs font-medium text-gray-600 w-14 shrink-0">{dim.name}</span>
                        <div className="flex-1 min-w-0">
                          <Progress
                            percent={dim.score}
                            strokeColor={dimColor}
                            showInfo={false}
                            size="small"
                            strokeWidth={5}
                          />
                        </div>
                        <span className="text-xs font-bold w-8 text-right shrink-0" style={{ color: dimColor }}>
                          {dim.score}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 4. 干预建议卡片 */}
            {interventions.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  针对性干预建议
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {interventions.map((item) => (
                    <div
                      key={item.bias}
                      className="bg-blue-50/60 border border-blue-100 rounded-lg p-3.5 flex items-start gap-2.5"
                    >
                      <div className="mt-0.5 w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                        <svg className="w-3 h-3 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-blue-700 mb-0.5">{item.bias}</p>
                        <p className="text-xs text-blue-800/80 leading-relaxed">{item.text}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 5. 完整分析文本（collapsible，默认收起）—— 仅在 businessNarrative 非空时显示 */}
            {businessNarrative && (
              <details className="group">
                <summary className="cursor-pointer text-xs font-medium text-gray-400 hover:text-gray-600 transition-colors select-none">
                  查看完整分析文本
                </summary>
                <div className="mt-2 bg-slate-50 rounded-lg p-4 border border-slate-200">
                  <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-line">
                    {_cleanNarrative(businessNarrative)}
                  </p>
                </div>
              </details>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// DisclaimerBanner - 免责声明横幅
// ═══════════════════════════════════════
export function DisclaimerBanner() {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="text-amber-500 text-lg shrink-0 mt-0.5">⚠</div>
        <div>
          <p className="text-sm font-semibold text-amber-800 mb-1">免责声明</p>
          <p className="text-xs text-amber-700 leading-relaxed">
            本心理画像基于行为经济学模型生成，仅用于辅助决策参考，
            不构成任何形式的心理诊断或法律建议。所有评分均基于输入的模拟数据通过规则引擎计算得出，
            不依赖大模型进行主观判断。建议结合专业税务顾问的意见进行综合决策。
          </p>
        </div>
      </div>
    </div>
  );
}

// 导出工具函数
export { BIAS_NAMES, DEFAULT_PEER_AVERAGE, BIAS_DESCRIPTIONS };
