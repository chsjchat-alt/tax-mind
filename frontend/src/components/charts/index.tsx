import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Legend, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell,
  LineChart, Line, Area, AreaChart, ComposedChart, ReferenceLine,
} from 'recharts';
import { RISK_COLORS, BIAS_LABELS } from '@/types';
import type { SnowballTimePoint, TaxBurdenElasticityData, CostGaugeData } from '@/types';

// 风险雷达图（7维度）
const RADAR_DIMENSIONS_CN: Record<string, string> = {
  private_card_ratio: '私卡收款',
  cost_deviation: '成本偏离',
  tax_burden_deviation: '税负率偏离',
  four_flow_mismatch: '四流不匹配',
  four_flow_match: '四流匹配',           // 后端实际返回的 key
  invoice_bank_mismatch: '票银不匹配',
  large_personal_transfer: '大额公转私',
  input_output_imbalance: '进销项失衡',
};

export function RiskRadar({ scores }: { scores: Record<string, number> }) {
  const data = Object.entries(scores).map(([key, value]) => ({
    dimension: RADAR_DIMENSIONS_CN[key] || key,
    score: value,
    fullMark: 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={320}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: '#64748b' }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
        <Radar name="风险评分" dataKey="score" stroke="#1A56DB" fill="#1A56DB" fillOpacity={0.25} />
        <Tooltip formatter={(v: number) => [`${v}分`, '风险评分']} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// 七维柱状图
export function RiskBarChart({ scores }: { scores: Record<string, number> }) {
  const data = Object.entries(scores)
    .map(([key, value]) => ({
      name: RADAR_DIMENSIONS_CN[key] || key,
      score: value,
      color: value >= 70 ? RISK_COLORS.high : value >= 40 ? RISK_COLORS.medium : RISK_COLORS.low,
    }))
    .sort((a, b) => b.score - a.score);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} width={80} />
        <Tooltip formatter={(v: number) => [`${v}分`, '风险评分']} />
        <Bar dataKey="score" radius={[0, 4, 4, 0]}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// 四流匹配度环形进度条
export function FourFlowGauge({ score, size = 120 }: { score: number; size?: number }) {
  const color = score >= 85 ? RISK_COLORS.low : score >= 65 ? RISK_COLORS.medium : RISK_COLORS.high;
  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="45" fill="none" stroke="#e2e8f0" strokeWidth="10" />
        <circle
          cx="60" cy="60" r="45" fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
        <text x="60" y="55" textAnchor="middle" fontSize="22" fontWeight="bold" fill={color}>
          {Math.round(score)}
        </text>
        <text x="60" y="75" textAnchor="middle" fontSize="10" fill="#94a3b8">匹配度</text>
      </svg>
    </div>
  );
}

export function ProfileRadarChart({ scores }: { scores: Record<string, number> }) {
  const data = Object.entries(scores).map(([key, value]) => ({
    dimension: BIAS_LABELS[key] || key,
    score: value,
    fullMark: 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={380}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12, fill: '#475569' }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
        <Radar name="偏差评分" dataKey="score" stroke="#7C3AED" fill="#7C3AED" fillOpacity={0.2} />
        <Tooltip formatter={(v: number) => [`${v}分`, '偏差评分']} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// 模拟器双路径对比图
export function SimulationComparisonChart({ timePoints }: {
  timePoints: { year: number; hidden_cumulative: number; penalty_exposure: number; audit_probability: number }[];
}) {
  const data = timePoints.map((tp) => ({
    year: `第${tp.year}年`,
    '隐匿收入(万)': +(tp.hidden_cumulative / 10000).toFixed(0),
    '罚款敞口(万)': +(tp.penalty_exposure / 10000).toFixed(0),
    '稽查概率(%)': +(tp.audit_probability * 100).toFixed(1),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="year" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="left" tick={{ fontSize: 11 }} label={{ value: '金额(万)', position: 'insideLeft', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} label={{ value: '概率(%)', position: 'insideRight', fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Area yAxisId="left" type="monotone" dataKey="隐匿收入(万)" stroke="#F59E0B" fill="#F59E0B" fillOpacity={0.1} strokeWidth={2} />
        <Area yAxisId="left" type="monotone" dataKey="罚款敞口(万)" stroke="#EF4444" fill="#EF4444" fillOpacity={0.1} strokeWidth={2} />
        <Line yAxisId="right" type="monotone" dataKey="稽查概率(%)" stroke="#1A56DB" strokeWidth={2} dot={{ r: 4 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// 风险趋势折线图
export function RiskTrendChart({ assessments }: {
  assessments: { date: string; score: number; level: string }[];
}) {
  const data = assessments
    .map((a) => ({
      date: a.date?.slice(0, 10) || '',
      score: a.score,
      level: a.level,
    }))
    .reverse();

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(v: number) => [`${v}分`, '风险评分']}
          labelFormatter={(label) => `日期: ${label}`}
        />
        <Line
          type="monotone"
          dataKey="score"
          name="风险评分"
          stroke="#1A56DB"
          strokeWidth={2}
          dot={{ r: 5, fill: '#1A56DB' }}
          activeDot={{ r: 7, stroke: '#1A56DB', strokeWidth: 2, fill: '#fff' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// 风险等级分布饼图
export function RiskPieChart({ low = 0, medium = 0, high = 0 }: { low: number; medium: number; high: number }) {
  const data = [
    { name: '低风险', value: low, fill: RISK_COLORS.low },
    { name: '中风险', value: medium, fill: RISK_COLORS.medium },
    { name: '高风险', value: high, fill: RISK_COLORS.high },
  ].filter((d) => d.value > 0);

  if (data.length === 0) return <p className="text-gray-400 text-sm text-center py-10">暂无数据</p>;

  return (
    <div className="flex items-center gap-4">
      <div className="flex gap-3">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1.5 text-sm">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: d.fill }} />
            <span className="text-gray-600">{d.name}:</span>
            <span className="font-semibold">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// 双轨仪表盘：成本费用率 vs 行业最高警戒阈值
// ═══════════════════════════════════════════════════════

interface DualCostGaugeProps {
  data: CostGaugeData;
  isCritical: boolean;
}

export function DualCostGauge({ data, isCritical }: DualCostGaugeProps) {
  const { actualCostRate, industryCostRate, warningThreshold, deviation, severity } = data;

  // 圆弧参数
  const radius = 70;
  const circumference = 2 * Math.PI * radius * 0.75; // 3/4 圆弧
  const maxValue = Math.max(warningThreshold, actualCostRate, 100);

  // 实际值在弧上的百分比
  const actualPct = Math.min(actualCostRate / maxValue, 1);
  const thresholdPct = Math.min(warningThreshold / maxValue, 1);

  const gaugeColor = severity === 'severe'
    ? '#EF4444'
    : severity === 'moderate'
      ? '#F59E0B'
      : '#10B981';

  // 阈值警示色（固定红色系，与实际值颜色明显区分）
  const thresholdColor = '#E53E3E';

  return (
    <div className="flex flex-col items-center">
      {/* ═══ 上方：关键数据并排展示 ═══ */}
      <div className="grid grid-cols-2 gap-3 w-full max-w-[220px] mb-2">
        {/* 实际成本费用率 */}
        <div className="text-center bg-white border rounded-lg py-2 px-3 shadow-sm">
          <p className={`text-[11px] font-medium mb-0.5 ${isCritical ? 'text-red-300' : 'text-gray-400'}`}>
            实际成本费用率
          </p>
          <p
            className="text-xl font-extrabold"
            style={{ color: isCritical ? '#EF4444' : gaugeColor }}
          >
            {actualCostRate.toFixed(1)}%
          </p>
        </div>
        {/* 最高警戒阈值 */}
        <div className="text-center bg-white border border-red-200 rounded-lg py-2 px-3 shadow-sm">
          <p className="text-[11px] font-medium text-gray-400 mb-0.5">
            最高警戒阈值
          </p>
          <p className="text-xl font-extrabold" style={{ color: thresholdColor }}>
            {warningThreshold.toFixed(1)}%
          </p>
        </div>
      </div>

      {/* ═══ 中间：环形图 ═══ */}
      <div className="relative" style={{ width: 200, height: 170 }}>
        <svg viewBox="0 0 200 180" className="w-full h-full">
          {/* 背景弧 */}
          <path
            d="M 20 155 A 70 70 0 0 1 180 155"
            fill="none"
            stroke={isCritical ? '#7f1d1d' : '#e2e8f0'}
            strokeWidth="12"
            strokeLinecap="round"
          />
          {/* 行业基准弧 */}
          <path
            d="M 20 155 A 70 70 0 0 1 180 155"
            fill="none"
            stroke={isCritical ? '#dc2626' : '#94a3b8'}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${circumference * thresholdPct} ${circumference}`}
            strokeDashoffset={circumference * 0.25}
            opacity={0.5}
          />
          {/* 实际值弧 */}
          <path
            d="M 20 155 A 70 70 0 0 1 180 155"
            fill="none"
            stroke={isCritical ? '#EF4444' : gaugeColor}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${circumference * actualPct} ${circumference}`}
            strokeDashoffset={circumference * 0.25}
            style={{ transition: 'stroke-dashoffset 1s ease, stroke-dasharray 1s ease' }}
          />
          {/* 警戒线标记 */}
          <circle
            cx={20 + 160 * thresholdPct}
            cy={155 - 70 * Math.sin(Math.PI * thresholdPct)}
            r="5"
            fill={isCritical ? '#fca5a5' : thresholdColor}
            stroke="#fff"
            strokeWidth="2"
          />
        </svg>

        {/* 中央：行业基准（精简） */}
        <div className="absolute bottom-5 left-0 right-0 text-center">
          <p className={`text-[10px] ${isCritical ? 'text-red-300' : 'text-gray-400'}`}>
            行业基准
          </p>
          <p className={`text-sm font-semibold ${isCritical ? 'text-red-200' : 'text-gray-500'}`}>
            {industryCostRate.toFixed(1)}%
          </p>
        </div>
      </div>

      {/* ═══ 下方：偏离信息 ═══ */}
      <div className="flex items-center gap-2 mt-2">
        <span
          className="inline-block w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: gaugeColor }}
        />
        <span className={`text-xs font-medium ${isCritical ? 'text-red-300' : 'text-gray-500'}`}>
          偏离 {deviation > 0 ? '+' : ''}{deviation.toFixed(1)}pp
          {deviation > 5 ? ' · 已超警戒' : ''}
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// 税负弹性系数双轨图：营业收入增长 vs 税负率下跌
// ═══════════════════════════════════════════════════════

interface TaxBurdenElasticityChartProps {
  data: TaxBurdenElasticityData[];
  isCritical: boolean;
}

export function TaxBurdenElasticityChart({ data, isCritical }: TaxBurdenElasticityChartProps) {
  const chartData = data.map((d) => ({
    period: d.period,
    '收入增长率(%)': d.revenueGrowth,
    '实际税负率(%)': d.taxBurdenRate,
    '期望税负率(%)': d.expectedTaxBurden,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={isCritical ? '#7f1d1d33' : '#f1f5f9'}
          />
          <XAxis
            dataKey="period"
            tick={{ fontSize: 11, fill: isCritical ? '#fca5a5' : '#64748b' }}
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11, fill: isCritical ? '#fca5a5' : '#64748b' }}
            label={{
              value: '增长率 (%)',
              position: 'insideTopLeft',
              offset: -5,
              style: { fontSize: 10, fill: '#94a3b8' },
            }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 'auto']}
            tick={{ fontSize: 11, fill: isCritical ? '#fca5a5' : '#64748b' }}
            label={{
              value: '税负率 (%)',
              position: 'insideTopRight',
              offset: -5,
              style: { fontSize: 10, fill: '#94a3b8' },
            }}
          />
          <Tooltip
            contentStyle={isCritical ? { backgroundColor: '#450a0a', border: '1px solid #7f1d1d', color: '#fca5a5' } : undefined}
            formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name]}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          />
          {/* 收入增长率柱状图 */}
          <Bar
            yAxisId="left"
            dataKey="收入增长率(%)"
            fill={isCritical ? '#dc2626' : '#1A56DB'}
            fillOpacity={isCritical ? 0.8 : 0.3}
            radius={[4, 4, 0, 0]}
            barSize={32}
          />
          {/* 实际税负率曲线 */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="实际税负率(%)"
            stroke={isCritical ? '#EF4444' : '#EF4444'}
            strokeWidth={2.5}
            dot={{ r: 5, fill: isCritical ? '#EF4444' : '#EF4444', stroke: '#fff', strokeWidth: 2 }}
            activeDot={{ r: 7 }}
          />
          {/* 期望税负率参考线 */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="期望税负率(%)"
            stroke={isCritical ? '#f87171' : '#10B981'}
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ r: 4, fill: isCritical ? '#f87171' : '#10B981', stroke: '#fff', strokeWidth: 1 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      {isCritical && (
        <p className="text-xs text-red-400 mt-1 text-center font-medium">
          弹性系数失衡：收入增长而税负率持续下跌，触发稽查预警
        </p>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// 指数级雪球对比图：税金本体+倍数罚金+个税穿透+复利滞纳金
// ═══════════════════════════════════════════════════════

interface ExponentialSnowballChartProps {
  data: SnowballTimePoint[];
}

export function ExponentialSnowballChart({ data }: ExponentialSnowballChartProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[320px] text-sm text-gray-400">
        暂无模拟数据
      </div>
    );
  }

  const chartData = data.map((tp) => ({
    label: tp.period === '6months' ? '6个月' : tp.period === '1year' ? '1年' : '3年',
    '路径A·指数雪球(万)': Math.round(tp.path_a_snowball / 10000),
    '路径B·合规整改(万)': Math.round(tp.path_b_cost / 10000),
    months: tp.months_elapsed,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={360}>
        <ComposedChart data={chartData} margin={{ top: 15, right: 20, left: 15, bottom: 5 }}>
          <defs>
            {/* 路径A：深红渐变 */}
            <linearGradient id="snowballGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#EF4444" stopOpacity={0.5} />
              <stop offset="40%" stopColor="#B91C1C" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#7F1D1D" stopOpacity={0.05} />
            </linearGradient>
            {/* 路径B：安全绿渐变 */}
            <linearGradient id="safeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10B981" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#10B981" stopOpacity={0.02} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />

          <XAxis
            dataKey="label"
            tick={{ fontSize: 12, fill: '#64748b', fontWeight: 500 }}
            axisLine={{ stroke: '#e2e8f0' }}
          />

          <YAxis
            tick={{ fontSize: 11, fill: '#64748b' }}
            label={{
              value: '万元',
              position: 'insideTopLeft',
              offset: -5,
              style: { fontSize: 11, fill: '#94a3b8' },
            }}
          />

          <Tooltip
            formatter={(v: number, name: string) => [
              `${v.toLocaleString()} 万元`,
              name === '路径A·指数雪球(万)' ? '税金+罚金+个税+滞纳金' : '合规整改投入',
            ]}
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            }}
          />

          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          />

          {/* 路径A：指数雪球（深红面积 + 深红线） */}
          <Area
            type="monotone"
            dataKey="路径A·指数雪球(万)"
            stroke="#EF4444"
            strokeWidth={2.5}
            fill="url(#snowballGradient)"
            name="路径A·指数雪球(万)"
            dot={false}
            activeDot={{ r: 6, fill: '#EF4444', stroke: '#fff', strokeWidth: 2 }}
          />

          {/* 路径B：合规整改（安全绿虚线） */}
          <Line
            type="monotone"
            dataKey="路径B·合规整改(万)"
            stroke="#10B981"
            strokeWidth={3}
            strokeDasharray="6 3"
            dot={{ r: 6, fill: '#10B981', stroke: '#fff', strokeWidth: 2 }}
            activeDot={{ r: 8, fill: '#10B981' }}
            name="路径B·合规整改(万)"
          />

          {/* 3年时间点垂直参考线 */}
          <ReferenceLine
            x="3年"
            stroke="#94a3b8"
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* 图例说明 */}
      <div className="flex items-center justify-center gap-6 mt-3 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-4 rounded bg-red-500 inline-block opacity-40" />
          <span className="text-gray-500">
            路径A 指数雪球（本金+罚金+个税穿透+滞纳金）
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0.5 bg-green-500 inline-block border-dashed" style={{ borderTop: '2px dashed #10B981' }} />
          <span className="text-gray-500">路径B 合规整改（低平安全线）</span>
        </span>
      </div>
    </div>
  );
}
