// ═══════════════════════════════════════
// API 请求封装
// ═══════════════════════════════════════
import apiClient from './client';
import type {
  ApiResponse, Enterprise, EnterpriseSummary,
  RiskScanResult, RiskAssessment,
  ProfileResult, ProfileSummary,
  SimulationRequest, SimulationResult,
  TaxPreferenceResult, InterventionResult,
  NBTInterventionResult,
  BankTransaction, Invoice, TaxDeclaration, Contract,
  RemediationTask, RemediationTaskUpdateResult, RiskScoreTrajectory, Report,
  ComplianceCheckResult, UploadCheckResult,
  SSFResult,
} from '@/types';

// ── 企业管理 ──
export const enterpriseApi = {
  list: (params?: { industry?: string; risk_level?: string; limit?: number }) =>
    apiClient.get<ApiResponse<{ enterprises: EnterpriseSummary[]; total: number }>>('/enterprises', { params }),

  detail: (id: string) =>
    apiClient.get<ApiResponse<{ enterprise: Enterprise; statistics: Record<string, number> }>>(`/enterprises/${id}`),

  create: (data: Partial<Enterprise>) =>
    apiClient.post<ApiResponse<Enterprise>>('/enterprises', data),

  update: (id: string, data: Partial<Enterprise>) =>
    apiClient.put<ApiResponse<Enterprise>>(`/enterprises/${id}`, data),

  delete: (id: string) =>
    apiClient.delete<ApiResponse<null>>(`/enterprises/${id}`),
};

// ── 风险扫描 ──
export const riskScanApi = {
  scan: (enterpriseId: string) =>
    apiClient.post<ApiResponse<RiskScanResult>>(`/enterprises/${enterpriseId}/risk-scan`),

  list: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ assessments: RiskAssessment[]; total: number }>>(`/enterprises/${enterpriseId}/risk-assessments`),

  latest: (enterpriseId: string) =>
    apiClient.get<ApiResponse<RiskScanResult>>(`/enterprises/${enterpriseId}/risk-assessments/latest`),

  detail: (assessmentId: string) =>
    apiClient.get<ApiResponse<RiskAssessment>>(`/risk-assessments/${assessmentId}`),

  /** 风险评分演化轨迹（B3：整改/重评估前后对比证据链） */
  trajectory: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ trajectories: RiskScoreTrajectory[]; total: number }>>(`/enterprises/${enterpriseId}/risk-score-trajectory`),
};

// ── 心理画像 ──
export const profileApi = {
  generate: (enterpriseId: string) =>
    apiClient.post<ApiResponse<ProfileResult>>(`/enterprises/${enterpriseId}/profile`),

  list: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ profiles: ProfileSummary[]; total: number }>>(`/enterprises/${enterpriseId}/profiles`),

  latest: (enterpriseId: string) =>
    apiClient.get<ApiResponse<ProfileResult>>(`/enterprises/${enterpriseId}/profiles/latest`),
};

// ── 风险模拟 ──
export const simulationApi = {
  run: (enterpriseId: string, params: SimulationRequest) =>
    apiClient.post<ApiResponse<SimulationResult>>(`/enterprises/${enterpriseId}/simulate`, params),

  caseStudies: (params?: { industry?: string; risk_level?: string }) =>
    apiClient.get<ApiResponse<{ cases: Record<string, unknown>[]; total: number }>>('/case-studies', { params }),
};

// ── 合规导航 ──
export const complianceApi = {
  taxPreference: (enterpriseId: string) =>
    apiClient.get<ApiResponse<TaxPreferenceResult>>(`/enterprises/${enterpriseId}/tax-preference`),

  intervention: (enterpriseId: string) =>
    apiClient.get<ApiResponse<InterventionResult>>(`/enterprises/${enterpriseId}/intervention`),

  // NBT 三层行为干预（调用大模型生成 Nudge-Budge-Trudge 结构化内容）
  nbtIntervention: (enterpriseId: string, riskData?: Record<string, unknown>) =>
    apiClient.post<ApiResponse<NBTInterventionResult>>(`/enterprises/${enterpriseId}/nbt-intervention`, riskData ?? {}),
};

// ── 数据接入 ──
export const dataApi = {
  bankStatements: (enterpriseId: string, params?: Record<string, unknown>) =>
    apiClient.get<ApiResponse<{ transactions: BankTransaction[]; total: number }>>(`/enterprises/${enterpriseId}/bank-statements`, { params }),

  invoices: (enterpriseId: string, params?: Record<string, unknown>) =>
    apiClient.get<ApiResponse<{ invoices: Invoice[]; total: number }>>(`/enterprises/${enterpriseId}/invoices`, { params }),

  taxDeclarations: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ declarations: TaxDeclaration[]; total: number }>>(`/enterprises/${enterpriseId}/tax-declarations`),

  contracts: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ contracts: Contract[]; total: number }>>(`/enterprises/${enterpriseId}/contracts`),

  loadMockData: (enterpriseId: string) =>
    apiClient.post(`/enterprises/${enterpriseId}/load-mock-data`),
};

// ── 整改追踪 ──
export const remediationApi = {
  list: (enterpriseId: string, params?: { status?: string; priority?: string; limit?: number }) =>
    apiClient.get<ApiResponse<{ tasks: RemediationTask[]; total: number }>>(`/enterprises/${enterpriseId}/remediation-tasks`, { params }),

  create: (enterpriseId: string, task: {
    title: string; description: string; priority: string;
    due_date?: string; risk_assessment_id?: string;
    source?: 'manual' | 'compliance'; compliance_tags?: string[];
  }) =>
    apiClient.post<ApiResponse<RemediationTask>>(`/enterprises/${enterpriseId}/remediation-tasks`, task),

  update: (taskId: string, data: {
    title?: string; description?: string; priority?: string;
    status?: string; progress?: number;
    compliance_tags?: string[]; feedback_notes?: string;
  }) =>
    apiClient.put<ApiResponse<RemediationTaskUpdateResult>>(`/remediation-tasks/${taskId}`, data),

  detail: (taskId: string) =>
    apiClient.get<ApiResponse<RemediationTask>>(`/remediation-tasks/${taskId}`),
};

// ── 合规校验 ──
export const complianceCheckApi = {
  run: (enterpriseId: string) =>
    apiClient.get<ApiResponse<ComplianceCheckResult>>(`/enterprises/${enterpriseId}/compliance-check`),
};

// ── SSF 博弈分析 ──
export const ssfApi = {
  /** 获取单企业 SSF 博弈状态 */
  getState: (enterpriseId: string) =>
    apiClient.get<ApiResponse<SSFResult>>(`/ssf/enterprises/${enterpriseId}`),

  /** 获取所有企业 SSF 坐标摘要 */
  getSummary: () =>
    apiClient.get<ApiResponse<{
      enterprises: Array<{
        enterprise_id: string;
        enterprise_name: string;
        power_coord: number;
        trust_coord: number;
        quadrant: string;
        quadrant_name: string;
        quadrant_color: string;
        primary_strategy: string;
        adjusted_risk_score: number;
        movement_description: string;
      }>;
      quadrant_distribution: Record<string, number>;
      total: number;
    }>>('/ssf/summary'),
};
// ── P3: Trudge 救赎工具箱 ──
export const trudgeApi = {
  /** 一键生成自查报告（Markdown） */
  getSelfAuditReport: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{
      report_id: string; enterprise_name: string; industry: string;
      generated_at: string; findings_summary: Record<string, unknown>;
      findings_detail: Record<string, unknown>[]; markdown_content: string;
      risk_level: string; compliance_advice: string[];
    }>>(`/enterprises/${enterpriseId}/self-audit-report`),

  /** 分期补税模拟 */
  getInstallmentSimulation: (enterpriseId: string, params?: { total_tax_due?: number; overdue_days?: number }) =>
    apiClient.get<ApiResponse<{
      total_tax_due: number; late_fee_daily: number;
      lump_sum: Record<string, unknown>;
      installments: Record<string, unknown>[];
      recommendation: string; cash_flow_analysis: string;
    }>>(`/enterprises/${enterpriseId}/installment-simulation`, { params }),
};
export const uploadApi = {
  /** 上传 Excel 报表并自动解析校验 */
  uploadDocuments: (enterpriseId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<ApiResponse<UploadCheckResult>>(
      `/enterprises/${enterpriseId}/upload-documents`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },

  /** 确认任务操作（完成/创建） */
  confirmTask: (enterpriseId: string, taskId: string, action: 'complete' | 'create', newFindingRules?: string[]) => {
    const formData = new FormData();
    formData.append('task_id', taskId);
    formData.append('action', action);
    if (action === 'create' && newFindingRules) {
      formData.append('new_finding_rules', newFindingRules.join(','));
    }
    return apiClient.post<ApiResponse<Record<string, unknown>>>(
      `/enterprises/${enterpriseId}/upload-documents/confirm-task`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },
};

// ── 报告 ──
export const reportApi = {
  generate: (enterpriseId: string, includeProfile?: boolean) =>
    apiClient.post<ApiResponse<Report>>(`/enterprises/${enterpriseId}/reports/generate`, { include_profile: includeProfile ?? false }),

  list: (enterpriseId: string) =>
    apiClient.get<ApiResponse<{ reports: Report[]; total: number }>>(`/enterprises/${enterpriseId}/reports`),

  detail: (reportId: string) =>
    apiClient.get<ApiResponse<Report>>(`/reports/${reportId}`),

  download: (enterpriseId: string, includeProfile?: boolean) =>
    apiClient.get(`/enterprises/${enterpriseId}/reports/download`, {
      params: { include_profile: includeProfile ?? false },
      responseType: 'blob',
    }),
};
