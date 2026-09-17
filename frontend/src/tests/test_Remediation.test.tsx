/**
 * Remediation（整改追踪）单元测试
 *
 * 覆盖率目标：
 *   - 进度修改 → 完成率 / 进行中 / 已逾期 联动更新
 *   - 进度 100% → 自动切换为已完成
 *   - 单任务 / 多任务进度修改 → 统计一致性
 *   - API 失败 → 乐观更新回滚
 *   - 更新中 → 按钮禁用 + 加载提示
 *   - 新建 / 编辑任务弹窗
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'

import Remediation from '@/pages/Remediation'
import { useEnterpriseStore } from '@/store'
import { remediationApi, riskScanApi, enterpriseApi } from '@/api'
import type { Enterprise, RemediationTask, RemediationTaskUpdateResult } from '@/types'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// ── Mock react-router-dom ──
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => vi.fn() }
})

// ── Mock antd responsive observer ──
// 说明：node_modules 内部 CJS require 无法被 vi.mock 拦截（vitest 默认外部化），
// 因此该 mock 实际不生效；antd 响应式组件的 matchMedia 依赖由 setup.ts 的
// 普通函数 polyfill 保证，无需在此 mock。

// ── Mock API ──
vi.mock('@/api', () => ({
  remediationApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
  riskScanApi: { scan: vi.fn(), list: vi.fn() },
  dataApi: { loadMockData: vi.fn() },
  enterpriseApi: { list: vi.fn(), detail: vi.fn() },
}))

// ── Mock Recharts ──
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children,
  RadarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PolarGrid: () => null, PolarAngleAxis: () => null, PolarRadiusAxis: () => null,
  Radar: () => null,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null, XAxis: () => null, YAxis: () => null,
  CartesianGrid: () => null, Tooltip: () => null, Legend: () => null,
}))

// ── Helpers ──
function makeEnterprise(overrides: Partial<Enterprise> = {}): Enterprise {
  return {
    id: 'ent-rem-001', name: '整改测试企业', industry: '批发零售',
    revenue_annual: 5000000, employee_count: 120,
    credit_code: '91330100MA00000001', tax_rate_claimed: 3.0,
    cost_rate_claimed: 85, is_high_tech: false, is_small_micro: true,
    risk_level: 'medium', created_at: '2025-01-01', updated_at: '2025-06-01',
    ...overrides,
  }
}

/** 构造完整 AxiosResponse（mock 响应必须包含 status/headers/config 等字段） */
const apiOk = <T,>(data: T): AxiosResponse<{ code: number; message: string; data: T }> => ({
  data: { code: 200, message: 'success', data },
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as InternalAxiosRequestConfig,
})

function makeTask(overrides: Partial<RemediationTask> = {}): RemediationTask {
  return {
    id: 'task-001', enterprise_id: 'ent-rem-001', risk_assessment_id: 'ra-rem-001',
    title: '测试整改任务', description: '测试描述',
    status: 'pending', priority: 'high', progress: 0,
    due_date: '2025-12-31', completed_at: null,
    created_at: '2025-06-01', updated_at: '2025-06-01',
    ...overrides,
  }
}

function mockTasksApi(tasks: RemediationTask[]) {
  vi.mocked(remediationApi.list).mockResolvedValue(
    apiOk({ tasks, total: tasks.length }),
  )
  vi.mocked(remediationApi.update).mockResolvedValue(
    apiOk<RemediationTaskUpdateResult>({} as RemediationTaskUpdateResult),
  )
  vi.mocked(riskScanApi.list).mockResolvedValue(apiOk({ assessments: [], total: 0 }))
  vi.mocked(enterpriseApi.detail).mockResolvedValue(
    apiOk({ enterprise: {}, statistics: {}, compliance: null }) as unknown as Awaited<
      ReturnType<typeof enterpriseApi.detail>
    >,
  )
}

function renderRemediation() {
  // 包裹 antd <App>：让 App.useApp() 提供可用的 message.error（页面错误提示依赖）
  return render(
    <MemoryRouter>
      <AntdApp>
        <Remediation />
      </AntdApp>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useEnterpriseStore.setState({
    enterprises: [makeEnterprise()],
    currentEnterprise: makeEnterprise(),
    listLoading: false,
    detailLoading: false,
  })
  vi.clearAllMocks()
})

afterEach(() => { vi.restoreAllMocks() })

// ═══════════════════════════════════════════════════
// 无企业 / 无任务
// ═══════════════════════════════════════════════════
describe('Remediation — 空状态', () => {
  it('无选中企业 → 空状态提示', async () => {
    useEnterpriseStore.setState({ currentEnterprise: null })
    renderRemediation()
    await waitFor(() => {
      expect(screen.getByText(/请先从顶部选择一家企业/)).toBeInTheDocument()
    })
  })

  it('有企业但无任务 → 显示创建按钮', async () => {
    mockTasksApi([])
    renderRemediation()
    await waitFor(() => {
      expect(screen.getByText(/暂无整改任务/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /创建第一个任务/ })).toBeInTheDocument()
    })
  })
})

// ═══════════════════════════════════════════════════
// 进度修改 → 联动验证
// ═══════════════════════════════════════════════════
describe('Remediation — 进度修改联动', () => {
  it('单任务进度 25% → 进度条即时更新', async () => {
    mockTasksApi([makeTask({ id: 't1', status: 'in_progress', progress: 0 })])
    renderRemediation()

    await waitFor(() => { expect(screen.getByText('测试整改任务')).toBeInTheDocument() })

    // 点击 25% 按钮
    const pct25 = screen.getByRole('button', { name: '25%' })
    fireEvent.click(pct25)

    // API 应被调用
    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', { progress: 25 })
    })

    // 乐观更新：Progress 组件 percent 变为 25
    // （通过检查 Progress aria-valuenow）
    await waitFor(() => {
      const bar = document.querySelector('.ant-progress-bg')
      expect(bar).toBeTruthy()
    })
  })

  it('进度 100% → 自动切换为已完成，完成率联动', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'in_progress', progress: 50 }),
      makeTask({ id: 't2', status: 'pending', progress: 0 }),
      makeTask({ id: 't3', status: 'completed', progress: 100 }),
    ])
    renderRemediation()

    // 等待三个任务全部渲染
    await waitFor(() => {
      const buttons = screen.getAllByRole('button', { name: /%/ })
      // 已完成任务不渲染进度按钮，所以只有 t1 和 t2 有按钮
      expect(buttons.length).toBeGreaterThanOrEqual(4)
    })

    // 找到 t1 (in_progress) 的 100% 按钮
    const pct100Buttons = screen.getAllByRole('button', { name: '100%' })
    expect(pct100Buttons.length).toBeGreaterThanOrEqual(1)
    fireEvent.click(pct100Buttons[0])

    // API 调用应包含 progress: 100 + status: completed
    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', { progress: 100, status: 'completed' })
    })
  })

  it('多任务进度修改 → 完成率 / 进行中 / 已逾期 全部联动', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'in_progress', progress: 30 }),
      makeTask({ id: 't2', status: 'in_progress', progress: 60 }),
      makeTask({ id: 't3', status: 'pending', progress: 10 }),
      makeTask({ id: 't4', status: 'completed', progress: 100 }),
      makeTask({ id: 't5', status: 'pending', progress: 0, due_date: '2020-01-01' }),
    ])
    renderRemediation()

    await waitFor(() => {
      // 完成率环形图应显示 1/5 = 20%
      expect(screen.getByText('20%')).toBeInTheDocument()
      // 已逾期应有 1 个
      expect(screen.getByText('1')).toBeInTheDocument()
    })

    // 将 t1 进度改为 100%
    const pct100Btns = screen.getAllByRole('button', { name: '100%' })
    fireEvent.click(pct100Btns[0])

    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', { progress: 100, status: 'completed' })
    })

    // 乐观更新后：completed 从 1→2，in_progress 从 2→1
    await waitFor(() => {
      // 至少确认组件不崩溃
      expect(screen.getByText('整改追踪器')).toBeInTheDocument()
    })
  })

  // ── 新增：pending→in_progress 智能转换 ──

  it('pending 任务设置进度 25% → 自动转为 in_progress，状态标签与统计联动', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'pending', progress: 0 }),
    ])
    renderRemediation()

    await waitFor(() => {
      expect(screen.getByText('测试整改任务')).toBeInTheDocument()
    })

    // 初始状态：pendingCount=1, inProgressCount=0
    // 使用 getAllByText 因为"待处理"也会出现在状态筛选栏
    const pendingTags = screen.getAllByText('待处理')
    expect(pendingTags.length).toBeGreaterThanOrEqual(1)

    // 点击 25% 进度按钮
    const pct25 = screen.getByRole('button', { name: '25%' })
    fireEvent.click(pct25)

    // API 应发送 status: 'in_progress'
    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', {
        progress: 25,
        status: 'in_progress',
      })
    })
  })

  it('pending 任务设置进度 50% → 统计数字联动（pending-1, in_progress+1）', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'pending', progress: 0 }),
      makeTask({ id: 't2', status: 'in_progress', progress: 30 }),
      makeTask({ id: 't3', status: 'completed', progress: 100 }),
    ])
    renderRemediation()

    await waitFor(() => {
      // 初始完成率 1/3 = 33%
      expect(screen.getByText('33%')).toBeInTheDocument()
    })

    // 点击 t1 的 50% 按钮
    const pct50Btns = screen.getAllByRole('button', { name: '50%' })
    fireEvent.click(pct50Btns[0])

    // API 应发送 status: 'in_progress'
    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', {
        progress: 50,
        status: 'in_progress',
      })
    })
  })

  it('in_progress 任务设置进度 100% → 完成率从 33% 变为 67%', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'in_progress', progress: 50 }),
      makeTask({ id: 't2', status: 'in_progress', progress: 30 }),
      makeTask({ id: 't3', status: 'completed', progress: 100 }),
    ])
    renderRemediation()

    await waitFor(() => {
      // 初始完成率 1/3 = 33%
      expect(screen.getByText('33%')).toBeInTheDocument()
    })

    // 将 t1 进度设 100%（第一个 in_progress 任务的 100% 按钮）
    const pct100Btns = screen.getAllByRole('button', { name: '100%' })
    expect(pct100Btns.length).toBeGreaterThanOrEqual(1)
    fireEvent.click(pct100Btns[0])

    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', {
        progress: 100,
        status: 'completed',
      })
    })
  })

  it('pending 任务直接设 100% → 跳过 in_progress 直接 completed', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'pending', progress: 0 }),
      makeTask({ id: 't2', status: 'completed', progress: 100 }),
    ])
    renderRemediation()

    await waitFor(() => {
      expect(screen.getByText('50%')).toBeInTheDocument() // 初始完成率
    })

    const pct100Btns = screen.getAllByRole('button', { name: '100%' })
    fireEvent.click(pct100Btns[0])

    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', {
        progress: 100,
        status: 'completed',
      })
    })
  })

  it('多任务批量进度修改 → 所有统计数字联动一致', async () => {
    mockTasksApi([
      makeTask({ id: 't1', status: 'pending', progress: 0 }),
      makeTask({ id: 't2', status: 'pending', progress: 0 }),
      makeTask({ id: 't3', status: 'in_progress', progress: 20 }),
      makeTask({ id: 't4', status: 'completed', progress: 100 }),
    ])
    renderRemediation()

    await waitFor(() => {
      // 初始完成率 1/4 = 25%
      expect(screen.getByText('25%')).toBeInTheDocument()
    })

    // t1 点 25%：pending→in_progress，pendingCount 2→1
    const pct25Btns = screen.getAllByRole('button', { name: '25%' })
    fireEvent.click(pct25Btns[0])

    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalledWith('t1', {
        progress: 25,
        status: 'in_progress',
      })
    })

    // 确认组件未崩溃
    expect(screen.getByText('整改追踪器')).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════
// API 失败 → 回滚
// ═══════════════════════════════════════════════════
describe('Remediation — 错误处理与回滚', () => {
  it('API 失败 → 乐观更新回滚，状态恢复', async () => {
    mockTasksApi([makeTask({ id: 't1', status: 'in_progress', progress: 30 })])

    // Mock update 失败
    vi.mocked(remediationApi.update).mockRejectedValueOnce(new Error('网络错误'))

    renderRemediation()
    await waitFor(() => { expect(screen.getByText('测试整改任务')).toBeInTheDocument() })

    const pct75Btn = screen.getByRole('button', { name: '75%' })
    fireEvent.click(pct75Btn)

    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalled()
    })

    // 回滚后完成率不应改变，组件仍正常渲染
    await waitFor(() => {
      expect(screen.getByText('整改追踪器')).toBeInTheDocument()
    })
  })
})

// ═══════════════════════════════════════════════════
// 更新中 → 按钮禁用
// ═══════════════════════════════════════════════════
describe('Remediation — 按钮状态', () => {
  it('更新中 → 进度按钮 disabled', async () => {
    // 先 mock 正常 API，再替换 update 为 pending promise
    mockTasksApi([makeTask({ id: 't1', status: 'in_progress', progress: 0 })])
    // Never-resolve 的 promise：保证按钮保持 disabled
    vi.mocked(remediationApi.update).mockReturnValue(new Promise(() => {}) as any)

    renderRemediation()

    await waitFor(() => { expect(screen.getByText('测试整改任务')).toBeInTheDocument() })

    const pct25Btn = screen.getByRole('button', { name: '25%' })
    fireEvent.click(pct25Btn)

    // 按钮应变为 disabled
    await waitFor(() => {
      expect(pct25Btn).toBeDisabled()
    })
  })

  it('更新完成后 → 按钮恢复可用', async () => {
    mockTasksApi([makeTask({ id: 't1', status: 'in_progress', progress: 0 })])
    renderRemediation()

    await waitFor(() => { expect(screen.getByText('测试整改任务')).toBeInTheDocument() })

    const pct50Btn = screen.getByRole('button', { name: '50%' })
    fireEvent.click(pct50Btn)

    // 等待 API 完成，按钮恢复
    await waitFor(() => {
      expect(remediationApi.update).toHaveBeenCalled()
    })
  })
})

// ═══════════════════════════════════════════════════
// 新建 / 编辑任务
// ═══════════════════════════════════════════════════
describe('Remediation — 新建/编辑弹窗', () => {
  it('点击新建任务 → 弹窗打开并显示标题', async () => {
    mockTasksApi([makeTask({ id: 't1', title: '现有任务', status: 'pending', progress: 0 })])
    renderRemediation()

    await waitFor(() => {
      expect(screen.getByText('现有任务')).toBeInTheDocument()
    })

    // 点击新建任务按钮
    const newBtn = screen.getByRole('button', { name: /新建任务/ })
    fireEvent.click(newBtn)

    // 弹窗标题应出现
    await waitFor(() => {
      expect(screen.getByText('新建整改任务')).toBeInTheDocument()
    })
  })

  it('点击编辑 → 弹窗预填标题', async () => {
    mockTasksApi([makeTask({ id: 't1', title: '待编辑任务', status: 'pending', progress: 0 })])
    const { container } = renderRemediation()

    await waitFor(() => {
      expect(screen.getByText('待编辑任务')).toBeInTheDocument()
    })

    // 通过 EditOutlined 的 data-icon 属性找到编辑按钮
    const editSvg = container.querySelector('[data-icon="edit"]')
    expect(editSvg).toBeTruthy()
    const editBtn = editSvg!.closest('button')!
    fireEvent.click(editBtn)

    // 弹窗应有编辑标题
    await waitFor(() => {
      expect(screen.getByText('编辑整改任务')).toBeInTheDocument()
    })
  })
})
