/**
 * 心理画像领域 Store
 *
 * 管理心理画像结果、加载/生成状态及对应请求动作。
 */
import { create } from 'zustand';
import type { ProfileResult } from '@/types';
import { profileApi } from '@/api';

interface ProfileState {
  result: ProfileResult | null;
  loading: boolean;
  generating: boolean;
  error: string | null;
  generateProfile: (enterpriseId: string) => Promise<void>;
  fetchLatest: (enterpriseId: string) => Promise<void>;
}

export const useProfileStore = create<ProfileState>((set) => ({
  result: null,
  loading: false,
  generating: false,
  error: null,

  generateProfile: async (enterpriseId: string) => {
    set({ generating: true, error: null });
    try {
      const res = await profileApi.generate(enterpriseId);
      set({ result: res.data.data, generating: false });
    } catch {
      set({ generating: false, error: '心理画像生成失败，请稍后重试' });
    }
  },

  fetchLatest: async (enterpriseId: string) => {
    set({ loading: true, error: null });
    try {
      const res = await profileApi.latest(enterpriseId);
      set({ result: res.data.data as unknown as ProfileResult, loading: false });
    } catch {
      set({ loading: false, error: '画像数据加载失败' });
    }
  },
}));
