/**
 * Simulator 风险模拟器测试
 *
 * 覆盖率目标：
 *   - 无企业 → EmptyState
 *   - 输入表单 → 默认值 + 参数调节
 *   - 点击模拟 → 加载中 → 结果展示
 *   - 结果展示 → 指数雪球图 + 组分分解表 + 损失框架 + 案例引用
 *   - 高风险企业 → 默认整改成本更高
 *   - 模拟失败 → 空状态提示
 *   - Trudge 降级 → 无后端数据时使用默认 SOP
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

import Simulator from '@/pages/Simulator'
import { useEnterpriseStore } from '@/store'
import type { Enterprise } from '@/types'

// ── Mock API ──
const mockSimulationRun = vi.fn()
const mockNBTIntervention = vi.fn()

vi.mock('@/api', () => ({
  simulationApi: {
    run: (...args: unknown[]) => mockSimulationRun(...args),
  },
  complianceApi: {
    nbtIntervention: (...args: unknown[]) => mockNBTIntervention(...args),
  },
}))

// ── Mock Recharts ──
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="snowball-chart">{children}</div>
  ),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ReferenceLine: () => null,
}))

// ── Mock 子组件 ──
vi.mock('@/components/simulator', () => ({
  SimulationInputForm: ({
    monthlyRevenue,
    taxRate,
    remediationCost,
    onSimulate,
    loading,
  }: {
    monthlyRevenue: number
    taxRate: number
    remediationCost: number
    riskLevel: string
    onSimulate: () => void
    loading: boolean
  }) => (
    <div data-testid="sim-form">
      <div>月营收: {monthlyRevenue}</div>
      <div>税率: {taxRate}</div>
      <div>整改成本: {remediationCost}</div>
      <button onClick={onSimulate} disabled={loading}>
        开始模拟
      </button>
    </div>
  ),
  LossFrameMessage: ({
    totalLoss,
    remediationCost,
  }: {
    totalLoss: number
    remediationCost: number
  }) => (
    <div data-testid="loss-frame">
      总损失: {totalLoss}万, 整改仅需: {remediationCost}万
    </div>
  ),
  CaseStudyCard: ({ index }: { index: number }) => (
    <div data-testid={`case-study-${index}`}>案例 #{index + 1}</div>
  ),
  TrudgeChecklist: ({
    title,
    tasks,
    closing,
  }: {
    title: string
    tasks: Array<{ task_id: number; task_name: string }>
    framework: string
    closing: string
  }) => (
    <div data-testid="trudge-checklist">
      <h4>{title}</h4>
      <ul>
        {tasks.map((t) => (
          <li key={t.task_id}>{t.task_name}</li>
        ))}
      </ul>
      <p>{closing}</p>
    </div>
  ),
  // 以下导出仅在对应数据存在时渲染，测试用例不关心其内容 → 空实现
  ThirdPartyConsequenceCard: () => null,
  PeerPressureCard: () => null,
  OfficialNoticeCard: () => null,
  NPTMixBar: () => null,
  TrudgeToolbox: () => null,
}))

vi.mock('@/components/charts', () => ({
  ExponentialSnowballChart: () => <div data-testid="snowball-chart" />,
}))

vi.mock('@/components/common', () => ({
  LoadingSpinner: ({ text }: { text?: string }) => (
    <div data-testid="loading-spinner">{text}</div>
  ),
  EmptyState: ({ text }: { text: string }) => (
    <div data-testid="empty-state">{text}</div>
  ),
  TableContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="table-container">{children}</div>
  ),
}))

// ── Helpers ──
function makeEnterprise(overrides: Partial<Enterprise> = {}): Enterprise {
  return {
    id: 'ent-001',
    name: '测试企业',
    industry: '批发零售',
    revenue_annual: 5000000,
    employee_count: 80,
    credit_code: '91330100MA00000001',
    tax_rate_claimed: 3.0,
    cost_rate_claimed: 85,
    is_high_tech: false,
    is_small_micro: true,
    risk_level: 'medium',
    created_at: '2025-01-01',
    updated_at: '2025-06-01',
    ...overrides,
  }
}

function makeSimulationResult(overrides = {}) {
  return {
    data: {
      code: 200,
      message: 'success',
      data: {
        time_points: [
          {
            period: '6months',
            months_elapsed: 6,
            path_a_cost: 3000000,
            path_b_cost: 300000,
            cost_difference: 2700000,
            audit_probability: 0.35,
            expected_penalty: 1500000,
            expected_late_fee: 500000,
            total_hidden_tax: 180000,
          },
          {
            period: '1year',
            months_elapsed: 12,
            path_a_cost: 6000000,
            path_b_cost: 300000,
            cost_difference: 5700000,
            audit_probability: 0.60,
            expected_penalty: 3000000,
            expected_late_fee: 1000000,
            total_hidden_tax: 360000,
          },
          {
            period: '3years',
            months_elapsed: 36,
            path_a_cost: 18000000,
            path_b_cost: 300000,
            cost_difference: 17700000,
            audit_probability: 0.95,
            expected_penalty: 9000000,
            expected_late_fee: 3000000,
            total_hidden_tax: 1080000,
          },
        ],
        recommendation: '建议立即整改',
        loss_frame_message: '维持现状将导致巨额罚款',
        technical_summary: '{"audit_probabilities": [0.35, 0.6, 0.95]}',
        case_references: [
          { title: '案例A', penalty: 500000 },
          { title: '案例B', penalty: 800000 },
          { title: '案例C', penalty: 1200000 },
        ],
        ...overrides,
      },
    },
  }
}

function renderSimulator() {
  return render(<Simulator />)
}

beforeEach(() => {
  useEnterpriseStore.setState({
    enterprises: [],
    currentEnterprise: null,
  })
  vi.clearAllMocks()
  mockSimulationRun.mockResolvedValue(makeSimulationResult())
  mockNBTIntervention.mockRejectedValue(new Error('no LLM'))
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ═══════════════════════════════════════════════════
describe('Simulator — 空状态', () => {
  it('无企业 → EmptyState', () => {
    renderSimulator()
    expect(screen.getByTestId('empty-state')).toHaveTextContent(/请先从顶部选择一家企业/)
  })
})

// ═══════════════════════════════════════════════════
describe('Simulator — 输入表单', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
  })

  it('初始渲染 → 默认参数可见', () => {
    renderSimulator()
    expect(screen.getByText('月营收: 50')).toBeInTheDocument()
    expect(screen.getByText('税率: 6')).toBeInTheDocument()
    // 中等风险默认整改成本 40
    expect(screen.getByText('整改成本: 40')).toBeInTheDocument()
  })

  it('高风险企业 → 默认整改成本为 80', () => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise({ risk_level: 'high' }),
    })
    renderSimulator()
    expect(screen.getByText('整改成本: 80')).toBeInTheDocument()
  })

  it('低风险企业 → 默认整改成本为 20', () => {
    useEnterpriseStore.setState({
      currentEnterprise: makeEnterprise({ risk_level: 'low' }),
    })
    renderSimulator()
    expect(screen.getByText('整改成本: 20')).toBeInTheDocument()
  })

  it('无结果 → 默认空状态提示文本', () => {
    renderSimulator()
    expect(
      screen.getByText(/配置参数后点击「开始模拟」查看双路径对比结果/),
    ).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('Simulator — 模拟执行', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
  })

  it('点击模拟 → 显示 LoadingSpinner', async () => {
    // 永不 resolve 保持 loading 状态
    mockSimulationRun.mockReturnValue(new Promise(() => {}))
    renderSimulator()

    const btn = screen.getByRole('button', { name: /开始模拟/ })
    fireEvent.click(btn)

    expect(
      await screen.findByText(/正在运行风险模拟与行为干预分析/),
    ).toBeInTheDocument()
  })

  it('模拟成功 → 双路径对比标题可见', async () => {
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(
        screen.getByText('双路径对比：维持现状 vs 主动整改'),
      ).toBeInTheDocument()
    })
  })

  it('模拟成功 → 雪球组分分解表显示 3 个时间节点', async () => {
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(screen.getByText('指数雪球组分分解')).toBeInTheDocument()
    })

    // 3 个时间节点
    expect(screen.getByText('6个月')).toBeInTheDocument()
    expect(screen.getByText('1年')).toBeInTheDocument()
    expect(screen.getByText('3年')).toBeInTheDocument()
  })

  it('损失框架话术 → 计算 totalLoss + 显示', async () => {
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(screen.getByTestId('loss-frame')).toBeInTheDocument()
    })
  })

  it('案例引用 → 3 个案例卡片', async () => {
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(screen.getByTestId('case-study-0')).toBeInTheDocument()
      expect(screen.getByTestId('case-study-1')).toBeInTheDocument()
      expect(screen.getByTestId('case-study-2')).toBeInTheDocument()
    })
  })

  it('模拟建议 → 显示推荐文案', async () => {
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(screen.getByText('建议立即整改')).toBeInTheDocument()
    })
  })
})

// ═══════════════════════════════════════════════════
describe('Simulator — Trudge 降级', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
  })

  it('无后端 NBT 数据 → 使用默认 5 个 SOP 微任务', async () => {
    mockNBTIntervention.mockRejectedValue(new Error('no LLM'))

    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(screen.getByTestId('trudge-checklist')).toBeInTheDocument()
    })

    // 默认 SOP 标题
    expect(
      screen.getByText('企业财税合规整改标准作业程序（SOP）'),
    ).toBeInTheDocument()

    // 默认 5 个微任务
    expect(screen.getByText('审查日常业务税务管理制度设计')).toBeInTheDocument()
    expect(
      screen.getByText('核实关联方无形劳务真实性'),
    ).toBeInTheDocument()
    expect(screen.getByText('成本费用凭证全面自查')).toBeInTheDocument()
    expect(
      screen.getByText('发票流-资金流一致性比对'),
    ).toBeInTheDocument()
    expect(screen.getByText('建立税务内控台账')).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('Simulator — 模拟失败', () => {
  beforeEach(() => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() })
  })

  it('模拟失败 → 显示空状态提示', async () => {
    mockSimulationRun.mockRejectedValue(new Error('Network error'))
    renderSimulator()
    fireEvent.click(screen.getByRole('button', { name: /开始模拟/ }))

    await waitFor(() => {
      expect(
        screen.getByText(/配置参数后点击「开始模拟」查看双路径对比结果/),
      ).toBeInTheDocument()
    })
  })
})
