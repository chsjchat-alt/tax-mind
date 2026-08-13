import { create } from 'zustand';
import apiClient from '@/api/client';

interface AuthState {
  token: string | null;
  username: string | null;
  loading: boolean;
  error: string | null;

  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const TOKEN_KEY = 'taxmind_token';
const REFRESH_TOKEN_KEY = 'taxmind_refresh_token';
const USERNAME_KEY = 'taxmind_username';

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem(TOKEN_KEY),
  username: localStorage.getItem(USERNAME_KEY),
  loading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.post('/auth/login', { username, password });
      const data = res.data.data;
      const token = data.access_token;
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
      localStorage.setItem(USERNAME_KEY, username);
      set({ token, username, loading: false, error: null });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败，请检查用户名和密码';
      set({ loading: false, error: msg });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    set({ token: null, username: null });
  },
}));
