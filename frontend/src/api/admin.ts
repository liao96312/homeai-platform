import { request } from './http';
import type { ApiId, ApiPayload } from './types';

export const adminApi = {
  getAdminData: () => request('/api/admin/bootstrap'),
  listUsers: () => request('/api/admin/users'),
  createUser: (payload: ApiPayload) => request('/api/admin/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: ApiId, payload: ApiPayload) => request(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id: ApiId) => request(`/api/admin/users/${id}`, { method: 'DELETE' }),
  createKnowledgeBase: (payload: ApiPayload) => request('/api/admin/knowledge-bases', { method: 'POST', body: JSON.stringify(payload) }),
  deleteKnowledgeBase: (kbKey: string) => request(`/api/admin/knowledge-bases/${kbKey}`, { method: 'DELETE' }),
  updateAgent: (agentKey: string, payload: ApiPayload) => request(`/api/admin/agents/${agentKey}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  updateConfig: (configKey: string, payload: ApiPayload) => request(`/api/admin/configs/${configKey}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  updatePermission: (kbKey: string, roleKey: string, payload: ApiPayload) => request(`/api/admin/permissions/${kbKey}/${roleKey}`, { method: 'PATCH', body: JSON.stringify(payload) })
};
