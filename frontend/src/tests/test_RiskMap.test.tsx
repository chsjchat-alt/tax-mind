/**
 * RiskMap 测试
 *
 * 覆盖率目标：
 *   - 无企业 → EmptyState
 *   - 加载中 → LoadingSpinner
 *   - 无扫描结果 → 提示执行风险扫描
 *   - 有数据 → 商业模式 banner + 双轨仪表盘 + 7 维卡片网格
 *   - 高风险渲染 → 红色背景 + 损失框架对比
 *   - 语言切换 → 业务叙事 / 技术摘要
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

import RiskMap from '@/pages/RiskMap'
import { useEnterpriseStore, useRiskStore } from '@/store'
import { enterpriseApi, riskScanApi } from '@/api'
import type { Enterprise, RiskScanResult } from '@/types'

// ── Mock API ──
vi.mock('@/api', () => ({
  riskScanApi: {
    scan: vi.fn().mockResolvedValue({ data: { data: null } }),
    latest: vi.fn().mockResolvedValue({ data: { data: null } }),
    trajectory: vi.fn().mockResolvedValue({ data: { data: { trajectories: [], total: 0 } } }),
  },
  enterpriseApi: {
    list: vi.fn(),
    detail: vi.fn().mockResolvedValue({ data: { data: { compliance: null } } }),
  },
}))

// ── Mock Recharts ──
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children,
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: () => null,
  Cell: () => null,
  Legend: () => null,
}))

// ── Mock 子组件（隔离测试页面逻辑） ──
vi.mock('@/components/riskmap', () => ({
  RiskLegend: () => <div data-testid="risk-legend">图例</div>,
  LanguageToggle: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (v: string) => void
  }) => (
    <button data-testid="lang-toggle" onClick={() => onChange(value === 'business' ? 'technical' : 'business')}>
      {value}
    </button>
  ),
  RiskMapCard: ({
    dimKey,
    dimName,
    score,
  }: {
    dimKey: string
    dimName: string
    score: number
  }) => (
    <div data-testid={`risk-card-${dimKey}`}>
      {dimName}: {score}
    </div>
  ),
}))

vi.mock('@/components/charts', () => ({
  DualCostGauge: () => <div data-testid="dual-cost-gauge" />,
  TaxBurdenElasticityChart: () => <div data-testid="tax-burden-elasticity" />,
}))

vi.mock('@/components/common', () => ({
  LoadingSpinner: ({ text }: { text?: string }) => (
    <div data-testid="loading-spinner">{text}</div>
  ),
  EmptyState: ({ text }: { text: string }) => (
    <div data-testid="empty-state">{text}</div>
  ),
  TableContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="table-container">{children}</div>
  ),
}))

// ── Helpers ──
function makeEnterprise(overrides: Partial<Enterprise> = {}): Enterprise {
  return {
    id: 'ent-001',
    name: '测试制造企业',
    industry: '制造',
    revenue_annual: 10000000,
    employee_count: 200,
    credit_code: '91330100MA00000001',
    tax_rate_claimed: 5.0,
    cost_rate_claimed: 72,
    is_high_tech: true,
    is_small_micro: false,
    risk_level: 'medium',
    created_at: '2025-01-01',
    updated_at: '2025-06-01',
    ...overrides,
  }
}

function makeRiskResult(overrides: Partial<RiskScanResult> = {}): RiskScanResult {
  return {
    risk_assessment_id: 'ra-001',
    enterprise_id: 'ent-001',
    overall_risk_level: 'medium',
    overall_risk_score: 55,
    four_flow_match_score: 72,
    private_card_ratio: 15,
    cost_deviation: 12,
    dimension_scores: {
      private_card_ratio: 45,
      cost_deviation: 38,
      tax_burden_deviation: 60,
      four_flow_mismatch: 28,
      invoice_bank_mismatch: 15,
      large_personal_transfer: 52,
      input_output_imbalance: 65,
    },
    dim_details: {
      private_card_ratio: { detail: '私卡偏高', technical_detail: 'ratio=15%' },
      cost_deviation: { detail: '成本略高', technical_detail: 'dev=12pp' },
    },
    recommendations: {},
    business_narrative: '企业存在中等风险，建议关注私卡收款',
    technical_summary: '{"scores": {"overall": 55}}',
    assessment_date: '2025-06-15',
    ...overrides,
  }
}

function renderRiskMap() {
  return render(<RiskMap />)
}

beforeEach(() => {
  useEnterpriseStore.setState({
    enterprises: [],
    currentEnterprise: null,
  })
  useRiskStore.setState({
    result: null,
    status: 'idle',
    pendingAction: null,
  })
  vi.clearAllMocks()
  // 重新建立 mock 实现（afterEach 的 restoreAllMocks 会清空工厂里的实现，
  // 否则 enterpriseApi.detail 返回 undefined 导致 RiskMap.tsx:197 .then 崩溃）
  vi.mocked(enterpriseApi.detail).mockResolvedValue(
    { data: { code: 200, message: 'success', data: { compliance: null } } } as unknown as Awaited<ReturnType<typeof enterpriseApi.detail>>,
  )
  vi.mocked(riskScanApi.latest).mockResolvedValue(
    { data: { code: 200, message: 'success', data: null } } as unknown as Awaited<ReturnType<typeof riskScanApi.latest>>,
  )
  vi.mocked(riskScanApi.trajectory).mockResolvedValue(
    { data: { code: 200, message: 'success', data: { trajectories: [], total: 0 } } } as unknown as Awaited<ReturnType<typeof riskScanApi.trajectory>>,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ═══════════════════════════════════════════════════
describe('RiskMap — 空状态', () => {
  it('无企业 → EmptyState 提示选择企业', () => {
    // scanRisk 被 useEffect 调用会触发 pending → 但不影响空企业判断
    renderRiskMap()
    expect(screen.getByTestId('empty-state')).toHaveTextContent(/请先从顶部选择一家企业/)
  })
})

// ═══════════════════════════════════════════════════
describe('RiskMap — 加载中', () => {
  it('loading=true → LoadingSpinner', () => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise(),
    })
    useRiskStore.setState({ status: 'pending', pendingAction: 'scanRisk', scanRisk: async () => {} })

    renderRiskMap()
    expect(screen.getByTestId('loading-spinner')).toHaveTextContent(/正在加载风险数据/)
  })
})

// ═══════════════════════════════════════════════════
describe('RiskMap — 无扫描结果', () => {
  it('企业选中但无结果 → 提示执行风险扫描', () => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise(),
    })
    useRiskStore.setState({
      result: null,
      status: 'idle',
      scanRisk: async () => {},
      fetchLatest: async () => {},  // 阻止 mount effect 把 status 置为 pending
    })

    renderRiskMap()
    expect(screen.getByTestId('empty-state')).toHaveTextContent(/尚未执行风险扫描/)
  })
})

// ═══════════════════════════════════════════════════
describe('RiskMap — 有数据', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise(),
    })
    useRiskStore.setState({
      result: makeRiskResult(),
      status: 'success',
      scanRisk: async () => {},  // 数据已就绪，阻止 useEffect 触发 re-scan
      fetchLatest: async () => {},  // 阻止 mount effect 用空数据覆盖注入的 result
    })
  })

  it('商业模式 banner → 显示"重资产制造"标签', () => {
    renderRiskMap()
    expect(screen.getByText('重资产制造')).toBeInTheDocument()
    expect(screen.getByText(/测试制造企业/)).toBeInTheDocument()
  })

  it('轻资产企业 → 显示"轻资产服务"', () => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise({ industry: '电商' }),
    })
    renderRiskMap()
    expect(screen.getByText('轻资产服务')).toBeInTheDocument()
  })

  it('图例 + 语言切换按钮可见', () => {
    renderRiskMap()
    expect(screen.getByTestId('risk-legend')).toBeInTheDocument()
    expect(screen.getByTestId('lang-toggle')).toBeInTheDocument()
  })

  it('宏观内控雷达区 → 双轨仪表盘', () => {
    renderRiskMap()
    expect(screen.getByText('宏观内控雷达监测')).toBeInTheDocument()
    expect(screen.getByTestId('dual-cost-gauge')).toBeInTheDocument()
    expect(screen.getByTestId('tax-burden-elasticity')).toBeInTheDocument()
  })

  // ── 老板视角专属功能 ──
  it('老板视角 → 5 个 KPI 概览卡片', () => {
    renderRiskMap()
    // 综合风险评分、合规得分、预计稽查概率、高危风险维度、预估补税·罚款
    expect(screen.getByText('综合风险评分')).toBeInTheDocument()
    expect(screen.getByText('合规得分')).toBeInTheDocument()
    expect(screen.getByText('预计稽查概率')).toBeInTheDocument()
    expect(screen.getByText('高危风险维度')).toBeInTheDocument()
    expect(screen.getByText('预估补税·罚款')).toBeInTheDocument()
  })

  // ── A3：合规得分换算（风险分 = 100 − 合规得分） ──
  it('老板视角 → 合规得分卡片（100 − 风险分换算）', () => {
    renderRiskMap()
    // adjustedRiskScore = round(55 * (1-0)) = 55 → 合规得分 = 100 − 55 = 45
    expect(screen.getByTestId('compliance-score')).toHaveTextContent('45')
    expect(screen.getByText(/100 − 风险分/)).toBeInTheDocument()
    // 无合规调整时风险分卡片不展示"原始风险分"副文案
    expect(screen.queryByText(/原始风险分/)).not.toBeInTheDocument()
  })

  // ── A1：整改前后评分演化（轨迹证据链） ──
  it('老板视角 → 整改前后评分演化（整改完成轨迹）', async () => {
    vi.mocked(riskScanApi.trajectory).mockResolvedValue(
      { data: { code: 200, message: 'success', data: {
        trajectories: [{
          id: 'tr-001',
          enterprise_id: 'ent-001',
          assessment_date: '2025-07-01T00:00:00',
          before_score: 55,
          after_score: 35,
          before_level: 'medium',
          after_level: 'medium',
          level_jump: 'down',
          changed_by: 'remediation',
          reason: '完成四流匹配整改',
          created_at: '2025-07-01T00:00:00',
        }],
        total: 1,
      } } } as unknown as Awaited<ReturnType<typeof riskScanApi.trajectory>>,
    )
    renderRiskMap()
    await waitFor(() => {
      expect(screen.getByText('整改前后评分演化')).toBeInTheDocument()
    })
    // 整改后风险分 + 改善标记 + 原因
    expect(screen.getByText('35')).toBeInTheDocument()
    expect(screen.getByText('改善')).toBeInTheDocument()
    expect(screen.getByText(/完成四流匹配整改/)).toBeInTheDocument()
    expect(screen.getByText('整改完成')).toBeInTheDocument()
  })

  it('老板视角 → 核心风险聚焦（高危 + 中危）', () => {
    renderRiskMap()
    expect(screen.getByText('核心风险聚焦')).toBeInTheDocument()
    // medium >=40: private_card_ratio=45, tax_burden_deviation=60, large_personal_transfer=52, input_output_imbalance=65 → 4
    expect(screen.getByText(/共4个需关注维度/)).toBeInTheDocument()
    // low <40 (已达标): cost_deviation=38, four_flow_mismatch=28, invoice_bank_mismatch=15 → 3
    expect(screen.getByText(/3 个维度处于健康状态/)).toBeInTheDocument()
  })

  it('老板视角 → 业务总述内容可见', () => {
    renderRiskMap()
    expect(screen.getByText('企业风险评估')).toBeInTheDocument()
    expect(screen.getByText(/企业存在中等风险/)).toBeInTheDocument()
  })

  it('老板视角 → 决策建议区域可见', () => {
    renderRiskMap()
    expect(screen.getByText('决策建议')).toBeInTheDocument()
    expect(screen.getByText('合规整改优先级')).toBeInTheDocument()
    expect(screen.getByText('税务筹划窗口')).toBeInTheDocument()
  })

  it('老板视角 → 宏观内控雷达监测区域可见', () => {
    renderRiskMap()
    expect(screen.getByText('宏观内控雷达监测')).toBeInTheDocument()
    expect(screen.getByTestId('dual-cost-gauge')).toBeInTheDocument()
    expect(screen.getByTestId('tax-burden-elasticity')).toBeInTheDocument()
  })

  // ── 财务视角专属功能 ──
  it('财务视角 → 切换后显示维度统计摘要', async () => {
    renderRiskMap()
    // 先切换到财务视角
    const toggle = screen.getByTestId('lang-toggle')
    fireEvent.click(toggle)
    // medium_high (>=55): tax_burden_deviation=60, input_output_imbalance=65 → 2
    // medium (>=40,<55): private_card_ratio=45, large_personal_transfer=52 → 2
    // low (<40): cost_deviation=38, four_flow_mismatch=28, invoice_bank_mismatch=15 → 3
    await waitFor(() => {
      expect(screen.getByText(/2 个中风险维度/)).toBeInTheDocument()
    })
    expect(screen.getByText(/3 个低风险维度/)).toBeInTheDocument()
  })

  it('财务视角 → 7 维卡片网格全部渲染', async () => {
    renderRiskMap()
    // 切换到财务视角
    const toggle = screen.getByTestId('lang-toggle')
    fireEvent.click(toggle)
    const dims = [
      'private_card_ratio',
      'cost_deviation',
      'tax_burden_deviation',
      'four_flow_mismatch',
      'invoice_bank_mismatch',
      'large_personal_transfer',
      'input_output_imbalance',
    ]
    await waitFor(() => {
      for (const dim of dims) {
        expect(screen.getByTestId(`risk-card-${dim}`)).toBeInTheDocument()
      }
    })
  })

  it('财务视角 → 财务影响量化分析卡片', async () => {
    renderRiskMap()
    const toggle = screen.getByTestId('lang-toggle')
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.getByText('财务影响量化分析')).toBeInTheDocument()
    })
    expect(screen.getByText('预估补税额')).toBeInTheDocument()
    expect(screen.getByText('预估罚款·滞纳金')).toBeInTheDocument()
    expect(screen.getByText('最大风险敞口')).toBeInTheDocument()
  })

  it('财务视角 → 技术摘要 JSON 内容', async () => {
    renderRiskMap()
    const toggle = screen.getByTestId('lang-toggle')
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.getByText('技术摘要')).toBeInTheDocument()
    })
    expect(screen.getByText(/{"scores": {"overall": 55}}/)).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('RiskMap — 高压渲染（高风险）', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise(),
    })
    useRiskStore.setState({
      result: makeRiskResult({
        overall_risk_level: 'high',
        overall_risk_score: 85,
        dimension_scores: {
          private_card_ratio: 75,
          cost_deviation: 80,
          tax_burden_deviation: 88,
          four_flow_mismatch: 72,
          invoice_bank_mismatch: 60,
          large_personal_transfer: 70,
          input_output_imbalance: 78,
        },
      }),
      status: 'success',
      scanRisk: async () => {},  // 数据已就绪，阻止 useEffect 触发 re-scan
      fetchLatest: async () => {},  // 阻止 mount effect 用空数据覆盖注入的 result
    })
  })

  it('高风险 → 老板视角：红色 banner + 预警 + 核心风险聚焦', () => {
    renderRiskMap()
    // 预警 banner 同步渲染，无需 waitFor
    expect(screen.getByText(/预计稽查概率 80%/)).toBeInTheDocument()
    expect(screen.getByText(/请立即关注风险指标/)).toBeInTheDocument()
    // 老板视角：核心风险聚焦 — 高危等级按类别计数（严重/高危各 1，共计 2 类）
    expect(screen.getByText(/需优先关注的2个高危等级/)).toBeInTheDocument()
    expect(screen.getByText(/7.*需关注维度/)).toBeInTheDocument()
  })

  it('高风险 → 财务视角：维度统计文案 + 财务影响量化', async () => {
    renderRiskMap()
    // 切换到财务视角
    const toggle = screen.getByTestId('lang-toggle')
    fireEvent.click(toggle)

    await waitFor(() => {
      // 1 严重 + 5 高风险 + 1 中高风险
      expect(screen.getByText(/5 个高风险维度/)).toBeInTheDocument()
    })
    expect(screen.getByText(/1 个中高风险维度/)).toBeInTheDocument()
    // 财务影响量化分析在财务视角显示
    expect(screen.getByText('财务影响量化分析')).toBeInTheDocument()
  })
})

