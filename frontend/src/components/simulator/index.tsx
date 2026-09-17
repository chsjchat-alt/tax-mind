import { useEffect, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
// ═══════════════════════════════════════
// TrudgeToolbox - Trudge 救赎工具箱 (P3)
// ═══════════════════════════════════════
interface TrudgeToolboxProps {
  enterpriseId: string;
  annualRevenue: number;
  totalTaxDue?: number;
  overdueDays?: number;
}

export function TrudgeToolbox({
  enterpriseId,
  annualRevenue: _annualRevenue,
  totalTaxDue: initTaxDue,
  overdueDays: initOverdueDays,
}: TrudgeToolboxProps) {
  const [_reportLoading, setReportLoading] = useState(false);
  const [report, setReport] = useState<{
    report_id: string;
    markdown_content: string;
    findings_summary: { total: number; high: number; medium: number; low: number; overall_rating: string };
    compliance_advice: string[];
  } | null>(null);
  const [reportModal, setReportModal] = useState(false);

  const [_installLoading, setInstallLoading] = useState(false);
  const [installData, setInstallData] = useState<{
    total_tax_due: number;
    late_fee_daily: number;
    lump_sum: Record<string, unknown>;
    installments: Record<string, unknown>[];
    recommendation: string;
    cash_flow_analysis: string;
  } | null>(null);

  // 一次性加载两个工具数据
  const loadToolbox = async () => {
    if (!enterpriseId) return;
    setReportLoading(true);
    setInstallLoading(true);
    try {
      const res = await import('@/api').then(m =>
        m.trudgeApi.getSelfAuditReport(enterpriseId)
      );
      setReport((res.data.data ?? null) as unknown as typeof report);
    } catch { setReport(null); } finally { setReportLoading(false); }
    try {
      const res = await import('@/api').then(m =>
        m.trudgeApi.getInstallmentSimulation(enterpriseId, {
          total_tax_due: initTaxDue,
          overdue_days: initOverdueDays,
        })
      );
      setInstallData(res.data.data ?? null);
    } catch { setInstallData(null); } finally { setInstallLoading(false); }
  };

  if (!report && !installData) {
    return (
      <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl border border-green-200 p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ToolOutlined className="text-green-600" />
            <span className="text-sm font-semibold text-gray-700">Trudge 救赎工具箱</span>
          </div>
          <Button
            type="primary"
            size="small"
            ghost
            onClick={loadToolbox}
            icon={<DownloadOutlined />}
          >
            加载工具箱
          </Button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          一键生成自查报告 + 分期补税模拟，帮助企业制定合规整改路线图
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <ToolOutlined className="text-green-600" />
        <span className="text-sm font-semibold text-gray-700">Trudge 救赎工具箱</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* ── 自查报告 ── */}
        {report && (
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-3">
              <FileTextOutlined className="text-blue-500" />
              <span className="text-sm font-semibold text-gray-700">自查报告</span>
              <span className="text-[10px] text-gray-400 ml-auto">{report.report_id}</span>
            </div>

            {/* 摘要数字 */}
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="bg-red-50 rounded-lg p-2 text-center">
                <p className="text-lg font-bold text-red-600">{report.findings_summary.high}</p>
                <p className="text-[10px] text-red-500">高风险</p>
              </div>
              <div className="bg-amber-50 rounded-lg p-2 text-center">
                <p className="text-lg font-bold text-amber-600">{report.findings_summary.medium}</p>
                <p className="text-[10px] text-amber-500">中风险</p>
              </div>
              <div className="bg-blue-50 rounded-lg p-2 text-center">
                <p className="text-lg font-bold text-blue-600">{report.findings_summary.low}</p>
                <p className="text-[10px] text-blue-500">低风险</p>
              </div>
            </div>

            <p className="text-xs text-gray-500 mb-2">{report.findings_summary.overall_rating}</p>

            <div className="flex gap-2">
              <Button
                type="primary"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => setReportModal(true)}
              >
                查看完整报告
              </Button>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={() => {
                  const blob = new Blob([report.markdown_content], { type: 'text/markdown' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `${report.report_id}.md`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                下载 MD
              </Button>
            </div>

            {/* 报告弹窗 */}
            <Modal
              title={
                <span className="flex items-center gap-2">
                  <FileTextOutlined className="text-blue-500" />
                  {report.report_id} · 企业税务合规自查报告
                </span>
              }
              open={reportModal}
              onCancel={() => setReportModal(false)}
              footer={
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 flex-1">
                    基于合规扫描 findings 自动生成的 Markdown 报告
                  </span>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={() => {
                      const blob = new Blob([report.markdown_content], { type: 'text/markdown' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${report.report_id}.md`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    下载原始 MD
                  </Button>
                  <Button size="small" onClick={() => setReportModal(false)}>关闭</Button>
                </div>
              }
              width={800}
            >
              <div className="max-h-[65vh] overflow-y-auto px-2">
                <style>{`
                  .report-content h1 { font-size: 1.5rem; font-weight: 700; color: #1f2937; border-bottom: 3px solid #3b82f6; padding-bottom: 0.5rem; margin-bottom: 1rem; }
                  .report-content h2 { font-size: 1.15rem; font-weight: 600; color: #374151; margin-top: 1.5rem; margin-bottom: 0.75rem; padding-left: 0.5rem; border-left: 3px solid #3b82f6; }
                  .report-content h3 { font-size: 1rem; font-weight: 600; color: #4b5563; margin-top: 1.25rem; margin-bottom: 0.5rem; }
                  .report-content h4 { font-size: 0.9rem; font-weight: 600; color: #6b7280; margin-top: 0.75rem; margin-bottom: 0.5rem; }
                  .report-content p { font-size: 0.8rem; color: #4b5563; line-height: 1.7; margin-bottom: 0.5rem; }
                  .report-content ul, .report-content ol { font-size: 0.8rem; color: #4b5563; line-height: 1.7; padding-left: 1.5rem; margin-bottom: 0.75rem; }
                  .report-content li { margin-bottom: 0.25rem; }
                  .report-content strong { font-weight: 600; color: #1f2937; }
                  .report-content em { font-style: italic; color: #6b7280; }
                  .report-content hr { border: none; border-top: 1px solid #e5e7eb; margin: 1.25rem 0; }
                  .report-content blockquote { border-left: 3px solid #d1d5db; padding-left: 1rem; color: #6b7280; margin: 0.75rem 0; }
                  .report-content code { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.75rem; background: #f3f4f6; padding: 0.15rem 0.35rem; border-radius: 3px; }
                `}</style>
                <div className="report-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {report.markdown_content}
                  </ReactMarkdown>
                </div>
              </div>
            </Modal>
          </div>
        )}

        {/* ── 分期补税模拟 ── */}
        {installData && (
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-3">
              <DollarOutlined className="text-amber-500" />
              <span className="text-sm font-semibold text-gray-700">分期补税模拟</span>
              <span className="text-[10px] text-gray-400">日滞纳金：{(installData.late_fee_daily || 0).toFixed(0)}元</span>
            </div>

            {/* 补税总额 */}
            <div className="bg-orange-50 rounded-lg p-3 mb-3 text-center">
              <p className="text-xs text-gray-500">应补税款总额</p>
              <p className="text-xl font-bold text-orange-600">
                {(installData.total_tax_due / 10000).toFixed(2)} 万元
              </p>
            </div>

            {/* 方案对比 */}
            <div className="space-y-2 mb-3">
              {/* 一次性 */}
              <div className="flex items-center justify-between bg-red-50 rounded-lg p-2">
                <div>
                  <span className="text-xs font-medium text-red-700">一次性补缴</span>
                  {installData.lump_sum?.late_fee as number > 0 && (
                    <span className="text-[10px] text-red-400 ml-1">
                      (含滞纳金 {(installData.lump_sum?.late_fee as number / 10000).toFixed(2)}万)
                    </span>
                  )}
                </div>
                <span className="text-sm font-bold text-red-600">
                  {(installData.lump_sum?.payment_amount as number / 10000).toFixed(2)} 万
                </span>
              </div>

              {/* 分期方案 */}
              {installData.installments.map((inst: Record<string, unknown>, i: number) => (
                <div
                  key={i}
                  className="flex items-center justify-between bg-white rounded-lg p-2 border border-gray-100"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded">
                      {inst.months as number}期
                    </span>
                    <span className="text-xs text-gray-500">
                      月付 {(inst.monthly_payment as number / 10000).toFixed(2)}万
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-gray-400">
                      总付 {(inst.total_installment_payment as number / 10000).toFixed(2)}万
                    </span>
                    <span className="text-[10px] text-orange-500 ml-1">
                      (+{(inst.total_interest_cost as number / 10000).toFixed(2)}万)
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* 推荐方案 */}
            <div className="bg-green-50 rounded-lg p-3 border border-green-100">
              <div className="flex items-center gap-1 mb-1">
                <TrophyOutlined className="text-green-600 text-xs" />
                <span className="text-xs font-medium text-green-700">推荐方案</span>
              </div>
              <p className="text-xs text-green-700">{installData.recommendation}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
import { Select, Slider, InputNumber, Button, Progress, Space, Modal } from 'antd';
import {
  PlayCircleOutlined, ThunderboltOutlined,
  WarningOutlined, CheckCircleOutlined,
  SafetyOutlined, BankOutlined,
  FileTextOutlined, TeamOutlined,
  AlertOutlined, EyeOutlined,
  ToolOutlined, DownloadOutlined,
  DollarOutlined, TrophyOutlined,
} from '@ant-design/icons';
import {
  Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ComposedChart,
} from 'recharts';
import { RISK_COLORS, RISK_LABELS } from '@/types';
import type { RiskLevel } from '@/types';

// ═══════════════════════════════════════
// AnimatedNumber - 数字滚动动画
// ═══════════════════════════════════════
function AnimatedNumber({ value, duration = 800, className = '' }: {
  value: number; duration?: number; className?: string;
}) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(0);

  useEffect(() => {
    const start = ref.current;
    const diff = value - start;
    const startTime = Date.now();
    let raf: number;

    function animate() {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));

      if (progress < 1) {
        raf = requestAnimationFrame(animate);
      }
    }

    raf = requestAnimationFrame(animate);
    ref.current = value;

    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span className={className}>{display.toLocaleString()}</span>;
}

// ═══════════════════════════════════════
// SimulationInputForm - 输入表单
// ═══════════════════════════════════════
interface SimulationInputFormProps {
  monthlyRevenue: number;
  onMonthlyRevenueChange: (v: number) => void;
  taxRate: number;
  onTaxRateChange: (v: number) => void;
  remediationCost: number;
  onRemediationCostChange: (v: number) => void;
  riskLevel: string;
  onSimulate: () => void;
  loading: boolean;
}

export function SimulationInputForm({
  monthlyRevenue, onMonthlyRevenueChange,
  taxRate, onTaxRateChange,
  remediationCost, onRemediationCostChange,
  riskLevel, onSimulate, loading,
}: SimulationInputFormProps) {
  const color = RISK_COLORS[riskLevel as RiskLevel];
  const label = RISK_LABELS[riskLevel as RiskLevel];

  // 根据风险等级自动估算整改成本
  const estimatedCost = riskLevel === 'high' ? 80 : riskLevel === 'medium' ? 40 : 15;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
        <ThunderboltOutlined /> 情景参数配置
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* 月隐匿收入 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">月均隐匿收入</span>
            <Space.Compact>
              <InputNumber
                min={0}
                max={500}
                value={monthlyRevenue}
                onChange={(v) => onMonthlyRevenueChange(v || 0)}
                size="small"
                style={{ width: 70 }}
              />
              <Button disabled size="small" style={{ padding: '0 8px' }}>万</Button>
            </Space.Compact>
          </div>
          <Slider
            min={0}
            max={500}
            step={5}
            value={monthlyRevenue}
            onChange={(v) => onMonthlyRevenueChange(v)}
            tooltip={{ formatter: (v) => `${v}万元/月` }}
          />
          <p className="text-xs text-gray-400 mt-1">推测企业未申报的月均经营收入</p>
        </div>

        {/* 综合税率（下拉选择） */}
        <div>
          <div className="flex flex-col gap-2">
            <span className="text-sm text-gray-600">综合税率</span>
            <Select
              value={taxRate}
              onChange={onTaxRateChange}
              options={[
                { value: 6, label: '6% — 小规模/服务业' },
                { value: 9, label: '9% — 建筑业/不动产' },
                { value: 13, label: '13% — 制造业/贸易' },
              ]}
              style={{ width: '100%' }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-2">增值税+所得税+附加税综合税率</p>
        </div>

        {/* 合规整改成本 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">合规整改成本</span>
            <Space.Compact>
              <InputNumber
                min={0}
                max={200}
                value={remediationCost}
                onChange={(v) => onRemediationCostChange(v || 0)}
                size="small"
                style={{ width: 70 }}
              />
              <Button disabled size="small" style={{ padding: '0 8px' }}>万</Button>
            </Space.Compact>
          </div>
          <Slider
            min={0}
            max={200}
            step={5}
            value={remediationCost}
            onChange={(v) => onRemediationCostChange(v)}
            tooltip={{ formatter: (v) => `${v}万元` }}
          />
          <p className="text-xs text-gray-400 mt-1">
            建议参考值：约 {estimatedCost} 万元
          </p>
        </div>

        {/* 当前风险等级 */}
        <div className="flex flex-col items-center justify-center">
          <p className="text-sm text-gray-500 mb-2">当前风险等级</p>
          <div
            className="w-full py-3 rounded-lg text-center"
            style={{ backgroundColor: color + '18', border: `1px solid ${color}40` }}
          >
            <p className="text-xl font-bold" style={{ color }}>{label}</p>
            <p className="text-xs text-gray-500 mt-0.5">自动带入</p>
          </div>
        </div>
      </div>

      {/* 模拟按钮 */}
      <div className="mt-6 text-center">
        <Button
          type="primary"
          size="large"
          icon={<PlayCircleOutlined />}
          onClick={onSimulate}
          loading={loading}
          className="px-10 h-11 text-base"
        >
          开始模拟
        </Button>
        <p className="text-xs text-gray-400 mt-2">
          拖动滑块实时调整参数，点击按钮进行双路径推演
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// PathComparisonChart - 双路径对比图
// ═══════════════════════════════════════
interface ChartPoint {
  year: number;
  label: string;
  '路径A 维持现状': number;
  '路径B 合规整改': number;
}

interface PathComparisonChartProps {
  data: ChartPoint[];
  remediationCost: number;
}

export function PathComparisonChart({ data }: PathComparisonChartProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[320px] text-sm text-gray-400">
        暂无模拟数据
      </div>
    );
  }

  // 计算最大Y值用于合理比例
  return (
    <div>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
          <defs>
            {/* 红色渐变：路径A下方区域 */}
            <linearGradient id="pathAGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#EF4444" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#EF4444" stopOpacity={0.05} />
            </linearGradient>
            {/* 绿色渐变：路径B下方区域 */}
            <linearGradient id="pathBGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10B981" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#10B981" stopOpacity={0.02} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />

          <XAxis
            dataKey="year"
            tickFormatter={(v) => {
              if (v <= 1) return '第1年';
              if (v <= 2) return '第2年';
              return '第3年';
            }}
            tick={{ fontSize: 11, fill: '#64748b' }}
          />

          <YAxis
            tick={{ fontSize: 11 }}
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
              name === '路径A 维持现状' ? '维持现状成本' : '合规整改成本',
            ]}
            labelFormatter={(label) => {
              const pt = data.find((d) => d.year === label);
              return pt?.label || `第${label}年`;
            }}
          />

          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            formatter={(value: string) => (
              <span style={{
                color: value.includes('路径A') ? '#EF4444' : '#10B981',
                fontWeight: 500,
              }}>
                {value}
              </span>
            )}
          />

          {/* 路径A：维持现状（红色面积 + 红色线） */}
          <Area
            type="monotone"
            dataKey="路径A 维持现状"
            stroke="#EF4444"
            strokeWidth={2.5}
            fill="url(#pathAGradient)"
            name="路径A 维持现状"
          />

          {/* 路径B：合规整改（绿色线 + 浅绿面积） */}
          <Line
            type="monotone"
            dataKey="路径B 合规整改"
            stroke="#10B981"
            strokeWidth={2.5}
            strokeDasharray="6 3"
            dot={{ r: 5, fill: '#10B981', stroke: '#fff', strokeWidth: 2 }}
            activeDot={{ r: 7, fill: '#10B981' }}
            name="路径B 合规整改"
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* 图例说明 */}
      <div className="flex items-center justify-center gap-6 mt-2 text-xs text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-red-500 inline-block" />
          路径A 维持现状（含罚款敞口）
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-green-500 inline-block" style={{ borderStyle: 'dashed' }} />
          路径B 合规整改
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 bg-red-100 rounded" />
          红色区域 = 多付出的代价
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// LossFrameMessage - 损失框架话术
// ═══════════════════════════════════════
interface LossFrameMessageProps {
  totalLoss: number;
  remediationCost: number;
  yearsAhead?: number;
}

export function LossFrameMessage({
  totalLoss, remediationCost, yearsAhead = 3,
}: LossFrameMessageProps) {
  const savedAmount = totalLoss - remediationCost;

  return (
    <div className="bg-gradient-to-br from-red-50 to-rose-50 border border-red-200 rounded-2xl p-6">
      <div className="flex items-start gap-4">
        <WarningOutlined className="text-red-500 text-2xl mt-1 shrink-0" />

        <div className="space-y-4">
          {/* 损失提示（大字） */}
          <div>
            <p className="text-sm text-red-600 mb-1">继续当前模式</p>
            <p className="text-3xl sm:text-4xl font-extrabold text-red-600 leading-tight">
              {yearsAhead}年后预计损失
              <span className="text-red-700">
                <AnimatedNumber value={totalLoss} className="mx-1" />万元
              </span>
            </p>
          </div>

          {/* 对比 */}
          <div className="flex items-center gap-3 p-3 bg-white rounded-xl border border-green-200">
            <CheckCircleOutlined className="text-green-500 text-lg shrink-0" />
            <div>
              <p className="text-sm text-green-700">
                现在整改仅需投入{' '}
                <span className="font-bold text-lg">
                  <AnimatedNumber value={remediationCost} />
                </span> 万元
              </p>
              {savedAmount > 0 && (
                <p className="text-xs text-green-600 mt-0.5">
                  主动整改可避免 <span className="font-bold">{savedAmount.toLocaleString()}</span> 万元的潜在损失
                </p>
              )}
            </div>
          </div>

          {/* 进度对比 */}
          <div className="space-y-2">
            <div>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-500">维持现状代价</span>
                <span className="text-red-600 font-bold">
                  <AnimatedNumber value={totalLoss} />万
                </span>
              </div>
              <Progress
                percent={100}
                strokeColor="#EF4444"
                showInfo={false}
                size="small"
              />
            </div>
            <div>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-500">合规整改投入</span>
                <span className="text-green-600 font-bold">
                  {remediationCost.toLocaleString()}万
                </span>
              </div>
              <Progress
                percent={totalLoss > 0 ? Math.round((remediationCost / totalLoss) * 100) : 0}
                strokeColor="#10B981"
                showInfo={false}
                size="small"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// TrudgeChecklist - 步履干预微任务打卡列表
// ═══════════════════════════════════════

export function TrudgeChecklist({
  title,
  tasks,
  framework,
  closing,
}: {
  title: string;
  tasks: { task_id: number; task_name: string; action: string; deadline: string; evidence_required: string }[];
  framework: string;
  closing: string;
}) {
  const [checkedMap, setCheckedMap] = useState<Record<number, boolean>>({});
  const [expandedTask, setExpandedTask] = useState<number | null>(null);

  const checkedCount = Object.values(checkedMap).filter(Boolean).length;
  const totalCount = tasks.length;
  const progress = totalCount > 0 ? Math.round((checkedCount / totalCount) * 100) : 0;

  const toggleCheck = (taskId: number) => {
    setCheckedMap((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  if (!tasks.length) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6 text-center">
        <p className="text-sm text-gray-400">暂无整改任务</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* SOP 标题 */}
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 rounded-full bg-green-500" />
        <h3 className="text-base font-semibold text-gray-700">{title}</h3>
      </div>

      {/* 进度条 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-gray-600">合规整改进度</span>
          <span className="text-sm font-bold text-green-600">
            {checkedCount}/{totalCount} 项完成
          </span>
        </div>
        <div className="relative w-full h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-gradient-to-r from-green-400 to-green-500 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-xs text-gray-400 mt-2">
          每完成一项勾选，即为企业构筑一道合规防线
        </p>
      </div>

      {/* 微任务列表 */}
      <div className="space-y-3">
        {tasks.map((task) => {
          const isChecked = !!checkedMap[task.task_id];
          const isExpanded = expandedTask === task.task_id;

          return (
            <div
              key={task.task_id}
              className={`
                bg-white rounded-xl border transition-all duration-300
                ${isChecked
                  ? 'border-green-200 bg-green-50/30'
                  : 'border-gray-200 hover:border-green-200 hover:shadow-sm'
                }
                ${isExpanded ? 'shadow-md ring-1 ring-green-200' : ''}
              `}
            >
              {/* 任务头部 */}
              <div className="flex items-start gap-3 p-4">
                {/* 勾选框 */}
                <button
                  onClick={() => toggleCheck(task.task_id)}
                  className={`
                    mt-0.5 w-5 h-5 rounded border-2 flex items-center justify-center shrink-0
                    transition-all duration-200
                    ${isChecked
                      ? 'bg-green-500 border-green-500 text-white'
                      : 'border-gray-300 hover:border-green-400'
                    }
                  `}
                >
                  {isChecked && (
                    <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </button>

                {/* 任务信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`
                        text-sm font-semibold
                        ${isChecked ? 'text-green-600 line-through' : 'text-gray-700'}
                      `}
                    >
                      {task.task_name}
                    </span>
                    <span className="text-xs bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full font-medium">
                      {task.deadline}
                    </span>
                  </div>

                  {/* 展开详情 */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 space-y-2 animate-fadeIn">
                      <div className="flex items-start gap-2">
                        <span className="text-xs text-gray-400 shrink-0 mt-0.5">操作：</span>
                        <span className="text-sm text-gray-600 leading-relaxed">{task.action}</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-xs text-gray-400 shrink-0 mt-0.5">凭证：</span>
                        <span className="text-sm text-gray-500 leading-relaxed">{task.evidence_required}</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* 展开/收起按钮 */}
                <button
                  onClick={() => setExpandedTask(isExpanded ? null : task.task_id)}
                  className="text-xs text-gray-400 hover:text-gray-600 shrink-0 px-2 py-1"
                >
                  {isExpanded ? '收起' : '详情'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* 合规框架说明 */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-blue-500 uppercase">合规框架引用</span>
        </div>
        <p className="text-sm text-blue-700 leading-relaxed">{framework}</p>
      </div>

      {/* 信任建设收尾 */}
      {closing && (
        <div className="bg-green-50 border border-green-100 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-green-500 uppercase">合规伙伴寄语</span>
          </div>
          <p className="text-sm text-green-700 leading-relaxed">{closing}</p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// ThirdPartyConsequenceCard - 第三方后果卡片（Budge 升级）
// ═══════════════════════════════════════
interface ThirdPartyConsequenceCardProps {
  data: {
    bidding_restriction_days: number;
    bidding_restriction_detail: string;
    bank_credit_restriction_days: number;
    bank_credit_restriction_detail: string;
    government_subsidy_risk: string;
    blacklist_risk: string;
    social_credit_impact: string;
  };
}

export function ThirdPartyConsequenceCard({ data }: ThirdPartyConsequenceCardProps) {
  const hasRisk = data.bidding_restriction_days > 0 || data.bank_credit_restriction_days > 0;

  return (
    <div
      className={`rounded-xl border p-5 ${
        hasRisk
          ? 'bg-gradient-to-br from-orange-50 to-red-50 border-orange-200'
          : 'bg-white border-gray-200'
      }`}
    >
      <div className="flex items-center gap-2 mb-4">
        <SafetyOutlined className={hasRisk ? 'text-orange-500' : 'text-green-500'} />
        <h3 className="text-base font-semibold text-gray-700">第三方后果关联</h3>
        {hasRisk ? (
          <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full font-medium">
            高风险
          </span>
        ) : (
          <span className="text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded-full font-medium">
            暂不受影响
          </span>
        )}
      </div>

      <div className="space-y-3">
        {/* 招投标资格 */}
        <div className={`p-3 rounded-lg ${hasRisk ? 'bg-red-50/60' : 'bg-gray-50'}`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-gray-700">招投标资格</span>
            {data.bidding_restriction_days > 0 && (
              <span className="text-xs font-bold text-red-500">
                预计 {data.bidding_restriction_days} 天内受限
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">
            {data.bidding_restriction_detail}
          </p>
        </div>

        {/* 银行授信 */}
        <div className={`p-3 rounded-lg ${hasRisk ? 'bg-red-50/60' : 'bg-gray-50'}`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-gray-700">
              <BankOutlined className="mr-1" />
              银行授信
            </span>
            {data.bank_credit_restriction_days > 0 && (
              <span className="text-xs font-bold text-red-500">
                预计 {data.bank_credit_restriction_days} 天内受限
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">
            {data.bank_credit_restriction_detail}
          </p>
        </div>

        {/* 政府补贴 */}
        <div className={`p-3 rounded-lg ${hasRisk ? 'bg-red-50/60' : 'bg-gray-50'}`}>
          <span className="text-sm font-medium text-gray-700 block mb-1">政府补贴/资质</span>
          <p className="text-xs text-gray-500 leading-relaxed">
            {data.government_subsidy_risk}
          </p>
        </div>

        {/* 信用影响 */}
        <div className={`p-3 rounded-lg ${hasRisk ? 'bg-red-50/60' : 'bg-gray-50'}`}>
          <span className="text-sm font-medium text-gray-700 block mb-1">社会信用</span>
          <p className="text-xs text-gray-500 leading-relaxed">
            {data.social_credit_impact}
          </p>
        </div>

        {/* 黑名单风险 */}
        <div className={`p-3 rounded-lg ${hasRisk ? 'bg-red-50/60' : 'bg-gray-50'}`}>
          <span className="text-sm font-medium text-gray-700 block mb-1">黑名单风险</span>
          <p className="text-xs text-gray-500 leading-relaxed">
            {data.blacklist_risk}
          </p>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// PeerPressureCard - 同行对比压力卡片（Budge 升级）
// ═══════════════════════════════════════
interface PeerPressureCardProps {
  data: {
    industry: string;
    peer_cases_count: number;
    peer_cases_detail: Array<{
      case_id: string;
      year: number | string;
      violation: string;
      penalty_amount: string;
      detection_method: string;
    }>;
    penalty_distribution: Record<string, number>;
    peer_compliance_rate: number;
    pressure_message: string;
  };
}

export function PeerPressureCard({ data }: PeerPressureCardProps) {
  const [showDetail, setShowDetail] = useState(false);
  const hasPressure = data.peer_cases_count > 0;

  const penaltyEntries = Object.entries(data.penalty_distribution).filter(
    ([, count]) => count > 0,
  );

  return (
    <div
      className={`rounded-xl border p-5 ${
        hasPressure
          ? 'bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200'
          : 'bg-white border-gray-200'
      }`}
    >
      <div className="flex items-center gap-2 mb-4">
        <TeamOutlined className={hasPressure ? 'text-amber-500' : 'text-gray-400'} />
        <h3 className="text-base font-semibold text-gray-700">同行对比压力</h3>
        <span className="text-xs bg-amber-100 text-amber-600 px-2 py-0.5 rounded-full font-medium">
          {data.industry}
        </span>
      </div>

      {/* 压力话术 */}
      {data.pressure_message && (
        <div className={`p-4 rounded-xl mb-4 text-sm leading-relaxed ${
          hasPressure ? 'bg-red-50 text-red-700 border border-red-100' : 'bg-green-50 text-green-700 border border-green-100'
        }`}>
          {data.pressure_message}
        </div>
      )}

      {/* 核心指标 */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-white rounded-lg p-3 text-center border border-gray-100">
          <p className="text-2xl font-bold text-amber-600">{data.peer_cases_count}</p>
          <p className="text-xs text-gray-400 mt-0.5">同行立案数</p>
        </div>
        <div className="bg-white rounded-lg p-3 text-center border border-gray-100">
          <p className="text-2xl font-bold text-blue-600">
            {Math.round(data.peer_compliance_rate * 100)}%
          </p>
          <p className="text-xs text-gray-400 mt-0.5">同行合规率</p>
        </div>
        <div className="bg-white rounded-lg p-3 text-center border border-gray-100">
          <p className="text-2xl font-bold text-red-600">
            {Math.round((1 - data.peer_compliance_rate) * 100)}%
          </p>
          <p className="text-xs text-gray-400 mt-0.5">已遭稽查比例</p>
        </div>
      </div>

      {/* 处罚分布 */}
      {penaltyEntries.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-gray-400 mb-2">同行处罚金额分布</p>
          <div className="flex gap-1 h-6 rounded-full overflow-hidden">
            {penaltyEntries.map(([label, count]) => {
              const colors: Record<string, string> = {
                '<50万': '#FCD34D',
                '50-200万': '#F59E0B',
                '200-500万': '#EF4444',
                '>500万': '#991B1B',
              };
              const total = penaltyEntries.reduce((s, [, c]) => s + c, 0);
              const pct = (count / total) * 100;
              return (
                <div
                  key={label}
                  title={`${label}: ${count}起`}
                  style={{
                    width: `${pct}%`,
                    backgroundColor: colors[label] || '#9CA3AF',
                  }}
                />
              );
            })}
          </div>
          <div className="flex justify-between mt-1">
            {penaltyEntries.map(([label, count]) => (
              <span key={label} className="text-[10px] text-gray-500">
                {label}: {count}起
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 查看详情 */}
      {data.peer_cases_detail.length > 0 && (
        <>
          <Button
            type="link"
            size="small"
            onClick={() => setShowDetail(true)}
            icon={<EyeOutlined />}
          >
            查看同行稽查案例详情
          </Button>

          <Modal
            title={
              <span className="flex items-center gap-2">
                <AlertOutlined className="text-amber-500" />
                {data.industry}行业稽查案例
              </span>
            }
            open={showDetail}
            onCancel={() => setShowDetail(false)}
            footer={null}
            width={640}
          >
            <div className="space-y-3 max-h-[60vh] overflow-y-auto">
              {data.peer_cases_detail.map((c) => (
                <div
                  key={c.case_id}
                  className="bg-gray-50 rounded-lg p-4 border border-gray-100"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-mono bg-gray-200 px-1.5 py-0.5 rounded">
                      {c.case_id}
                    </span>
                    <span className="text-xs text-gray-400">{c.year}</span>
                    <span className="text-xs font-bold text-red-500 ml-auto">
                      {c.penalty_amount}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mb-2">{c.violation}</p>
                  <p className="text-xs text-gray-400">
                    发现方式：{c.detection_method}
                  </p>
                </div>
              ))}
            </div>
          </Modal>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// OfficialNoticeCard - 模拟官方文书卡片（Budge 升级）
// ═══════════════════════════════════════
interface OfficialNoticeCardProps {
  data: {
    document_type: string;
    document_title: string;
    document_number: string;
    issuing_body: string;
    enterprise_name: string;
    credit_code: string;
    risk_findings: string[];
    potential_consequences: string[];
    compliance_deadline: string;
    disclaimer: string;
    full_text: string;
  };
}

export function OfficialNoticeCard({ data }: OfficialNoticeCardProps) {
  const [showFull, setShowFull] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <FileTextOutlined className="text-blue-500" />
        <h3 className="text-base font-semibold text-gray-700">模拟官方文书</h3>
        <span className="text-[10px] bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full font-medium">
          第三方风险提示
        </span>
        <span className="text-[10px] text-gray-400 ml-auto">
          {data.document_number}
        </span>
      </div>

      {/* 文书摘要 */}
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border border-blue-100 p-4 mb-4">
        <p className="text-sm font-semibold text-gray-700 mb-2">
          {data.document_title}
        </p>

        <div className="flex items-center gap-4 text-xs text-gray-500 mb-3">
          <span>致：{data.enterprise_name}</span>
          <span>信用代码：{data.credit_code || '（未登记）'}</span>
        </div>

        {/* 风险提示摘要 */}
        {data.risk_findings.length > 0 && (
          <div className="mb-3">
            <p className="text-xs font-medium text-gray-500 mb-1">风险发现：</p>
            <ul className="list-disc list-inside text-xs text-red-600 space-y-0.5">
              {data.risk_findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        )}

        {/* 潜在后果 */}
        {data.potential_consequences.length > 0 && (
          <div className="mb-3">
            <p className="text-xs font-medium text-gray-500 mb-1">潜在后果：</p>
            <div className="flex flex-wrap gap-1">
              {data.potential_consequences.map((c, i) => (
                <span
                  key={i}
                  className="text-[10px] bg-red-50 text-red-600 px-2 py-0.5 rounded-full border border-red-100"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 整改期限 */}
        {data.compliance_deadline && (
          <p className="text-xs text-orange-600 font-medium">
            合规建议：{data.compliance_deadline}
          </p>
        )}
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center gap-3">
        <Button
          type="primary"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => setShowFull(true)}
        >
          查看完整文书
        </Button>
        <p className="text-[10px] text-gray-400 flex-1">
          {data.disclaimer}
        </p>
      </div>

      {/* 完整文书弹窗 */}
      <Modal
        title={
          <span className="flex items-center gap-2">
            <FileTextOutlined className="text-blue-500" />
            模拟官方文书预览
          </span>
        }
        open={showFull}
        onCancel={() => setShowFull(false)}
        footer={
          <div className="flex items-center justify-between">
            <span className="text-xs text-red-400">{data.disclaimer}</span>
            <Button onClick={() => setShowFull(false)}>关闭</Button>
          </div>
        }
        width={720}
      >
        <div className="bg-gray-50 rounded-lg p-5 max-h-[60vh] overflow-y-auto">
          <pre className="text-xs text-gray-700 font-mono leading-relaxed whitespace-pre-wrap">
            {data.full_text}
          </pre>
        </div>
      </Modal>
    </div>
  );
}


// ═══════════════════════════════════════
// CaseStudyCard - 案例引用卡片
// ═══════════════════════════════════════
interface CaseStudyCardProps {
  caseData: Record<string, unknown>;
  index: number;
}

export function CaseStudyCard({ caseData, index }: CaseStudyCardProps) {
  const [expanded, setExpanded] = useState(false);

  const title = String(caseData.title || `案例 ${index + 1}`);
  const description = String(caseData.description || '暂无描述');
  const penalty = caseData.penalty ? String(caseData.penalty) : '';
  const industry = caseData.industry ? String(caseData.industry) : '';

  return (
    <div
      className={`
        bg-white rounded-xl border p-4 cursor-pointer transition-all duration-300
        ${expanded ? 'shadow-lg ring-1 ring-primary/20 border-primary/30' : 'border-gray-200 hover:shadow-md'}
      `}
      onClick={() => setExpanded(!expanded)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(!expanded); } }}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center shrink-0">
              {index + 1}
            </div>
            <h4 className="text-sm font-semibold text-gray-700 truncate">{title}</h4>
            {industry && (
              <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">
                {industry}
              </span>
            )}
          </div>

          <p className={`text-xs text-gray-600 leading-relaxed ${expanded ? '' : 'line-clamp-2'}`}>
            {description}
          </p>

          {penalty && !expanded && (
            <p className="text-xs text-red-500 mt-1.5 font-medium">
              处罚：{penalty}
            </p>
          )}
        </div>

        <span className="text-[10px] text-gray-400 shrink-0 ml-2 mt-0.5">
          {expanded ? '收起' : '展开'}
        </span>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-2 animate-fadeIn">
          {!!caseData.violation && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-gray-400 shrink-0">违规行为：</span>
              <span className="text-gray-700">{String(caseData.violation as string)}</span>
            </div>
          )}
          {!!caseData.result && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-gray-400 shrink-0">查处结果：</span>
              <span className="text-gray-700">{String(caseData.result as string)}</span>
            </div>
          )}
          {penalty && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-gray-400 shrink-0">罚款金额：</span>
              <span className="text-red-600 font-bold">{penalty}</span>
            </div>
          )}
          {!!caseData.lesson && (
            <div className="bg-amber-50 rounded-lg p-2.5 text-xs text-amber-800 leading-relaxed">
              <span className="font-medium">教训：</span>
              {String(caseData.lesson as string)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
