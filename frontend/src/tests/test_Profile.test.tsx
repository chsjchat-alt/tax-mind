/**
 * Profile 心理画像测试
 *
 * 测试策略：Mock @/api 的 profileApi，让真实 store 通过 mock API 获取数据。
 * 组件 mount 后 useEffect 调用 fetchLatest → mock API 返回 → store 更新 → 组件重渲染。
 *
 * 覆盖率目标：
 *   - 无企业 → EmptyState
 *   - 加载中 → LoadingSpinner
 *   - 无画像数据 → 提示 + 生成按钮
 *   - 有画像数据 → 总结卡 + 雷达图 + 六维详情 + 干预策略
 *   - 主导偏差识别 / 免责声明
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import Profile from '@/pages/Profile'
import { useEnterpriseStore, useProfileStore } from '@/store'

// ── Mock API（store 内 fetchLatest / generateProfile 通过 mock 获取数据） ──
const { mockLatest, mockGenerate } = vi.hoisted(() => {
  const latest = vi.fn()
  const generate = vi.fn().mockResolvedValue({
    data: { code: 200, message: 'success', data: { profile_id: 'gen-001', deviation_index: 50 } },
  })
  return { mockLatest: latest, mockGenerate: generate }
})

vi.mock('@/api', () => ({
  profileApi: {
    latest: mockLatest,
    generate: mockGenerate,
    list: vi.fn().mockResolvedValue({ data: { data: { profiles: [], total: 0 } } }),
  },
}))

// ── Mock 子组件 ──
vi.mock('@/components/profile', () => ({
  BiasRadarChart: ({ scores }: { scores: Record<string, number> }) => (
    <div data-testid="bias-radar-chart">
      {Object.entries(scores)
        .map(([k, v]) => `${k}:${v}`)
        .join(', ')}
    </div>
  ),
  BiasCard: ({
    biasKey,
    score,
    isDominant,
  }: {
    biasKey: string
    score: number
    isDominant: boolean
  }) => (
    <div data-testid={`bias-card-${biasKey}`} data-dominant={isDominant}>
      {biasKey}: {score}
      {isDominant ? ' (主导)' : ''}
    </div>
  ),
  ProfileSummary: ({
    deviationIndex,
    businessNarrative,
  }: {
    deviationIndex: number
    businessNarrative?: string
  }) => (
    <div data-testid="profile-summary">
      偏差指数: {deviationIndex}
      {businessNarrative && <p>{businessNarrative}</p>}
    </div>
  ),
  DisclaimerBanner: () => <div data-testid="disclaimer-banner">免责声明</div>,
  // 模拟数据生成器（供 Profile 页面无后端数据时回退使用）
  determineSizeTier: (revenue: number) => (revenue < 5_000_000 ? 'small' : revenue <= 50_000_000 ? 'medium' : 'large'),
  generateSimulatedProfile: () => ({
    scores: {
      control_desire: 50, loss_aversion: 45, optimism_bias: 42,
      control_illusion: 38, short_termism: 48, defensiveness: 40,
    },
    peerAverage: {
      control_desire: 48, loss_aversion: 42, optimism_bias: 40,
      control_illusion: 35, short_termism: 46, defensiveness: 38,
    },
  }),
}))

vi.mock('@/components/common', () => ({
  LoadingSpinner: ({ text }: { text?: string }) => (
    <div data-testid="loading-spinner">{text}</div>
  ),
  EmptyState: ({
    text,
    action,
  }: {
    text: string
    action?: React.ReactNode
  }) => (
    <div data-testid="empty-state">
      <span>{text}</span>
      {action && <div data-testid="action-area">{action}</div>}
    </div>
  ),
}))

// ── Helpers ──
const makeEnterprise = () => ({
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
})

type ProfileResultOverrides = {
  dominant_biases?: string[]
  intervention_strategy?: Record<string, string>
  business_narrative?: string
}

const makeProfileResult = (overrides: ProfileResultOverrides = {}) => ({
  profile_id: 'prof-001',
  enterprise_id: 'ent-001',
  assessment_date: '2025-06-15',
  control_desire_score: 72,
  loss_aversion_score: 45,
  optimism_bias_score: 30,
  control_illusion_score: 58,
  short_termism_score: 65,
  defensiveness_score: 20,
  deviation_index: 48,
  dominant_biases: ['control_desire', 'short_termism'],
  intervention_strategy: {
    control_desire: '建立对公账户管理制度',
    short_termism: '引入季度合规审查流程',
  },
  business_narrative: '该企业控制欲望较强，对私卡收款的依赖度偏高',
  technical_summary: '{}',
  ...overrides,
})

/** 生成 mock AxiosResponse：store 通过 res.data.data 获取 payload */
const apiOk = <T,>(data: T) => ({
  data: { code: 200, message: 'success', data },
})

const apiError = (code: number, message: string) => ({
  data: { code, message, data: null },
})

/** 等待 profile-summary 出现（异步 API 完成后） */
const waitForProfile = () =>
  waitFor(() => {
    expect(screen.getByTestId('profile-summary')).toBeInTheDocument()
  })

function renderProfile() {
  return render(<Profile />)
}

// ── 全局初始化 ──
beforeEach(() => {
  useEnterpriseStore.setState({ enterprises: [], currentEnterprise: null, listLoading: false, detailLoading: false })
  useProfileStore.setState({ result: null, loading: false, generating: false })
})

// ═══════════════════════════════════════════════════
describe('Profile — 空状态', () => {
  it('无企业 → EmptyState', () => {
    renderProfile()
    expect(screen.getByTestId('empty-state')).toHaveTextContent(/请先从顶部选择一家企业/)
  })
})

// ═══════════════════════════════════════════════════
describe('Profile — 加载中', () => {
  it('generating → LoadingSpinner', () => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() } as never)
    useProfileStore.setState({ generating: true })
    renderProfile()
    expect(screen.getByTestId('loading-spinner')).toHaveTextContent(/正在生成心理画像/)
  })

  it('loading → LoadingSpinner', () => {
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() } as never)
    useProfileStore.setState({ loading: true })
    renderProfile()
    expect(screen.getByTestId('loading-spinner')).toHaveTextContent(/正在加载画像数据/)
  })
})

// ═══════════════════════════════════════════════════
describe('Profile — 无画像数据', () => {
  it('API 返回无数据 → 回退到模拟数据渲染雷达图', async () => {
    // fetchLatest 返回 code!=200 → store 保持 result=null
    // generateProfile 也失败 → result 仍为 null
    mockLatest.mockResolvedValueOnce(apiError(40001, '未找到画像'))
    mockGenerate.mockResolvedValueOnce(apiError(50001, '生成失败'))

    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() } as never)
    renderProfile()

    // 等待 loading + generating 都完成
    await waitFor(() => {
      expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
    })

    // 应回退到模拟数据渲染，雷达图可见
    expect(screen.getByTestId('bias-radar-chart')).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('Profile — 有画像数据', () => {
  const profileData = makeProfileResult()

  beforeEach(() => {
    mockLatest.mockResolvedValue(apiOk(profileData))
    mockGenerate.mockResolvedValue(apiOk({ profile_id: 'prof-new', enterprise_id: 'ent-001', deviation_index: 48 }))
    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() } as never)
    useProfileStore.setState({ result: null, loading: false, generating: false })
  })

  it('画像总结卡 → 显示偏差指数', async () => {
    renderProfile()
    await waitForProfile()
    expect(screen.getByTestId('profile-summary')).toHaveTextContent('偏差指数: 48')
  })

  it('六维雷达图 → 存在', async () => {
    renderProfile()
    await waitForProfile()
    expect(screen.getByTestId('bias-radar-chart')).toBeInTheDocument()
  })

  it('主导偏差卡片 → 主导标记正确', async () => {
    renderProfile()
    await waitForProfile()
    const cdCard = screen.getAllByTestId('bias-card-control_desire')[0]
    expect(cdCard).toHaveAttribute('data-dominant', 'true')
  })

  it('六维详情 → 6 张卡片全部渲染', async () => {
    renderProfile()
    await waitForProfile()
    const dims = ['control_desire', 'loss_aversion', 'optimism_bias',
      'control_illusion', 'short_termism', 'defensiveness']
    for (const dim of dims) {
      expect(screen.getAllByTestId(`bias-card-${dim}`).length).toBeGreaterThanOrEqual(1)
    }
  })

  it('画像解读 → 商业叙事可见', async () => {
    renderProfile()
    await waitForProfile()
    expect(screen.getByText(/控制欲望较强，对私卡收款的依赖度偏高/)).toBeInTheDocument()
  })

  it('主导偏差建议区域可见', async () => {
    renderProfile()
    await waitForProfile()
    expect(screen.getByText('建议行动')).toBeInTheDocument()
  })

  it('免责声明 → 可见', async () => {
    renderProfile()
    await waitForProfile()
    expect(screen.getByTestId('disclaimer-banner')).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
describe('Profile — 无 dominant_biases 后端返回时', () => {
  it('后端未返回主导偏差 → 前端按评分排序取前 2', async () => {
    mockLatest.mockResolvedValueOnce(
      apiOk(makeProfileResult({ dominant_biases: [], intervention_strategy: {}, business_narrative: '无主导偏差' })),
    )

    useEnterpriseStore.setState({ currentEnterprise: makeEnterprise() } as never)
    useProfileStore.setState({ result: null, loading: false, generating: false })

    renderProfile()
    await waitForProfile()

    const cdCard = screen.getAllByTestId('bias-card-control_desire')[0]
    expect(cdCard).toHaveAttribute('data-dominant', 'true')
    const stCard = screen.getAllByTestId('bias-card-short_termism')[0]
    expect(stCard).toHaveAttribute('data-dominant', 'true')
  })
})
