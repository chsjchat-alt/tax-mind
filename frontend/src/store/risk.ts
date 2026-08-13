/**
 * 风险扫描领域 Store
 *
 * 管理最新风险扫描结果、扫描状态与统一视图选择器。
 * 页面层通过 useRiskViewState 消费，无需区分 loading / scanning。
 */
import { create } from 'zustand';
import type { RiskScanResult } from '@/types';
import { riskScanApi } from '@/api';

type RiskAction = 'scanRisk' | 'fetchLatest';

interface RiskState {
  result: RiskScanResult | null;
  status: 'idle' | 'pending' | 'success' | 'error';
  pendingAction: RiskAction | null;
  error: string | null;
  _scanningId: string | null;  // 防重复请求
  scanRisk: (enterpriseId: string) => Promise<void>;
  fetchLatest: (enterpriseId: string) => Promise<void>;
}

export const useRiskStore = create<RiskState>((set, get) => ({
  result: null,
  status: 'idle',
  pendingAction: null,
  error: null,
  _scanningId: null,

  scanRisk: async (enterpriseId: string) => {
    // 防重复：同一 enterpriseId 正在扫描中则跳过
    if (get()._scanningId === enterpriseId) return;
    set({ status: 'pending', pendingAction: 'scanRisk', error: null, _scanningId: enterpriseId });
    try {
      const res = await riskScanApi.scan(enterpriseId);
      set({ result: res.data.data, status: 'success', pendingAction: null, _scanningId: null });
    } catch {
      set({ status: 'error', pendingAction: null, error: '风险扫描失败，请稍后重试', _scanningId: null });
    }
  },

  fetchLatest: async (enterpriseId: string) => {
    set({ status: 'pending', pendingAction: 'fetchLatest', error: null });
    try {
      const res = await riskScanApi.latest(enterpriseId);
      set({ result: res.data.data as unknown as RiskScanResult, status: 'success', pendingAction: null });
    } catch {
      set({ status: 'error', pendingAction: null, error: '风险数据加载失败' });
    }
  },
}));

// ── 统一视图选择器 ──
// 使用单个原始值选择器避免 Zustand + useSyncExternalStore 的对象引用问题
export const useRiskViewState = () => {
  const result = useRiskStore((s) => s.result);
  const isBusy = useRiskStore((s) => s.status === 'pending');
  const pendingAction = useRiskStore((s) => s.pendingAction);
  const scanRisk = useRiskStore((s) => s.scanRisk);
  const fetchLatest = useRiskStore((s) => s.fetchLatest);
  return {
    result,
    isBusy,
    busyText: pendingAction === 'scanRisk' ? '正在执行风险扫描...' : '正在加载风险数据...',
    scanRisk,
    fetchLatest,
  };
};
