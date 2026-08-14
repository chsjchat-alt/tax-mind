/**
 * 企业领域 Store
 *
 * 管理企业列表、当前选中企业、合规调整风险信息及加载状态。
 * 页面/组件仅消费 selector，不直接持有请求逻辑。
 */
import { create } from 'zustand';
import type { Enterprise, EnterpriseSummary, ComplianceAdjustedRisk } from '@/types';
import { enterpriseApi } from '@/api';

export interface EnterpriseState {
  enterprises: EnterpriseSummary[];
  currentEnterprise: (Enterprise & { statistics?: Record<string, number> }) | null;
  compliance: ComplianceAdjustedRisk | null;
  /** 企业列表加载状态（Header 下拉框展示用） */
  listLoading: boolean;
  /** 企业详情加载状态（切换企业时保持选择器常驻） */
  detailLoading: boolean;
  /** 企业列表加载失败（Header 下拉框"点击重试"入口） */
  error: string | null;
  /** 企业详情加载失败（与列表错误分离，避免重试被误导到列表接口） */
  detailError: string | null;
  /** 最近一次选择但加载失败的企业 id（供"重试详情"使用） */
  pendingDetailId: string | null;
  fetchEnterprises: () => Promise<void>;
  selectEnterprise: (id: string) => Promise<void>;
  retryDetail: () => Promise<void>;
}

// 请求序号：last-request-wins 防竞态，旧请求晚返回时直接丢弃
let detailSeq = 0;

export const useEnterpriseStore = create<EnterpriseState>((set, get) => ({
  enterprises: [],
  currentEnterprise: null,
  compliance: null,
  listLoading: false,
  detailLoading: false,
  error: null,
  detailError: null,
  pendingDetailId: null,

  fetchEnterprises: async () => {
    // 幂等：in-flight 请求复用，避免 Header + Dashboard + StrictMode 重复请求
    if (get().listLoading) return;
    set({ listLoading: true, error: null });
    try {
      const res = await enterpriseApi.list({ limit: 50 });
      set({ enterprises: res.data.data.enterprises, listLoading: false });
    } catch {
      set({ listLoading: false, error: '企业列表加载失败，请检查网络连接' });
    }
  },

  selectEnterprise: async (id: string) => {
    const seq = ++detailSeq;
    set({ detailLoading: true, error: null, detailError: null, pendingDetailId: null });
    try {
      const res = await enterpriseApi.detail(id);
      // 旧请求丢弃：期间用户已切换到其他企业
      if (seq !== detailSeq) return;
      const data = res.data.data as Record<string, unknown>;
      set({
        currentEnterprise: data.enterprise as Enterprise & { statistics?: Record<string, number> },
        compliance: (data.compliance as ComplianceAdjustedRisk) ?? null,
        detailLoading: false,
      });
    } catch {
      if (seq !== detailSeq) return;
      set({ detailLoading: false, detailError: '企业详情加载失败', pendingDetailId: id });
    }
  },

  /** 重试最近一次失败的企业详情加载（而非重新拉取企业列表） */
  retryDetail: async () => {
    const { pendingDetailId } = get();
    if (pendingDetailId) await get().selectEnterprise(pendingDetailId);
  },
}));
