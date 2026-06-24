import { request } from './http';
import type { ApiUser, LoginPayload, LoginResponse } from './types';

export const authApi = {
  login: (payload: LoginPayload) => request<LoginResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) }),
  me: () => request<ApiUser>('/api/auth/me')
};
