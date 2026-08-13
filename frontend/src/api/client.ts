// ═══════════════════════════════════════
// Axios 实例 + 拦截器
// ═══════════════════════════════════════
import axios from 'axios';
import type { ApiResponse } from '@/types';
import type { InternalAxiosRequestConfig } from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

const TOKEN_KEY = 'taxmind_token';
const REFRESH_TOKEN_KEY = 'taxmind_refresh_token';
const USERNAME_KEY = 'taxmind_username';

/** 扩展请求配置：标记已重试，防止 401 刷新后无限循环 */
type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

// 刷新令牌的共享 Promise：并发 401 只触发一次刷新
let _refreshPromise: Promise<string> | null = null;

/** 用 refresh_token 换取新 access_token（裸 axios 调用，避免拦截器递归） */
async function refreshAccessToken(): Promise<string> {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) throw new Error('缺少 refresh_token');
    const { data } = await axios.post<ApiResponse<{ access_token: string; refresh_token: string }>>(
      '/api/v1/auth/refresh',
      { refresh_token: refreshToken },
    );
    if (data.code !== 200 || !data.data?.access_token) {
      throw new Error(data.message || '刷新令牌失败');
    }
    localStorage.setItem(TOKEN_KEY, data.data.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, data.data.refresh_token);
    return data.data.access_token;
  })().finally(() => {
    _refreshPromise = null;
  });
  return _refreshPromise;
}

/** 清除本地凭证并跳转登录页 */
function forceLogout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  if (window.location.pathname !== '/login') {
    window.location.href = '/login';
  }
}

// 请求拦截器 - 认证 Token + 日志
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    if (import.meta.env.DEV) {
      console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器 - 统一错误处理 + 401 无感续期
apiClient.interceptors.response.use(
  (response) => {
    // 二进制响应（blob）跳过 code 校验
    if (response.config.responseType === 'blob') {
      return response;
    }
    const data = response.data as ApiResponse<unknown>;
    if (data.code !== 200) {
      console.warn(`[API] Error ${data.code}: ${data.message}`);
      return Promise.reject(new Error(data.message));
    }
    return response;
  },
  async (error) => {
    const { config, response } = error;

    // 401 → 尝试刷新一次后重放原请求；刷新失败才登出
    if (response?.status === 401
      && config
      && !(config as RetriableConfig)._retried
      && !String(config.url).includes('/auth/login')
      && !String(config.url).includes('/auth/refresh')) {
      try {
        const newToken = await refreshAccessToken();
        const retryConfig = config as RetriableConfig;
        retryConfig._retried = true;
        retryConfig.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(retryConfig);
      } catch {
        forceLogout();
        return Promise.reject(error);
      }
    }

    if (response) {
      const { status, data } = response;
      console.error(`[API] HTTP ${status}:`, data);
      // 登录接口本身的 401（密码错误）不触发登出跳转
      if (status === 401 && !String(config?.url).includes('/auth/login')) {
        forceLogout();
      }
    } else if (error.request) {
      console.error('[API] 网络错误：无法连接服务器');
    }
    return Promise.reject(error);
  },
);

export default apiClient;
