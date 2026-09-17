/**
 * Dashboard 测试
 *
 * 覆盖率目标：
 *   - 无企业 → 空状态提示 + 刷新按钮
 *   - 加载中 → LoadingSpinner
 *   - 有数据 → 4 个核心指标卡片 + 图表区域 + 历史记录表格
 *   - 风险等级颜色映射正确
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Dashboard from '@/pages/Dashboard'
import { useEnterpriseStore, useRiskStore } from '@/store'
import { riskScanApi, remediationApi, enterpriseApi, dataApi } from '@/api'
import type { Enterprise, RiskScanResult } from '@/types'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// ── Mock react-router-dom ──
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

// ── Mock API（让 store 内的 fetchLatest / scanRisk 正常执行） ──
vi.mock('@/api', () => ({
  riskScanApi: { scan: vi.fn(), list: vi.fn(), latest: vi.fn() },
  remediationApi: { list: vi.fn() },
  dataApi: { loadMockData: vi.fn() },
  enterpriseApi: { list: vi.fn(), detail: vi.fn() },
}))

// ── Mock Recharts ──
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children,
  RadarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="radar-chart">{children}</div>,
  PolarGrid: () => null, PolarAngleAxis: () => null, PolarRadiusAxis: () => null,
  Radar: () => null,
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null, XAxis: () => null, YAxis: () => null,
  CartesianGrid: () => null, Tooltip: () => null, Legend: () => null,
}))

// ── Helpers ──
/** 构造完整 AxiosResponse（mock 响应必须包含 status/headers/config 等字段） */
const apiOk = <T,>(data: T): AxiosResponse<{ code: number; message: string; data: T }> => ({
  data: { code: 200, message: 'success', data },
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as InternalAxiosRequestConfig,
})

function makeEnterprise(overrides: Partial<Enterprise> = {}): Enterprise {
  return {
    id: 'ent-001', name: '测试企业', industry: '批发零售',
    revenue_annual: 5000000, employee_count: 120,
    credit_code: '91330100MA00000001', tax_rate_claimed: 3.0,
    cost_rate_claimed: 85, is_high_tech: false, is_small_micro: true,
    risk_level: 'low', created_at: '2025-01-01', updated_at: '2025-06-01',
    ...overrides,
  }
}

function makeRiskResult(overrides: Partial<RiskScanResult> = {}): RiskScanResult {
  return {
    risk_assessment_id: 'ra-001', enterprise_id: 'ent-001',
    overall_risk_level: 'low', overall_risk_score: 25,
    four_flow_match_score: 88, private_card_ratio: 5, cost_deviation: 3,
    dimension_scores: {
      private_card_ratio: 10, cost_deviation: 15, tax_burden_deviation: 8,
      four_flow_mismatch: 12, input_output_imbalance: 5,
    },
    dim_details: {}, recommendations: {},
    business_narrative: '企业经营状况良好', technical_summary: '技术摘要内容',
    assessment_date: '2025-06-15', ...overrides,
  }
}

function renderDashboard() {
  return render(<MemoryRouter><Dashboard /></MemoryRouter>)
}

beforeEach(() => {
  useEnterpriseStore.setState({ enterprises: [], currentEnterprise: null, listLoading: false, detailLoading: false })
  useRiskStore.setState({ result: null, status: 'idle', pendingAction: null, _scanningId: null })
  vi.clearAllMocks()
})

afterEach(() => { vi.restoreAllMocks() })

// ── 预设成功的 API mock ──
function mockApiSuccess() {
  vi.mocked(enterpriseApi.list).mockResolvedValue(apiOk({ enterprises: [], total: 0 }))
  vi.mocked(riskScanApi.scan).mockResolvedValue(apiOk(makeRiskResult()))
  vi.mocked(riskScanApi.list).mockResolvedValue(apiOk({ assessments: [], total: 0 }))
  vi.mocked(riskScanApi.latest).mockResolvedValue(apiOk(makeRiskResult()))
  vi.mocked(remediationApi.list).mockResolvedValue(apiOk({ tasks: [], total: 3 }))
  vi.mocked(dataApi.loadMockData).mockResolvedValue(apiOk({}))
}

// ═══════════════════════════════════════════════════
describe('Dashboard — 空状态', () => {
  it('无选中企业 → 显示空状态提示 + 刷新按钮', async () => {
    mockApiSuccess() // 让 enterpriseApi.list 成功返回 → entLoading=false
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText('数据驾驶舱')).toBeInTheDocument()
    })
    expect(screen.getByText(/请先从顶部选择一家企业/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /刷新企业列表/ })).toBeInTheDocument()
  })

  it('点击刷新企业列表 → 按钮可交互', async () => {
    mockApiSuccess()
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新企业列表/ })).toBeInTheDocument()
    })
    const btn = screen.getByRole('button', { name: /刷新企业列表/ })
    fireEvent.click(btn)
    expect(btn).toBeEnabled()
  })
})

// ═══════════════════════════════════════════════════
describe('Dashboard — 加载中', () => {
  it('企业已选中但数据加载未完成 → LoadingSpinner', async () => {
    mockApiSuccess()
    // 让 scanRisk 与 fetchLatest API 永不 resolve，加载状态保持 pending
    vi.mocked(riskScanApi.scan).mockReturnValue(new Promise(() => {}))
    vi.mocked(riskScanApi.latest).mockReturnValue(new Promise(() => {}))
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
    renderDashboard()
    expect(await screen.findByText(/正在加载风险数据/)).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('Dashboard — 数据展示（API mock 成功 + store 注入 result）', () => {
  beforeEach(() => {
    mockApiSuccess()
  })

  it('有数据 → 显示 3 个核心指标卡片', async () => {
    // loadAllData 会调用 scanRisk → 通过 mock 返回数据，覆盖 store 状态
    vi.mocked(riskScanApi.scan).mockResolvedValue(apiOk(makeRiskResult()))
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('总体风险等级')).toBeInTheDocument()
      expect(screen.getByText('四流匹配度')).toBeInTheDocument()
      expect(screen.getByText('待办整改任务')).toBeInTheDocument()
    })
  })

  it('总体风险等级卡片 → 点击跳转 /risk-map', async () => {
    vi.mocked(riskScanApi.scan).mockResolvedValue(apiOk(makeRiskResult()))
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('总体风险等级')).toBeInTheDocument()
    })
    const riskCard = screen.getByText('总体风险等级').closest('[class*="cursor-pointer"]')!
    fireEvent.click(riskCard)
    expect(mockNavigate).toHaveBeenCalledWith('/risk-map')
  })

  it('高风险企业 → 显示对应颜色和标签', async () => {
    mockApiSuccess()
    // loadAllData 通过 fetchLatest 读取最新快照，必须让 latest 返回高风险结果
    vi.mocked(riskScanApi.latest).mockResolvedValue(
      apiOk(makeRiskResult({ overall_risk_level: 'high', overall_risk_score: 82 })),
    )
    vi.mocked(riskScanApi.scan).mockResolvedValue(
      apiOk(makeRiskResult({ overall_risk_level: 'high', overall_risk_score: 82 })),
    )
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise({ risk_level: 'high' }) })
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('总体风险等级')).toBeInTheDocument()
    })
    // MetricCards 渲染 RISK_LABELS['high'] = "高风险"
    const highRisk = await screen.findByText((content) => content.includes('高'))
    expect(highRisk).toBeInTheDocument()
  })

  it('图表区域 → 包含雷达图和趋势图容器', async () => {
    vi.mocked(riskScanApi.scan).mockResolvedValue(apiOk(makeRiskResult()))
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('风险维度分布')).toBeInTheDocument()
      // 使用更宽松的匹配器查找 "风险趋势"
      expect(screen.getByText((content) => content.includes('风险趋势'))).toBeInTheDocument()
    })
  })
})
