import { useEffect, useState, useMemo } from 'react';
import { AlertOutlined } from '@ant-design/icons';
import { useEnterpriseStore } from '@/store';
import { simulationApi } from '@/api';
import {
  SimulationInputForm,
  LossFrameMessage,
  CaseStudyCard,
  TrudgeChecklist,
  ThirdPartyConsequenceCard,
  PeerPressureCard,
  OfficialNoticeCard,
  TrudgeToolbox,
} from '@/components/simulator';
import { ExponentialSnowballChart } from '@/components/charts';
import { LoadingSpinner, EmptyState, TableContainer } from '@/components/common';
import type {
  SimulationResult, SnowballTimePoint,
  TrudgeLayer,
} from '@/types';

// ── 默认值 ──
const DEFAULT_MONTHLY_REVENUE = 50;   // 万元/月
const DEFAULT_TAX_RATE = 6;           // %
const DEFAULT_REMEDIATION_COST = 30;  // 万元

// ── 动态风险等级计算（与后端 _compute_dynamic_risk_level 对齐） ──
function computeDynamicRiskLevel(monthlyHiddenRevenueYuan: number): string {
  if (monthlyHiddenRevenueYuan <= 0) return 'low';
  if (monthlyHiddenRevenueYuan < 50_000) return 'medium';
  if (monthlyHiddenRevenueYuan < 200_000) return 'medium_high';
  if (monthlyHiddenRevenueYuan < 500_000) return 'high';
  return 'critical';
}

// ── 罚款倍数（与后端 penalty_calculator 对齐） ──
const PENALTY_MULTIPLIERS: Record<string, number> = {
  low: 0.5,
  medium: 1.5,
  medium_high: 2.5,
  high: 3.5,
  critical: 5.0,
};

// 滞纳金日利率（征管法第32条）
const LATE_FEE_DAILY_RATE = 0.0005;

// ── 时间节点对应的月数和天数 ──
const PERIOD_CONFIG: Record<string, { months: number; days: number }> = {
  '6months': { months: 6, days: 180 },
  '1year': { months: 12, days: 365 },
  '3years': { months: 36, days: 1095 },
};

// ── 默认 Trudge SOP 微任务（LLM 不可用时的降级内容） ──
const DEFAULT_TRUDGE_TASKS = [
  {
    task_id: 1,
    task_name: '审查日常业务税务管理制度设计',
    action: '全面审查企业现行的税务管理制度文件，包括发票管理、收入确认、成本费用列支的内部流程，确保与《大企业税务风险管理指引》一致',
    deadline: '15个工作日',
    evidence_required: '制度文件清单、修订建议报告',
  },
  {
    task_id: 2,
    task_name: '核实关联方无形劳务真实性',
    action: '逐笔核对企业向关联方支付的服务费/咨询费/特许权使用费，收集对应的合同、服务成果交付证明、市场公允价格比对资料',
    deadline: '20个工作日',
    evidence_required: '服务合同、成果交付记录、公允价格比对分析',
  },
  {
    task_id: 3,
    task_name: '成本费用凭证全面自查',
    action: '逐笔审核近36个月成本费用凭证，重点筛查咨询费/服务费/劳务费发票的真实性和关联性',
    deadline: '7个工作日',
    evidence_required: '每笔费用对应的合同、付款凭证、服务成果交付证明',
  },
  {
    task_id: 4,
    task_name: '发票流-资金流一致性比对',
    action: '以合同台账为基准，逐月比对发票流与银行流水，识别开票金额与收款金额偏离超过30%的异常交易',
    deadline: '10个工作日',
    evidence_required: '比对表、差异说明、补充协议或更正后的发票',
  },
  {
    task_id: 5,
    task_name: '建立税务内控台账',
    action: '按国税发[2009]90号要求，设置税务风险管理岗位，建立月度税负率监控、季度发票异常预警、年度合规自查的制度化流程',
    deadline: '30个工作日',
    evidence_required: '内控制度文件、岗位职责说明、监控台账模板',
  },
];

// ── 计算指数级雪球数据 ──
function computeSnowballData(
  simResult: SimulationResult | null,
  monthlyRevenue: number,
  taxRate: number,
  remediationCost: number,
  riskLevel: string,
): SnowballTimePoint[] {
  if (!simResult?.time_points?.length) return [];

  const multiplier = PENALTY_MULTIPLIERS[riskLevel] || 1.5;
  const monthlyHiddenTax = (monthlyRevenue * 10000) * (taxRate / 100);

  return simResult.time_points.map((tp) => {
    const cfg = PERIOD_CONFIG[tp.period as keyof typeof PERIOD_CONFIG] ||
      PERIOD_CONFIG['1year'];
    const months = cfg.months;
    const days = cfg.days;

    // 税金本体：累计少缴税款
    const totalHiddenTax = Math.round(monthlyHiddenTax * months);

    // 行政罚款：税金本金 × 倍数（不乘概率，即确定性金额）
    const adminPenalty = Math.round(totalHiddenTax * multiplier);

    // 个税穿透（模拟：隐匿收入的20%视同隐性分红）
    const monthlyHiddenRevenue = monthlyRevenue * 10000;
    const totalHiddenRevenue = monthlyHiddenRevenue * months;
    const iitPenetration = Math.round(totalHiddenRevenue * 0.20);

    // 复利滞纳金：日万分之五 × 天数（确定性金额，不乘概率）
    const lateFeeTotal = Math.round(totalHiddenTax * LATE_FEE_DAILY_RATE * days);

    // 路径A指数雪球 = 税金本体 + 倍数罚金 + 个税穿透 + 复利滞纳金
    const pathASnowball = totalHiddenTax + adminPenalty + iitPenetration + lateFeeTotal;

    // 路径B合规整改（低平直线）
    const pathBCost = Math.round(remediationCost * 10000);

    return {
      period: tp.period,
      months_elapsed: months,
      total_hidden_tax: totalHiddenTax,
      admin_penalty: adminPenalty,
      iit_penetration: iitPenetration,
      late_fee_total: lateFeeTotal,
      path_a_snowball: pathASnowball,
      path_b_cost: pathBCost,
      audit_probability: tp.audit_probability,
    };
  });
}

function Simulator() {
  const { currentEnterprise } = useEnterpriseStore();

  const [monthlyRevenue, setMonthlyRevenue] = useState(DEFAULT_MONTHLY_REVENUE);
  const [taxRate, setTaxRate] = useState(DEFAULT_TAX_RATE);
  const [remediationCost, setRemediationCost] = useState(DEFAULT_REMEDIATION_COST);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);

  // 合规微任务（Trudge SOP）数据
  const [trudgeData, setTrudgeData] = useState<TrudgeLayer | null>(null);
  const [trudgeLoading] = useState(false);

  const enterpriseId = currentEnterprise?.id;

  // ── 风险等级联动：优先后端返回的 effective_risk_level，否则按场景参数动态推算 ──
  const riskLevel: string = result?.effective_risk_level
    || computeDynamicRiskLevel(monthlyRevenue * 10000);

  // 切换企业时重置
  useEffect(() => {
    setResult(null);
    setTrudgeData(null);
    if (currentEnterprise) {
      if (currentEnterprise.risk_level === 'critical') setRemediationCost(120);
      else if (currentEnterprise.risk_level === 'high') setRemediationCost(80);
      else if (currentEnterprise.risk_level === 'medium_high') setRemediationCost(60);
      else if (currentEnterprise.risk_level === 'medium') setRemediationCost(40);
      else setRemediationCost(20);
    }
  }, [enterpriseId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 执行模拟
  const handleSimulate = async () => {
    if (!enterpriseId) return;
    setLoading(true);
    try {
      const simRes = await simulationApi.run(enterpriseId, {
        monthly_hidden_revenue: monthlyRevenue * 10000,
        comprehensive_tax_rate: taxRate / 100,
        remediation_cost: remediationCost * 10000,
      });
      setResult(simRes.data.data ?? null);
      // 一期边界（V4 §5.4）：分层干预已下线，trudgeData 恒为空
      setTrudgeData(null);
    } catch {
      setResult(null);
      setTrudgeData(null);
    } finally {
      setLoading(false);
    }
  };

  // 计算指数级雪球数据
  const snowballData = useMemo(
    () => computeSnowballData(result, monthlyRevenue, taxRate, remediationCost, riskLevel),
    [result, monthlyRevenue, taxRate, remediationCost, riskLevel],
  );

  // 计算总损失（取最后一个时间点的路径A雪球值）
  const totalLoss = snowballData.length
    ? Math.round(snowballData[snowballData.length - 1].path_a_snowball / 10000)
    : 0;

  // 使用后端返回的或降级的合规微任务数据
  const activeTrudge: TrudgeLayer = trudgeData && trudgeData.micro_tasks?.length > 0
    ? trudgeData
    : {
        sop_title: '企业财税合规整改标准作业程序（SOP）',
        micro_tasks: DEFAULT_TRUDGE_TASKS,
        compliance_framework:
          '依据国税发[2009]90号《大企业税务风险管理指引（试行）》第3章"税务风险管理组织"和第4章"税务风险识别和评估"的要求，结合《税收征收管理法》第32条、第63条的相关规定。',
        trust_building_closing:
          '合规不是负担，而是企业长期健康发展的护城河。完成上述整改后，贵司的纳税信用等级将得到修复，在融资授信、政府采购、资质审批中获得实实在在的竞争优势。',
      };

  // ── 无企业 ──
  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以使用风险模拟器" />;
  }

  return (
    <div className="space-y-6">
      {/* ═══ 标题 ═══ */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">沉浸式违法推演与步履干预器</h2>
        <p className="text-sm text-gray-500 mt-1">
          {currentEnterprise.name} · 双路径决策模拟 · 指数级雪球预估 · SOP 步履干预
        </p>
      </div>

      {/* ═══ 输入表单 ═══ */}
      <SimulationInputForm
        monthlyRevenue={monthlyRevenue}
        onMonthlyRevenueChange={setMonthlyRevenue}
        taxRate={taxRate}
        onTaxRateChange={setTaxRate}
        remediationCost={remediationCost}
        onRemediationCostChange={setRemediationCost}
        riskLevel={riskLevel}
        onSimulate={handleSimulate}
        loading={loading}
      />

      {/* ═══ 模拟结果 ═══ */}
      {loading ? (
        <LoadingSpinner text="正在运行风险模拟与合规干预分析..." />
      ) : result ? (
        <>
          {/* ═══ 指数级雪球对比图 ═══ */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="text-base font-semibold text-gray-700 mb-1">
              双路径对比：维持现状 vs 主动整改
            </h3>
            <p className="text-xs text-gray-400 mb-4">
              路径A（指数雪球）= 税金本体 + {PENALTY_MULTIPLIERS[riskLevel]}倍罚金 + 个税穿透 + 日万分之五复利滞纳金
            </p>
            <ExponentialSnowballChart data={snowballData} />
          </div>

          {/* ═══ P3: Trudge 救赎工具箱 ═══ */}
          {enterpriseId && (
            <TrudgeToolbox
              enterpriseId={enterpriseId}
              annualRevenue={currentEnterprise?.revenue_annual ?? 0}
              totalTaxDue={totalLoss}
            />
          )}

          {/* ═══ 雪球组分分解 ═══ */}
          {snowballData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-base font-semibold text-gray-700 mb-4">
                指数雪球组分分解
              </h3>
              <TableContainer>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-gray-500">
                      <th className="text-left py-2 px-3 font-medium">时间节点</th>
                      <th className="text-right py-2 px-3 font-medium">税金本金(万)</th>
                      <th className="text-right py-2 px-3 font-medium">{PENALTY_MULTIPLIERS[riskLevel]}倍罚金(万)</th>
                      <th className="text-right py-2 px-3 font-medium">个税穿透(万)</th>
                      <th className="text-right py-2 px-3 font-medium">滞纳金(万)</th>
                      <th className="text-right py-2 px-3 font-medium text-red-500">雪球总额(万)</th>
                      <th className="text-right py-2 px-3 font-medium text-green-500">整改成本(万)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snowballData.map((tp) => (
                      <tr key={tp.period} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2.5 px-3 font-medium text-gray-700">
                          {tp.period === '6months' ? '6个月' : tp.period === '1year' ? '1年' : '3年'}
                        </td>
                        <td className="py-2.5 px-3 text-right text-gray-600">
                          {Math.round(tp.total_hidden_tax / 10000).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right text-orange-600">
                          {Math.round(tp.admin_penalty / 10000).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right text-purple-600">
                          {Math.round(tp.iit_penetration / 10000).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right text-amber-600">
                          {Math.round(tp.late_fee_total / 10000).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-red-600">
                          {Math.round(tp.path_a_snowball / 10000).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right text-green-600">
                          {Math.round(tp.path_b_cost / 10000).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableContainer>
            </div>
          )}

          {/* ═══ 底部双列：损失框架话术（左）+ 案例引用（右） ═══ */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 损失框架话术 */}
            <LossFrameMessage
              totalLoss={totalLoss}
              remediationCost={remediationCost}
              yearsAhead={3}
            />

            {/* 同行业案例引用 */}
            <div>
              <h3 className="text-base font-semibold text-gray-700 mb-3">同行业案例参考</h3>
              {result.case_references && result.case_references.length > 0 ? (
                <div className="space-y-3">
                  {result.case_references.slice(0, 3).map((c: Record<string, unknown>, i: number) => (
                    <CaseStudyCard key={i} caseData={c} index={i} />
                  ))}
                </div>
              ) : (
                <div className="bg-white rounded-xl border border-gray-200 p-6 text-center">
                  <p className="text-sm text-gray-400">暂无匹配案例</p>
                  <p className="text-xs text-gray-300 mt-1">案例库将根据模拟参数自动匹配</p>
                </div>
              )}
            </div>
          </div>

          {/* ═══ Budge 升级：损失具象化增强 ═══ */}
          <div className="bg-gradient-to-r from-yellow-50 to-orange-50 rounded-xl border border-yellow-200 p-4">
            <h3 className="text-base font-semibold text-gray-700 mb-1 flex items-center gap-2">
              <AlertOutlined className="text-orange-500" />
              损失具象化增强（Budge 升级）
            </h3>
            <p className="text-xs text-gray-500 mb-4">
              通过第三方后果关联、同行对比压力和模拟官方文书，将"法律后果"转化为"老板看得见的损失"
            </p>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* 第三方后果关联 */}
              {result.third_party_consequences && (
                <ThirdPartyConsequenceCard data={result.third_party_consequences} />
              )}

              {/* 同行对比压力 */}
              {result.peer_pressure && (
                <PeerPressureCard data={result.peer_pressure} />
              )}

              {/* 模拟官方文书 */}
              {result.official_notice && (
                <OfficialNoticeCard data={result.official_notice} />
              )}
            </div>
          </div>

          {/* ═══ Trudge 步履干预层：可交互 Checkbox 微任务列表 ═══ */}
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-2xl border border-green-200 p-5 sm:p-6">
            {trudgeLoading ? (
              <LoadingSpinner text="正在生成合规整改SOP..." />
            ) : (
              <TrudgeChecklist
                title={activeTrudge.sop_title}
                tasks={activeTrudge.micro_tasks}
                framework={activeTrudge.compliance_framework}
                closing={activeTrudge.trust_building_closing}
              />
            )}
          </div>

          {/* ═══ 模拟建议 ═══ */}
          {result.recommendation && (
            <div className="bg-blue-50 rounded-xl border border-blue-100 p-4">
              <p className="text-sm text-blue-700 leading-relaxed">
                {result.recommendation}
              </p>
            </div>
          )}
        </>
      ) : (
        <EmptyState text={'配置参数后点击「开始模拟」查看双路径对比结果与合规整改SOP'} />
      )}
    </div>
  );
}

export default Simulator;
