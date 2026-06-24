import { request, streamRequest } from './http';
import type { ApiPayload, StreamDeltaHandler } from './types';

export const chatApi = {
  chat: (payload: ApiPayload) => request('/api/chat/completions', { method: 'POST', body: JSON.stringify(payload) }),
  streamChatCompletion: (payload: ApiPayload, onDelta?: StreamDeltaHandler) => streamRequest('/api/chat/completions', payload, onDelta),
  legacyChat: (payload: ApiPayload) => request('/api/chat', { method: 'POST', body: JSON.stringify(payload) })
};
