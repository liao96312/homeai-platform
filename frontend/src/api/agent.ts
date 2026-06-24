import { request } from './http';
import type { ApiPayload } from './types';

export const agentApi = {
  dispatchAgent: (payload: ApiPayload) => request('/api/agent/dispatch', { method: 'POST', body: JSON.stringify(payload) }),
  runAgent: (payload: ApiPayload) => request('/api/agent/run', { method: 'POST', body: JSON.stringify(payload) }),
  listAgentTools: () => request('/api/agent/tools')
};
