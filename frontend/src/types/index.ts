// ═══════════════════════════════════════
// 统一类型定义
// ═══════════════════════════════════════

// ── 企业 ──
export interface Enterprise {
  id: string;
  name: string;
  credit_code: string;
  industry: string;
  revenue_annual: number;
  employee_count: number;
  tax_rate_claimed: number;
  cost_rate_claimed: number;
  is_high_tech: boolean;
  is_small_micro: boolean;
  risk_level: RiskLevel;
  created_at: string;
  updated_at: string;
}

export interface EnterpriseSummary {
  id: string;
  name: string;
  industry: string;
  revenue_annual: number;
  risk_level: string;
  created_at: string;
}

// ── 商业模式分类 ──
export type BusinessModel = 'asset_heavy' | 'asset_light';

// 行业 → 商业模式映射（重资产 vs 轻资产）
export const BUSINESS_MODEL_MAP: Record<string, BusinessModel> = {
  '制造': 'asset_heavy',
  '制造业': 'asset_heavy',
  '建筑': 'asset_heavy',
  '交通运输': 'asset_heavy',
  '批发零售': 'asset_light',
  '电商': 'asset_light',
  '餐饮服务': 'asset_light',
  '医美咨询': 'asset_light',
};

export const BUSINESS_MODEL_LABELS: Record<BusinessModel, string> = {
  asset_heavy: '重资产制造',
  asset_light: '轻资产服务',
};

export const BUSINESS_MODEL_DESC: Record<BusinessModel, string> = {
  asset_heavy: '本企业属重资产制造型，核心风险锚点为资产折旧摊销、进销项匹配与产能-能耗弹性系数。',
  asset_light: '本企业属轻资产服务型，核心风险锚点为成本费用率畸高、缺乏合法进项导致利润虚高、关联方无形劳务真实性。',
};

// ── 风险等级（五级，匹配后端 AssessRiskLevel + medium_high） ──
export type RiskLevel = 'low' | 'medium' | 'medium_high' | 'high' | 'critical';

export const RISK_COLORS: Record<RiskLevel, string> = {
  low: '#10B981',
  medium: '#F59E0B',
  medium_high: '#F97316',
  high: '#EF4444',
  critical: '#DC2626',
};

// ── 高压渲染阈值：稽查概率超过该值触发高压渲染 ──
export const AUDIT_PROBABILITY_CRITICAL = 0.80;

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  medium_high: '中高风险',
  high: '高风险',
  critical: '严重风险',
};



// ── 风险指标健康阈值 ──
export const HEALTH_THRESHOLDS = {
  four_flow_match: 85,
  private_card_ratio: 20,
  cost_deviation: 15,
  risk_score: 70,
} as const;


// ── 风险扫描 ──
export interface RiskScanResult {
  risk_assessment_id: string;
  enterprise_id: string;
  overall_risk_level: RiskLevel;
  overall_risk_score: number;
  four_flow_match_score: number;
  private_card_ratio: number;
  cost_deviation: number;
  dimension_scores: Record<string, number>;
  dim_details: Record<string, {
    detail: string;
    technical_detail: string;
    risk_reason?: string;
    policy_ref?: string;
    policy_basis?: string;
    /** 内控系数 C（B4 连续化，1.0 − 维度分/100，仅 5 维引擎返回） */
    internal_control_coefficient?: number;
  }>;
  recommendations: Record<string, unknown>;
  match_details?: MatchDetailItem[];
  business_narrative: string;
  /** 5 维引擎返回结构化 dict；旧引擎兼容字符串 */
  technical_summary: string | Record<string, unknown>;
  assessment_date: string;
}

/** 四流匹配明细（后端 match_details，逐合同/发票的匹配状态与差异） */
export interface MatchDetailItem {
  contract_no?: string | null;
  counterparty?: string | null;
  contract_amount?: number;
  invoice_no?: string | null;
  invoice_amount?: number;
  counterparty_match?: boolean;
  amount_match_score?: number;
  match_status?: 'matched' | 'unmatched';
  diff_amount?: number;
  diff_rate?: number;
  matched_bank_counterparty?: string | null;
  matched_bank_amount?: number;
  score?: number;
}

export interface RiskAssessment {
  id: string;
  enterprise_id: string;
  assessment_date: string;
  overall_risk_level: RiskLevel;
  overall_risk_score: number;
  four_flow_match_score: number;
  private_card_ratio: number;
  cost_deviation: number;
  risk_details: Record<string, unknown>;
  recommendations: Record<string, unknown>;
}

// ── 风险模拟 ──
// ── P3: Trudge 救赎工具箱 ──
export interface SelfAuditReport {
  report_id: string;
  enterprise_name: string;
  industry: string;
  generated_at: string;
  findings_summary: {
    total: number;
    high: number;
    medium: number;
    low: number;
    by_category: Record<string, number>;
    overall_rating: string;
  };
  findings_detail: Array<{
    rule_key: string;
    category: string;
    severity: string;
    title: string;
    description: string;
    suggestion: string;
    metrics: Record<string, number>;
  }>;
  markdown_content: string;
  risk_level: string;
  compliance_advice: string[];
}

export interface InstallmentComparison {
  total_tax_due: number;
  late_fee_daily: number;
  lump_sum: {
    payment_amount: number;
    late_fee: number;
    description: string;
    cash_flow_impact: string;
    pros: string[];
    cons: string[];
  };
  installments: Array<{
    months: number;
    monthly_payment: number;
    total_installment_payment: number;
    total_interest_cost: number;
    extra_vs_lump_sum: number;
    payoff_date: string;
    cash_flow_rating: string;
    pros: string[];
    cons: string[];
  }>;
  recommendation: string;
  cash_flow_analysis: string;
}
export interface SimulationRequest {
  monthly_hidden_revenue: number;
  comprehensive_tax_rate: number;
  remediation_cost: number;
}

export interface TimePoint {
  period: string;               // "6months" / "1year" / "3years"
  months_elapsed: number;
  path_a_cost: number;
  path_b_cost: number;
  cost_difference: number;
  audit_probability: number;
  expected_penalty: number;
  expected_late_fee: number;
  total_hidden_tax: number;
}

export interface SimulationResult {
  time_points: TimePoint[];
  recommendation: string;
  loss_frame_message: string;
  technical_summary: string;
  case_references: Record<string, unknown>[];
  effective_risk_level?: string;
  // ── Budge 升级：损失具象化增强 ──
  third_party_consequences?: ThirdPartyConsequence | null;
  peer_pressure?: PeerPressure | null;
  official_notice?: OfficialNoticePreview | null;
}

// ── 第三方后果关联 ──
export interface ThirdPartyConsequence {
  bidding_restriction_days: number;
  bidding_restriction_detail: string;
  bank_credit_restriction_days: number;
  bank_credit_restriction_detail: string;
  government_subsidy_risk: string;
  blacklist_risk: string;
  social_credit_impact: string;
}

// ── 同行对比压力 ──
export interface PeerPressure {
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
}

// ── 模拟官方文书 ──
export interface OfficialNoticePreview {
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
}

// ── 复合罚款雪球数据（前端计算） ──
export interface SnowballTimePoint {
  period: string;               // 6months / 1year / 3years
  months_elapsed: number;
  total_hidden_tax: number;     // 累计少缴税金本金
  admin_penalty: number;        // 行政罚款（倍数罚金）
  iit_penetration: number;      // 个税穿透补缴
  late_fee_total: number;       // 复利滞纳金
  path_a_snowball: number;      // 路径A 指数级雪球 = 本金+罚金+个税+滞纳金
  path_b_cost: number;          // 路径B 合规整改（低平直线）
  audit_probability: number;    // 稽查概率
}

// ── 合规导航 ──
export interface ConditionDetail {
  value: number;
  threshold: number;
  passed: boolean;
}

export interface TaxPreferenceResult {
  is_small_micro: boolean;
  small_micro_eligible: boolean;
  small_micro_conditions: Record<string, ConditionDetail>;
  is_high_tech: boolean;
  high_tech_risk: string | null;
  current_status: string;
  industry_preferences: string[];
  recommendations: string[];
  business_narrative: string;
  technical_summary: string;
}

export interface InterventionLayer {
  layer: number;
  name: string;
  theory: string;
  visual_type: string;
  content: string;
}

export interface InterventionResult {
  layers: InterventionLayer[];
  business_narrative: string;
  technical_summary: string;
  priority_bias: string;
  priority_order: string[];
  /** 合规调整后的风险等级（与展示链路联动，五级；缺失时回退企业详情等级） */
  compliance_risk_level?: RiskLevel | null;
}

export interface TrudgeMicroTask {
  task_id: number;
  task_name: string;
  action: string;
  deadline: string;
  evidence_required: string;
}

export interface TrudgeLayer {
  sop_title: string;
  micro_tasks: TrudgeMicroTask[];
  compliance_framework: string;
  trust_building_closing: string;
}

// ── 内控雷达数据 ──
export interface CostGaugeData {
  actualCostRate: number;               // 实际成本费用率 (%)
  industryCostRate: number;             // 行业基准成本费用率 (%)
  warningThreshold: number;             // 最高警戒阈值 (%)
  deviation: number;                    // 偏离度
  severity: 'normal' | 'moderate' | 'high' | 'severe';
}

export interface TaxBurdenElasticityData {
  period: string;
  revenueGrowth: number;                // 营业收入增长率 (%)
  taxBurdenRate: number;                // 增值税税负率 (%)
  expectedTaxBurden: number;            // 期望税负率 (%)
}

// ── 宏观内控雷达数据 ──
export interface ICRadarData {
  costGauge: CostGaugeData;
  taxBurdenElasticity: TaxBurdenElasticityData[];
  internalControlFailureWarning: boolean;
  predictedAuditProbability: number;
}

// ── 数据概览 ──
export interface BankTransaction {
  id: string;
  transaction_date: string;
  direction: 'inflow' | 'outflow';
  amount: number;
  account_type: 'corporate' | 'personal';
  counterparty: string;
  description: string;
  is_declared: boolean;
}

export interface Invoice {
  id: string;
  invoice_no: string;
  invoice_type: 'input' | 'output';
  invoice_date: string;
  product_name: string;
  amount: number;
  tax_amount: number;
  total_amount: number;
  buyer_name: string;
  seller_name: string;
  is_digital: boolean;
}

export interface TaxDeclaration {
  id: string;
  tax_type: string;
  period: string;
  declared_revenue: number;
  declared_tax: number;
  actual_paid: number;
}

export interface Contract {
  id: string;
  contract_no: string;
  contract_type: string;
  counterparty: string;
  contract_amount: number;
  signing_date: string;
  execution_status: string;
}

// ── 整改追踪 ──
export interface RemediationTask {
  id: string;
  enterprise_id: string;
  risk_assessment_id: string | null;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  status: 'pending' | 'in_progress' | 'completed';
  due_date: string | null;
  completed_at: string | null;
  progress: number;
  /** 任务来源 */
  source?: 'manual' | 'compliance';
  /** 关联合规发现的 rule_key 列表 */
  compliance_tags?: string[];
  /** 效果反馈备注 */
  feedback_notes?: string;
  created_at: string;
  updated_at: string;
}

// ── 合规校验 ──
export interface ComplianceFinding {
  rule_key: string;
  category: 'tax' | 'accounting' | 'financial' | 'invoice';
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  suggestion: string;
  metrics?: Record<string, number>;
}

export interface ComplianceCheckResult {
  enterprise_id: string;
  enterprise_name: string;
  findings_count: number;
  by_severity: { high: number; medium: number; low: number };
  by_category: Record<string, number>;
  findings: ComplianceFinding[];
}

/** 文档上传解析结果 */
export interface UploadParseResult {
  success: boolean;
  filename: string;
  errors: string[];
  warnings: string[];
  data_summary: {
    vouchers_count: number;
    trial_balance_codes: number;
    bs_items: number;
    inc_items: number;
    tax_types: string[];
  };
}

/** 上传后任务建议 */
export interface TaskSuggestion {
  task_id: string;
  title: string;
  status: string;
  tags: string[];
  unresolved_findings_count: number;
  suggested_action: 'complete' | 'keep_pending';
  suggested_progress: number | null;
}

/** 上传合规校验完整结果 */
export interface UploadCheckResult {
  enterprise_id: string;
  enterprise_name: string;
  parse_result: UploadParseResult;
  findings: {
    total: number;
    by_severity: { high: number; medium: number; low: number };
    items: ComplianceFinding[];
  };
  task_suggestions: TaskSuggestion[];
  new_tasks_needed: string[];
  compliance_adjusted?: ComplianceAdjustedRisk;
}

/** 合规调整风险数据（后端 compliance_adjustment 模块） */
export interface ComplianceAdjustedRisk {
  /** 原始风险评分（整改前/未调整口径） */
  original_score?: number;
  /** 原始风险等级（整改前/未调整口径，前端五级） */
  original_level?: RiskLevel;
  adjusted_score: number;
  adjusted_level: RiskLevel;
  completion_count: number;
  is_fully_compliant: boolean;
  reduction_pct: number;
}

/** 完成任务后 API 返回的扩展字段（含前后风险对比） */
export interface RemediationTaskUpdateResult extends RemediationTask {
  comparison?: {
    before: {
      overall_risk_score?: number;
      assessment_date?: string;
      compliance_adjusted?: ComplianceAdjustedRisk;
    };
    after: {
      overall_risk_score?: number;
      assessment_date?: string;
      compliance_adjusted?: ComplianceAdjustedRisk;
    };
  };
  overall_risk_score?: number;
}

/** 风险评分演化轨迹（B3：整改/重评估前后对比证据链） */
export interface RiskScoreTrajectory {
  id: string;
  enterprise_id: string;
  assessment_date: string;
  before_score: number | null;
  after_score: number;
  before_level: RiskLevel | null;
  after_level: RiskLevel;
  level_jump: 'up' | 'down' | 'same';
  changed_by: 'remediation' | 'risk_scan';
  reason: string;
  created_at: string;
}

export const TASK_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  in_progress: '进行中',
  completed: '已完成',
};

export const TASK_PRIORITY_LABELS: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
};

// ── 报告 ──
export interface ReportContent {
  enterprise: {
    id: string;
    name: string;
    industry: string;
    revenue_annual: number;
    employee_count: number;
  };
  risk_assessment: {
    id: string;
    level: string;
    score: number;
    four_flow_match: number;
    private_card_ratio: number;
    cost_deviation: number;
    details: Record<string, unknown>;
    recommendations: Record<string, unknown>;
    date: string | null;
  } | null;
  /**
   * 整改后风险状态（后端 compute_compliance_adjusted_risk 显式双状态节）。
   * 规则：当前状态视图 = adjusted_score+adjusted_level 成对；
   *      risk_assessment 保持原始快照（original score+level 成对），不再交叉绑定。
   */
  compliance_adjusted_risk?: ComplianceAdjustedRisk & { veto_reason?: string | null };
  generated_at: string;
  disclaimer: string;
}

export interface Report {
  id: string;
  enterprise_id: string;
  title: string;
  report_type: string;
  generated_at: string;
  content: ReportContent;
  content_summary: {
    risk_level: string;
  };
}

// ── 通用API响应 ──
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
