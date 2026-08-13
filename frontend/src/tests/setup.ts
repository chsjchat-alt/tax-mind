/**
 * Vitest 测试环境全局配置
 *
 * - 引入 @testing-library/jest-dom 扩展断言（toBeInTheDocument 等）
 * - Mock window.matchMedia（Ant Design 响应式组件依赖）
 * - Mock IntersectionObserver（Recharts / 懒加载组件依赖）
 * - Mock ResizeObserver（Recharts 图表自适应依赖）
 * - 抑制 console.warn/error 中的特定噪音（可选）
 */
import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// ── Mock matchMedia ──
// 注意：必须使用普通函数而非 vi.fn()。测试文件的 afterEach 常调用
// vi.restoreAllMocks()，会清空 vi.fn() 的实现，导致 antd 响应式组件
// window.matchMedia() 返回 undefined 而崩溃（Cannot destructure 'matches'）。
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// ── Mock IntersectionObserver ──
class MockIntersectionObserver {
  readonly root: Element | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = []
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
  takeRecords = vi.fn(() => [])
}

Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: MockIntersectionObserver,
})

// ── Mock ResizeObserver ──
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: MockResizeObserver,
})

// ── Mock SVGElement.getBBox（Recharts 依赖） ──
;(SVGElement.prototype as unknown as Record<string, unknown>).getBBox = vi.fn(() => ({
  x: 0,
  y: 0,
  width: 200,
  height: 200,
}))

// ── Mock scrollTo ──
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
