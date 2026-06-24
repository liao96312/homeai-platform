import { request } from './http';
import type { ApiId, ApiPayload } from './types';

export const businessApi = {
  listConversations: () => request('/api/conversations'),
  getConversation: (conversationKey: string) => request(`/api/conversations/${conversationKey}`),
  scoreLead: (payload: ApiPayload) => request('/api/sales/lead-score', { method: 'POST', body: JSON.stringify(payload) }),
  createDesignCard: (payload: ApiPayload) => request('/api/design/requirement-card', { method: 'POST', body: JSON.stringify(payload) }),
  listDesignAssignees: () => request('/api/design/assignees'),
  assignDesignCard: (id: ApiId, payload: ApiPayload) => request(`/api/design/requirement-cards/${id}/assignment`, { method: 'PATCH', body: JSON.stringify(payload) }),
  generatePromoCopy: (payload: ApiPayload) => request('/api/promo/copy', { method: 'POST', body: JSON.stringify(payload) }),
  generateVideo: (payload: ApiPayload) => request('/api/video/generate', { method: 'POST', body: JSON.stringify(payload) }),
  getVideoTask: (taskId: string) => request(`/api/video/tasks/${taskId}`),
  getVideoDelivery: (taskId: string) => request(`/api/video/tasks/${taskId}/delivery`),
  listPromoTemplates: () => request('/api/promo/templates'),
  createPromoTemplate: (payload: ApiPayload) => request('/api/promo/templates', { method: 'POST', body: JSON.stringify(payload) }),
  updatePromoTemplate: (id: ApiId, payload: ApiPayload) => request(`/api/promo/templates/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deletePromoTemplate: (id: ApiId) => request(`/api/promo/templates/${id}`, { method: 'DELETE' })
};
