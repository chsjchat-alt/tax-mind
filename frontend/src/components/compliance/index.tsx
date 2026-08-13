import { useState, useMemo } from 'react';
import { CheckCircleOutlined, CloseCircleOutlined, RightOutlined, SafetyCertificateOutlined, FileTextOutlined, BulbOutlined, ThunderboltOutlined, AimOutlined, ApartmentOutlined } from '@ant-design/icons';
import { Progress, Tag, Tooltip } from 'antd';
import { RISK_COLORS } from '@/types';
import { TableContainer } from '@/components/common';
import type { RiskLevel, TaxPreferenceResult, InterventionResult } from '@/types';

// ═══════════════════════════════════════
// 方案类型
// ═══════════════════════════════════════
export interface PlanOption {
  id: string;
  name: string;
  description: string;
  estimatedCost: number;     // 万元
  estimatedTime: number;     // 月
  riskReduction: number;     // % 降低幅度
  recommendation: number;    // 推荐指数 1-5
  scope: string[];           // 覆盖范围
}

// ── current_status 英文→中文映射 ──
const STATUS_CN_MAP: Record<string, string> = {
  enjoying_correctly: '当前正确享受小微企业优惠，状态正常。',
  enjoying_incorrectly: '当前享受小微企业优惠但已不满足条件，存在被追缴风险，请尽快自查并主动调整。',
  should_enjoy_but_not: '贵企业符合小微企业条件但尚未享受优惠，建议尽快向税务机关申请认定。',
  not_applicable: '贵企业不适用小微企业优惠政策。',
};

// 根据风险等级生成三套方案
export function generatePlans(riskLevel: RiskLevel): PlanOption[] {
  const basePlans: Record<RiskLevel, PlanOption[]> = {
    low: [
      {
        id: 'minimal',
        name: '基础合规方案',
        description: '维持现有合规水平，定期进行风险扫描监控',
        estimatedCost: 5,
        estimatedTime: 1,
        riskReduction: 10,
        recommendation: 4,
        scope: ['季度风险扫描', '基础四流匹配', '发票合规检查'],
      },
      {
        id: 'standard',
        name: '标准优化方案',
        description: '完善四流匹配体系，建立内部财税审计流程',
        estimatedCost: 15,
        estimatedTime: 3,
        riskReduction: 25,
        recommendation: 3,
        scope: ['月度风险扫描', '四流匹配优化', '发票全量校验', '内部审计流程'],
      },
      {
        id: 'comprehensive',
        name: '全面保障方案',
        description: '全维度合规体系建设，引入第三方审计，培养财税团队',
        estimatedCost: 30,
        estimatedTime: 6,
        riskReduction: 40,
        recommendation: 2,
        scope: ['实时风险监控', '四流匹配升级', '全流程合规', '第三方审计', '团队培训'],
      },
    ],
    medium: [
      {
        id: 'minimal',
        name: '聚焦整改方案',
        description: '针对中高风险维度进行专项整改，快速降低核心风险',
        estimatedCost: 15,
        estimatedTime: 2,
        riskReduction: 30,
        recommendation: 3,
        scope: ['高风险维度专项整改', '私卡收款规范化', '发票进销项匹配'],
      },
      {
        id: 'standard',
        name: '系统治理方案',
        description: '建立系统性合规架构，覆盖主要风险维度',
        estimatedCost: 40,
        estimatedTime: 4,
        riskReduction: 50,
        recommendation: 4,
        scope: ['全维度风险整改', '四流匹配建设', '内部审计+外部审计', '财务流程重构'],
      },
      {
        id: 'comprehensive',
        name: '深度转型方案',
        description: '企业财税合规全面转型，建立长效合规机制',
        estimatedCost: 80,
        estimatedTime: 8,
        riskReduction: 75,
        recommendation: 5,
        scope: ['全面合规转型', 'ERP系统对接', '财税顾问驻场', '团队建设', '长效监控'],
      },
    ],
    medium_high: [
      {
        id: 'urgent',
        name: '重点优化方案',
        description: '针对中高风险维度实施定向优化，快速收敛核心偏离指标',
        estimatedCost: 20,
        estimatedTime: 2,
        riskReduction: 40,
        recommendation: 4,
        scope: ['重点维度定向优化', '私卡收款整改', '成本费用率调优', '四流匹配自查'],
      },
      {
        id: 'standard',
        name: '综合治理方案',
        description: '覆盖中高风险维度的系统性治理，建立内部风控流程',
        estimatedCost: 50,
        estimatedTime: 4,
        riskReduction: 60,
        recommendation: 4,
        scope: ['全维度风险评估', '四流匹配建设', '进销项匹配优化', '内部审计+培训'],
      },
      {
        id: 'comprehensive',
        name: '深度升级方案',
        description: '全面升级财税合规体系，引入第三方评估与数字化工具',
        estimatedCost: 100,
        estimatedTime: 8,
        riskReduction: 80,
        recommendation: 3,
        scope: ['全面合规升级', 'ERP系统评估', '第三方审计', '团队建设', '数字化合规工具'],
      },
    ],
    high: [
      {
        id: 'urgent',
        name: '紧急止损方案',
        description: '立即停止高风险行为，补缴税款+主动申报争取从轻处理',
        estimatedCost: 30,
        estimatedTime: 1,
        riskReduction: 50,
        recommendation: 5,
        scope: ['紧急停损', '补缴税款', '主动申报说明', '律师介入'],
      },
      {
        id: 'standard',
        name: '全面整改方案',
        description: '系统性整改所有高风险维度，重建合规体系',
        estimatedCost: 80,
        estimatedTime: 6,
        riskReduction: 70,
        recommendation: 4,
        scope: ['全维度整改', '补缴+自查申报', '四流匹配重建', '外审介入', '流程重设计'],
      },
      {
        id: 'comprehensive',
        name: '彻底重构方案',
        description: '从零重建企业财税合规体系，引入数字化合规平台',
        estimatedCost: 150,
        estimatedTime: 12,
        riskReduction: 90,
        recommendation: 3,
        scope: ['全面重构', '补缴+自查+主动申报', '数字化合规平台', '常年顾问', '全员培训'],
      },
    ],
    critical: [
      {
        id: 'urgent',
        name: '最高警戒方案',
        description: '立即启动全面自查，停止所有高风险经营行为，配合税务稽查',
        estimatedCost: 50,
        estimatedTime: 1,
        riskReduction: 60,
        recommendation: 5,
        scope: ['立即全面自查', '停止高风险行为', '补缴+主动申报', '律师+会计师紧急介入'],
      },
      {
        id: 'standard',
        name: '强制整改方案',
        description: '在税务稽查指导下进行强制性全维度整改，引入权威第三方审计',
        estimatedCost: 120,
        estimatedTime: 6,
        riskReduction: 80,
        recommendation: 5,
        scope: ['强制整改', '配合稽查', '全量补缴', '第三方审计', '合规体系重建'],
      },
      {
        id: 'comprehensive',
        name: '全面重构方案',
        description: '从零推翻重建企业财税体系，引入全过程数字化合规监控',
        estimatedCost: 200,
        estimatedTime: 12,
        riskReduction: 95,
        recommendation: 4,
        scope: ['体系重构建', '配合稽查+补缴', '数字化全流程监控', '常年驻场顾问', '全员合规培训'],
      },
    ],
  };

  return basePlans[riskLevel] || basePlans.low;
}

// ═══════════════════════════════════════
// PreferenceCheck - 优惠条件校验项
// ═══════════════════════════════════════
interface PreferenceCheckProps {
  label: string;
  met: boolean;
}

function PreferenceCheck({ label, met }: PreferenceCheckProps) {
  return (
    <div className="flex items-center gap-2 text-sm py-1">
      {met ? (
        <CheckCircleOutlined style={{ color: RISK_COLORS.low, fontSize: 16 }} />
      ) : (
        <CloseCircleOutlined style={{ color: RISK_COLORS.high, fontSize: 16 }} />
      )}
      <span className={met ? 'text-gray-700' : 'text-gray-400 line-through'}>
        {label}
      </span>
    </div>
  );
}

// ═══════════════════════════════════════
// TaxPreferencePanel - 税收优惠校验面板
// ═══════════════════════════════════════
interface TaxPreferencePanelProps {
  preference: TaxPreferenceResult;
  enterpriseName: string;
}

export function TaxPreferencePanel({ preference, enterpriseName }: TaxPreferencePanelProps) {
  // 判断享受状态
  const getStatus = () => {
    if (preference.is_small_micro && preference.small_micro_eligible) return { text: '正确享受', color: 'success', desc: '企业已认定为小微企业且符合条件，优惠享受合规' };
    if (preference.is_small_micro && !preference.small_micro_eligible) return { text: '错误享受', color: 'error', desc: '企业已认定为小微企业但当前不符合条件，存在合规风险' };
    if (!preference.is_small_micro && preference.small_micro_eligible) return { text: '应享未享', color: 'warning', desc: '企业符合小微企业条件但未享受优惠，建议尽快申报' };
    if (preference.is_high_tech) return { text: '正确享受', color: 'success', desc: '高新技术企业优惠正常享受中' };
    return { text: '未涉及', color: 'default', desc: '当前不涉及相关优惠政策' };
  };

  const status = getStatus();

  return (
    <div className="space-y-6">
      {/* 享受状态横幅 */}
      <div className={`rounded-xl p-5 border ${
        status.color === 'success' ? 'bg-green-50 border-green-200' :
        status.color === 'error' ? 'bg-red-50 border-red-200' :
        status.color === 'warning' ? 'bg-amber-50 border-amber-200' :
        'bg-gray-50 border-gray-200'
      }`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-gray-700">
              {enterpriseName} · 税收优惠状态
            </p>
            <p className={`text-sm mt-1 ${
              status.color === 'success' ? 'text-green-700' :
              status.color === 'error' ? 'text-red-700' :
              status.color === 'warning' ? 'text-amber-700' : 'text-gray-500'
            }`}>
              {status.desc}
            </p>
          </div>
          <Tag color={status.color} className="text-sm px-3 py-1">
            {status.text}
          </Tag>
        </div>
      </div>

      {/* 小微企业条件核验 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-700 mb-1">小微企业优惠核验</h3>
          <p className="text-xs text-gray-400 mb-4">
            小型微利企业：年应纳税所得额≤300万元，从业人数≤300人，资产总额≤5000万元
          </p>
          <div className="space-y-1 mb-4">
            {Object.entries(preference.small_micro_conditions).length > 0 ? (
              Object.entries(preference.small_micro_conditions).map(([key, c]) => (
                <PreferenceCheck
                  key={key}
                  met={c.passed}
                  label={
                    key === 'employee_count' ? `从业人数 ${c.value} / ${c.threshold} 人` :
                    key === 'total_assets' ? `资产总额 ${(c.value / 10000).toFixed(0)} / ${(c.threshold / 10000).toFixed(0)} 万元` :
                    key === 'annual_profit' ? `年应纳税所得额 ${(c.value / 10000).toFixed(0)} / ${(c.threshold / 10000).toFixed(0)} 万元` : key
                  }
                />
              ))
            ) : (
              <p className="text-sm text-gray-400">条件数据收集中...</p>
            )}
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-400">
              {Object.values(preference.small_micro_conditions).filter((c) => c.passed).length}
              /{Object.keys(preference.small_micro_conditions).length} 项符合
            </span>
            <Tag color={preference.small_micro_eligible ? 'success' : 'error'}>
              {preference.small_micro_eligible ? '符合条件' : '不符合条件'}
            </Tag>
          </div>
        </div>

        {/* 高新技术企业监测 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-700 mb-1">
            高新技术企业
            {preference.is_high_tech && (
              <Tag color="blue" className="ml-2">已认定</Tag>
            )}
          </h3>
          <p className="text-xs text-gray-400 mb-4">
            高新技术企业享受15%优惠所得税率（法定税率25%），需持续满足认定条件
          </p>

          {preference.high_tech_risk ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500 mb-2">动态监测提示：</p>
              <div className="flex items-start gap-2 text-sm">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                <span className="text-gray-700">{preference.high_tech_risk}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400">
              非高新技术企业。建议评估是否符合认定条件：研发费用占比≥5%、高新收入占比≥60%、科技人员占比≥10%
            </p>
          )}
        </div>
      </div>

      {/* 当前状态 + 业务解读 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-blue-800 mb-2">当前合规状态</h3>
          <p className="text-sm text-blue-700 leading-relaxed">
            {STATUS_CN_MAP[preference.current_status] || preference.current_status}
          </p>
        </div>
        {preference.business_narrative && (
          <div className="bg-purple-50 border border-purple-100 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-purple-800 mb-2">业务解读</h3>
            <p className="text-sm text-purple-700 leading-relaxed">{preference.business_narrative}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// PlanComparisonTable - 三套方案对比表
// ═══════════════════════════════════════
interface PlanComparisonTableProps {
  plans: PlanOption[];
}

export function PlanComparisonTable({ plans }: PlanComparisonTableProps) {
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);

  // 推荐星级
  const renderStars = (count: number) => (
    <div className="flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={`text-xs ${i < count ? 'text-amber-500' : 'text-gray-200'}`}>
          ★
        </span>
      ))}
    </div>
  );

  return (
    <div>
      {/* 卡片式比较（移动端）/ 表格（桌面端） */}
      {/* 桌面表格 */}
      <TableContainer className="hidden lg:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-gray-200">
              <th className="text-left py-3 px-4 font-medium text-gray-500">对比维度</th>
              {plans.map((plan) => (
                <th
                  key={plan.id}
                  className={`text-left py-3 px-4 font-semibold cursor-pointer transition-colors ${
                    selectedPlan === plan.id ? 'text-primary' : 'text-gray-700'
                  }`}
                  onClick={() => setSelectedPlan(selectedPlan === plan.id ? null : plan.id)}
                >
                  {plan.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-gray-100">
              <td className="py-3 px-4 text-gray-500">方案描述</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4 text-gray-700">{plan.description}</td>
              ))}
            </tr>
            <tr className="border-b border-gray-100 bg-gray-50">
              <td className="py-3 px-4 text-gray-500 font-medium">预计成本</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4">
                  <span className="font-bold text-gray-800">{plan.estimatedCost}</span>
                  <span className="text-xs text-gray-400 ml-1">万元</span>
                </td>
              ))}
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-3 px-4 text-gray-500">预计时间</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4">
                  <span className="font-bold text-gray-800">{plan.estimatedTime}</span>
                  <span className="text-xs text-gray-400 ml-1">个月</span>
                </td>
              ))}
            </tr>
            <tr className="border-b border-gray-100 bg-gray-50">
              <td className="py-3 px-4 text-gray-500">风险降低幅度</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <Progress
                      percent={plan.riskReduction}
                      size="small"
                      strokeColor={
                        plan.riskReduction >= 70 ? RISK_COLORS.low :
                        plan.riskReduction >= 40 ? RISK_COLORS.medium : RISK_COLORS.high
                      }
                      style={{ width: 80 }}
                    />
                    <span className="text-xs text-gray-500">{plan.riskReduction}%</span>
                  </div>
                </td>
              ))}
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-3 px-4 text-gray-500">推荐指数</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4">{renderStars(plan.recommendation)}</td>
              ))}
            </tr>
            <tr>
              <td className="py-3 px-4 text-gray-500">覆盖范围</td>
              {plans.map((plan) => (
                <td key={plan.id} className="py-3 px-4">
                  <div className="flex flex-wrap gap-1">
                    {plan.scope.map((item, i) => (
                      <Tag key={i} className="text-[10px]">{item}</Tag>
                    ))}
                  </div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </TableContainer>

      {/* 移动端卡片 */}
      <div className="lg:hidden space-y-4">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className={`bg-white rounded-xl border p-4 cursor-pointer transition-all ${
              selectedPlan === plan.id ? 'ring-2 ring-primary/30 border-primary/30' : 'border-gray-200'
            }`}
            onClick={() => setSelectedPlan(selectedPlan === plan.id ? null : plan.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedPlan(selectedPlan === plan.id ? null : plan.id); } }}
          >
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-gray-700">{plan.name}</h4>
              {renderStars(plan.recommendation)}
            </div>
            <p className="text-xs text-gray-500 mb-3">{plan.description}</p>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-gray-50 rounded-lg p-2">
                <p className="text-xs text-gray-400">预计成本</p>
                <p className="text-sm font-bold text-gray-700">{plan.estimatedCost}万</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <p className="text-xs text-gray-400">预计时间</p>
                <p className="text-sm font-bold text-gray-700">{plan.estimatedTime}月</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <p className="text-xs text-gray-400">风险降低</p>
                <p className="text-sm font-bold text-green-600">{plan.riskReduction}%</p>
              </div>
            </div>
            {selectedPlan === plan.id && (
              <div className="mt-3 pt-3 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-1">覆盖范围：</p>
                <div className="flex flex-wrap gap-1">
                  {plan.scope.map((item, i) => (
                    <Tag key={i} className="text-[10px]">{item}</Tag>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// 心理账户对比表格解析与渲染
// ═══════════════════════════════════════
interface MentalAccountData {
  header: string;
  leftTitle: string;
  rightTitle: string;
  rows: { left: string; right: string }[];
  closing: string;
}

function _parseMentalAccountTable(raw: string): MentalAccountData | null {
  if (!raw || !raw.includes('心理账户对比') || !raw.includes('┌')) return null;

  const result: MentalAccountData = {
    header: '心理账户对比',
    leftTitle: '合规账户',
    rightTitle: '违规账户',
    rows: [],
    closing: '',
  };

  // 提取标题行
  const headerMatch = raw.match(/│\s*(.+?（.+?）)\s*│\s*(.+?（.+?）)\s*│/);
  if (headerMatch) {
    result.leftTitle = headerMatch[1].trim();
    result.rightTitle = headerMatch[2].trim();
  }

  // 提取数据行（├ 和 └ 之间的行）
  const dataMatch = raw.match(/├─+┼─+┤\n([\s\S]*?)└─+┴─+┘/);
  if (dataMatch) {
    const rowLines = dataMatch[1].trim().split('\n');
    for (const line of rowLines) {
      const cells = line.split('│');
      if (cells.length >= 3) {
        const left = cells[1].trim();
        const right = cells[2].trim();
        if (left && right) {
          result.rows.push({ left, right });
        }
      }
    }
  }

  // 提取结尾语
  const closingMatch = raw.match(/┘\n\n?(.+?)$/);
  if (closingMatch) {
    result.closing = closingMatch[1].trim();
  }

  return result.rows.length > 0 ? result : null;
}

function MentalAccountTable({ data }: { data: MentalAccountData }) {
  return (
    <div className="mt-3 space-y-4 animate-fadeIn">
      {/* 表头 */}
      <div className="text-center">
        <p className="text-xs font-semibold text-gray-700">{data.header}</p>
      </div>

      {/* 对比表格 */}
      <div className="rounded-xl border border-gray-200 overflow-hidden">
        {/* 列标题 */}
        <div className="grid grid-cols-2">
          <div className="bg-emerald-500 px-4 py-2.5 text-center">
            <p className="text-xs font-bold text-white">{data.leftTitle}</p>
          </div>
          <div className="bg-red-500 px-4 py-2.5 text-center">
            <p className="text-xs font-bold text-white">{data.rightTitle}</p>
          </div>
        </div>

        {/* 数据行 */}
        <div>
          {data.rows.map((row, i) => (
            <div
              key={i}
              className={`grid grid-cols-2 ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}
            >
              <div className="flex items-center gap-2 px-4 py-2.5 border-r border-gray-100">
                <svg className="w-3.5 h-3.5 text-emerald-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-xs text-gray-700">{row.left}</span>
              </div>
              <div className="flex items-center gap-2 px-4 py-2.5">
                <svg className="w-3.5 h-3.5 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span className="text-xs text-gray-700">{row.right}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 结尾语 */}
      {data.closing && (
        <div className="bg-gradient-to-r from-emerald-50 to-gray-50 rounded-xl border border-emerald-200 p-4 text-center">
          <p className="text-sm font-semibold text-emerald-800 leading-relaxed">
            {data.closing}
          </p>
        </div>
      )}
    </div>
  );
}
interface InterventionLayerCardProps {
  layer: number;
  name: string;
  theory?: string;
  visualType: string;
  content: string;
  isExpanded: boolean;
  onToggle: () => void;
}

const LAYER_THEORIES: Record<number, string> = {
  1: '前景理论（Kahneman & Tversky, 1979）— 人们对损失的敏感性约是收益的2倍，损失框架话术能有效改变风险偏好',
  2: '可得性启发（Tversky & Kahneman, 1973）— 人们通过回忆类似案例的容易程度来判断事件概率，案例展示可纠正低估偏差',
  3: '控制错觉理论（Langer, 1975）— 人们倾向于高估自己对不可控事件的影响力，实证数据可有效破除这一偏差',
  4: '社会规范理论（Cialdini, 2003）— 个体行为深受社会规范影响，展示同行业平均水平可激发合规动机',
  5: '自我效能理论（Bandura, 1977）— 提供可操作的具体行动方案可增强"我能做到"的信念，促进行为改变',
};

const LAYER_COLORS: Record<number, string> = {
  1: '#F59E0B',
  2: '#3B82F6',
  3: '#8B5CF6',
  4: '#10B981',
  5: '#14B8A6',
};

const LAYER_BG: Record<number, string> = {
  1: 'border-amber-200 bg-amber-50/30',
  2: 'border-blue-200 bg-blue-50/30',
  3: 'border-purple-200 bg-purple-50/30',
  4: 'border-green-200 bg-green-50/30',
  5: 'border-teal-200 bg-teal-50/30',
};

export function InterventionLayerCard({
  layer, name, theory, visualType, content, isExpanded, onToggle,
}: InterventionLayerCardProps) {
  const mentalAccountData = useMemo(
    () => (layer === 5 ? _parseMentalAccountTable(content) : null),
    [layer, content],
  );

  return (
    <div
      className={`rounded-xl border-2 p-4 cursor-pointer transition-all duration-300 ${
        LAYER_BG[layer] || LAYER_BG[1]
      } ${isExpanded ? 'shadow-lg' : 'hover:shadow-md'}`}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } }}
    >
      <div className="flex items-start gap-3">
        {/* 层级标识 */}
        <div
          className="w-9 h-9 rounded-full flex items-center justify-center text-lg shrink-0 font-bold text-white"
          style={{ backgroundColor: LAYER_COLORS[layer] || LAYER_COLORS[1] }}
        >
          {layer}
        </div>

        <div className="flex-1 min-w-0">
          {/* 标题行 */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-semibold text-gray-700">
              第{layer}层：{name}
            </span>
            <Tag>{visualType}</Tag>
            {theory && (
              <Tag color="purple">{theory}</Tag>
            )}
          </div>

          {/* 内容预览 */}
          <p className={`text-xs text-gray-600 leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`}>
            {mentalAccountData ? '对比合规路径与违规路径的长期影响，帮助企业建立正确的税务心理账户。' : content}
          </p>

          {/* 展开后：理论依据 + 心理账户对比表格 */}
          {isExpanded && (
            <div className="mt-3 pt-3 border-t border-gray-200/60 animate-fadeIn">
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">理论依据</p>
                <p className="text-xs text-gray-600 leading-relaxed">
                  {theory || LAYER_THEORIES[layer] || ''}
                </p>
              </div>

              {/* 第五层特殊渲染：心理账户对比表格 */}
              {mentalAccountData && (
                <MentalAccountTable data={mentalAccountData} />
              )}
            </div>
          )}

          {/* 底部提示 */}
          <div className="flex items-center justify-between mt-2">
            <span className="text-[10px] text-gray-400">
              {isExpanded ? '点击收起' : '点击展开理论依据'}
            </span>
            <span className="text-[10px] text-gray-400">
              层级 {layer}/5
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// InterventionNarrativePanel - 干预解读（四模块结构化排版）
// ═══════════════════════════════════════

interface InterventionNarrativePanelProps {
  intervention: InterventionResult;
  enterpriseName: string;
  riskLevel: RiskLevel;
}

// ── 干预层中文简述映射 ──
const LAYER_PURPOSE: Record<number, string> = {
  1: '通过数据警示打破企业主"不会被查到"的乐观偏见，植入真实稽查概率认知。',
  2: '揭示金税四期全自动预警流程，破除"靠关系能摆平"的控制错觉。',
  3: '以损失框架重构认知——不合规的实际代价远超合规整改成本。',
  4: '提供合理化出口，将合规从"额外成本"重新定义为"长期投资"。',
  5: '建立合规心理账户，让企业主看到合规带来的长期竞争资产。',
};

// ── 图层摘要（用于流程图） ──
const LAYER_SHORT: Record<number, string> = {
  1: '数据警示',
  2: '流程透明',
  3: '损失对比',
  4: '认知重构',
  5: '长期锚定',
};

// ── 操作指引模板 ──
function getActionGuidance(riskLevel: RiskLevel): { step: string; detail: string; timeline: string }[] {
  const baseSteps = [
    { step: '认知对齐', detail: '与财务团队/外部顾问确认当前风险点，逐项对照七维度风险评分', timeline: '本周内' },
    { step: '制度完善', detail: '建立或完善四流匹配管理制度，规范发票开具、资金流转流程', timeline: '30天内' },
    { step: '数据补录', detail: '整理并补充历史票据、合同、银行流水等合规凭证', timeline: '60天内' },
    { step: '定期自查', detail: '每季度执行风险扫描，跟踪各维度风险评分变化趋势', timeline: '持续进行' },
  ];
  if (riskLevel === 'high') {
    baseSteps.unshift({
      step: '紧急止损',
      detail: '立即停止高风险行为（如私卡收款、大额公转私无合理商业目的），准备主动补申报材料',
      timeline: '立即执行',
    });
  }
  return baseSteps;
}

export function InterventionNarrativePanel({
  intervention, enterpriseName, riskLevel,
}: InterventionNarrativePanelProps) {

  const sortedLayers = intervention.priority_order.map(
    (num) => intervention.layers.find((l) => l.layer === Number(num))!
  ).filter(Boolean);

  const actions = getActionGuidance(riskLevel);
  const isHigh = riskLevel === 'high';
  const isMedium = riskLevel === 'medium';
  const riskLabel = isHigh ? '高风险' : isMedium ? '中风险' : '低风险';

  // ── 主导偏差中文名 ──
  const priorityBiasLabel = intervention.priority_bias === 'optimism_bias' ? '乐观偏差'
    : intervention.priority_bias === 'control_illusion' ? '控制错觉'
    : intervention.priority_bias === 'loss_aversion' ? '损失厌恶'
    : intervention.priority_bias === 'defensiveness' ? '防御心理'
    : intervention.priority_bias === 'short_termism' ? '短期主义'
    : intervention.priority_bias;

  return (
    <div className="space-y-5 sm:space-y-6">

      {/* ═══════════════════════════════════════
        模块一：核心合规要求
        ═══════════════════════════════════════ */}
      <section>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-100">
            <SafetyCertificateOutlined className="text-blue-600 text-sm" />
          </div>
          <h3 className="text-base font-semibold text-gray-800">核心合规要求</h3>
          {isHigh && (
            <Tag color="red" className="ml-1 text-xs">高风险预警</Tag>
          )}
        </div>

        <div className="bg-gradient-to-br from-slate-50 to-blue-50/30 rounded-2xl border border-slate-200 p-5 sm:p-6">
          {/* 企业状态摘要 */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">企业名称</p>
              <p className="text-sm font-semibold text-gray-800">{enterpriseName}</p>
              <p className="text-[11px] text-gray-400 mt-0.5">当前合规评估对象</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">合规风险等级</p>
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: RISK_COLORS[riskLevel] }}
                />
                <span className="text-sm font-bold" style={{ color: RISK_COLORS[riskLevel] }}>
                  {riskLabel}
                </span>
              </div>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {isHigh ? '需立即启动专项合规整改' : isMedium ? '建议优化关键风险维度' : '当前处于健康合规区间'}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">主导认知偏差</p>
              <div className="flex items-center gap-2">
                <AimOutlined className="text-amber-500 text-sm" />
                <span className="text-sm font-semibold text-gray-700">
                  {priorityBiasLabel !== 'none' ? priorityBiasLabel : '无显著偏差'}
                </span>
              </div>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {priorityBiasLabel !== 'none' ? '干预策略的主要靶向目标' : '采用默认认知校准策略'}
              </p>
            </div>
          </div>

          {/* 核心法规引用 */}
          <div className="bg-white rounded-xl border border-blue-100 p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileTextOutlined className="text-blue-500 text-xs" />
              <span className="text-xs font-semibold text-blue-700">适用核心法规</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-gray-600 leading-relaxed">
              <div className="flex items-start gap-1.5">
                <span className="mt-0.5 w-1 h-1 rounded-full bg-blue-400 shrink-0" />
                <span>
                  <strong className="text-gray-700">《税收征收管理法》</strong>
                  第六十三条：纳税人伪造、变造、隐匿、擅自销毁账簿、记账凭证，或者在账簿上多列支出或者不列、少列收入，由税务机关追缴其不缴或者少缴的税款、滞纳金，并处不缴或者少缴的税款百分之五十以上五倍以下的罚款。
                </span>
              </div>
              <div className="flex items-start gap-1.5">
                <span className="mt-0.5 w-1 h-1 rounded-full bg-blue-400 shrink-0" />
                <span>
                  <strong className="text-gray-700">《企业所得税法》</strong>
                  第二十八条：符合条件的小型微利企业，减按20%的税率征收企业所得税。
                </span>
              </div>
              <div className="flex items-start gap-1.5">
                <span className="mt-0.5 w-1 h-1 rounded-full bg-blue-400 shrink-0" />
                <span>
                  <strong className="text-gray-700">《增值税暂行条例》</strong>
                  第九条：纳税人购进货物、劳务、服务、无形资产、不动产，取得的增值税扣税凭证不符合法律、行政法规或者国务院税务主管部门有关规定的，其进项税额不得从销项税额中抵扣。
                </span>
              </div>
              <div className="flex items-start gap-1.5">
                <span className="mt-0.5 w-1 h-1 rounded-full bg-blue-400 shrink-0" />
                <span>
                  <strong className="text-gray-700">金税四期·数电票全面推广</strong>
                  自2025年12月1日起全国推广应用全面数字化电子发票，所有发票信息实时上传至税务系统，实现自动比对与风险识别。
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════
        模块二：干预场景说明
        ═══════════════════════════════════════ */}
      <section>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-100">
            <ApartmentOutlined className="text-amber-600 text-sm" />
          </div>
          <h3 className="text-base font-semibold text-gray-800">干预场景说明</h3>
          {intervention.priority_bias !== 'none' && (
            <span className="text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
              已根据主导偏差调整优先级
            </span>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
          {/* 场景描述 */}
          <p className="text-sm text-gray-600 leading-relaxed mb-5">
            基于{enterpriseName}的风险画像与认知偏差分析，以下五层干预策略按优先级排序执行。
            {priorityBiasLabel !== 'none' && (
              <span className="text-amber-700 font-medium">
                {' '}因检测到主导偏差为「{priorityBiasLabel}」，已优先推送对应的干预层内容。
              </span>
            )}
          </p>

          {/* 干预流程图 — 桌面端 */}
          <div className="hidden sm:flex items-center mb-6 overflow-x-auto pb-2">
            {sortedLayers.map((layer, idx) => (
              <div key={layer.layer} className="flex items-center shrink-0">
                <Tooltip title={`第${layer.layer}层：${layer.name}`}>
                  <div
                    className="flex items-center justify-center w-11 h-11 rounded-full text-sm font-bold text-white shadow-md shrink-0"
                    style={{ backgroundColor: LAYER_COLORS[layer.layer] }}
                  >
                    {layer.layer}
                  </div>
                </Tooltip>
                <div className="ml-2 mr-1 text-center min-w-[72px]">
                  <p className="text-xs font-semibold text-gray-700">{LAYER_SHORT[layer.layer]}</p>
                  {idx === 0 && <Tag color="amber" className="text-[10px] mt-0.5 leading-none px-1">优先</Tag>}
                </div>
                {idx < sortedLayers.length - 1 && (
                  <RightOutlined className="text-gray-300 mx-1 shrink-0 text-xs" />
                )}
              </div>
            ))}
          </div>

          {/* 干预流程图 — 移动端（纵向） */}
          <div className="sm:hidden flex flex-col items-center mb-5 space-y-0">
            {sortedLayers.map((layer, idx) => (
              <div key={layer.layer} className="flex flex-col items-center">
                <Tooltip title={`第${layer.layer}层：${layer.name}`}>
                  <div
                    className="flex items-center justify-center w-11 h-11 rounded-full text-sm font-bold text-white shadow-md"
                    style={{ backgroundColor: LAYER_COLORS[layer.layer] }}
                  >
                    {layer.layer}
                  </div>
                </Tooltip>
                <p className="text-[10px] font-medium text-gray-600 mt-1">{LAYER_SHORT[layer.layer]}</p>
                {idx === 0 && <Tag color="amber" className="text-[10px] mt-0.5 leading-none px-1">优先</Tag>}
                {idx < sortedLayers.length - 1 && (
                  <div className="w-0.5 h-4 bg-gray-200 my-1" />
                )}
              </div>
            ))}
          </div>

          {/* 各层场景说明 */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {sortedLayers.map((layer) => (
              <div
                key={layer.layer}
                className="rounded-xl border p-4 transition-shadow hover:shadow-sm"
                style={{ borderLeftColor: LAYER_COLORS[layer.layer], borderLeftWidth: 3 }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: LAYER_COLORS[layer.layer] }}
                  />
                  <span className="text-xs font-semibold text-gray-700">{layer.name}</span>
                </div>
                <p className="text-xs text-gray-500 leading-relaxed">
                  {LAYER_PURPOSE[layer.layer]}
                </p>
                <div className="mt-2 flex items-center gap-1.5">
                  <Tag className="text-[10px] leading-none px-1.5" style={{ borderColor: LAYER_COLORS[layer.layer], color: LAYER_COLORS[layer.layer] }}>
                    {layer.visual_type === 'card' ? '数据卡片' :
                     layer.visual_type === 'animation' ? '流程动画' :
                     layer.visual_type === 'text' ? '文字提示' : '对比表格'}
                  </Tag>
                  <span className="text-[10px] text-gray-400">第{layer.layer}层</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════
        模块三：政策解读要点
        ═══════════════════════════════════════ */}
      <section>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-100">
            <BulbOutlined className="text-purple-600 text-sm" />
          </div>
          <h3 className="text-base font-semibold text-gray-800">政策解读要点</h3>
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
          <div className="space-y-4">
            {/* 解读项 1：四流匹配 */}
            <div className="rounded-xl border border-l-4 border-l-amber-400 bg-amber-50/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <ThunderboltOutlined className="text-amber-500 text-sm" />
                <h4 className="text-sm font-semibold text-gray-800">
                  <span className="bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded text-xs mr-1.5">重点</span>
                  四流匹配是合规基础
                </h4>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed ml-6">
                金税四期要求合同流、发票流、货物流、资金流"四流一致"。任何一流缺失或数据不一致（如发票金额与银行流水不符、合同签约方与发票开具方不同）都将被系统自动标记为异常，触发稽查选案流程。这是税务合规的底线要求。
              </p>
            </div>

            {/* 解读项 2：损失框架 */}
            <div className="rounded-xl border border-l-4 border-l-red-400 bg-red-50/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <ThunderboltOutlined className="text-red-500 text-sm" />
                <h4 className="text-sm font-semibold text-gray-800">
                  <span className="bg-red-100 text-red-700 px-1.5 py-0.5 rounded text-xs mr-1.5">警示</span>
                  不合规的经济代价远超认知
                </h4>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed ml-6">
                根据《税收征收管理法》第六十三条，偷税行为除追缴税款外，处不缴或少缴税款50%以上5倍以下罚款。此外，纳税信用等级降为D级将导致：银行贷款受阻、发票领用受限（每次领用不得超过25份，且需预缴税款）、政府采购/招投标资格取消、出入境受限等连锁反应。
              </p>
            </div>

            {/* 解读项 3：金税四期自动化 */}
            <div className="rounded-xl border border-l-4 border-l-blue-400 bg-blue-50/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <ThunderboltOutlined className="text-blue-500 text-sm" />
                <h4 className="text-sm font-semibold text-gray-800">
                  <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded text-xs mr-1.5">系统</span>
                  金税四期全自动化风险识别
                </h4>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed ml-6">
                每日自动比对超2000万户企业的发票、申报与资金数据。异常识别无需人工介入——从数据采集、比对分析到风险标记、推送稽查，全流程由系统自动完成。高企"动态摘帽"已成为制度性常态（2025年全国取消4758家高企资格，同比增长11.77%）。
              </p>
            </div>

            {/* 解读项 4：合规的长期价值 */}
            <div className="rounded-xl border border-l-4 border-l-emerald-400 bg-emerald-50/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <ThunderboltOutlined className="text-emerald-500 text-sm" />
                <h4 className="text-sm font-semibold text-gray-800">
                  <span className="bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded text-xs mr-1.5">价值</span>
                  合规是企业长期信用资产
                </h4>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed ml-6">
                税务合规不仅是风险防范，更是企业的核心竞争力。合规企业可享受：银行授信额度上浮、政府补贴优先审批、招投标合规加分、企业估值提升等长期利益。纳税信用A级企业还可享受3年免检、绿色办税通道等便利措施。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════
        模块四：操作指引
        ═══════════════════════════════════════ */}
      <section>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-100">
            <CheckCircleOutlined className="text-emerald-600 text-sm" />
          </div>
          <h3 className="text-base font-semibold text-gray-800">操作指引</h3>
          <span className="text-xs text-gray-400">
            {actions.length} 项关键步骤
          </span>
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
          {/* 步骤流程 */}
          <div className="space-y-0">
            {actions.map((action, idx) => (
              <div key={action.step} className="flex">
                {/* 左侧：步骤编号 + 连接线 */}
                <div className="flex flex-col items-center mr-4">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm ${
                      idx === 0 && isHigh ? 'bg-red-500' : 'bg-emerald-500'
                    }`}
                  >
                    {idx + 1}
                  </div>
                  {idx < actions.length - 1 && (
                    <div className="w-0.5 flex-1 min-h-[20px] bg-gray-200 my-1" />
                  )}
                </div>
                {/* 右侧：内容 */}
                <div className={`pb-5 ${idx === actions.length - 1 ? '' : ''}`}>
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <h4 className={`text-sm font-semibold ${idx === 0 && isHigh ? 'text-red-700' : 'text-gray-800'}`}>
                      {action.step}
                    </h4>
                    <Tag
                      color={idx === 0 && isHigh ? 'red' : 'blue'}
                      className="text-[10px] leading-none px-1.5"
                    >
                      {action.timeline}
                    </Tag>
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed">{action.detail}</p>
                </div>
              </div>
            ))}
          </div>

          {/* 底部提示 */}
          <div className="mt-2 pt-4 border-t border-gray-100">
            <div className="flex items-start gap-2 p-3 bg-amber-50 rounded-lg border border-amber-100">
              <BulbOutlined className="text-amber-500 text-sm mt-0.5 shrink-0" />
              <div className="text-xs text-amber-700 leading-relaxed">
                <span className="font-semibold">提示：</span>
                上述操作步骤建议按顺序执行。如企业当前已处于高风险状态，建议立即聘请专业税务律师或注册税务师介入，并在专业指导下进行自查补报，以争取《行政处罚法》第三十二条规定的从轻或减轻处罚情节。
              </div>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
}
