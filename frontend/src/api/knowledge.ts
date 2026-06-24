import { queryString, request } from './http';
import type { ApiId, ApiParams, ApiPayload } from './types';

type UploadOptions = {
  chunkSize?: number;
  chunkOverlap?: number;
};

export const knowledgeApi = {
  uploadKnowledgeDocument: (kbKey: string, file: File, options: UploadOptions = {}) => {
    const form = new FormData();
    form.append('file', file);
    form.append('chunk_size', String(options.chunkSize || 800));
    form.append('chunk_overlap', String(options.chunkOverlap || 120));
    return request(`/api/knowledge/${kbKey}/documents`, {
      method: 'POST',
      body: form,
      headers: {}
    });
  },
  searchKnowledge: (kbKey: string, payload: ApiPayload) => request(`/api/knowledge/${kbKey}/search`, { method: 'POST', body: JSON.stringify(payload) }),
  listDocuments: (kbKey: string, params: ApiParams = {}) => request(`/api/knowledge/${kbKey}/documents${queryString(params)}`),
  deleteKnowledgeDocument: (kbKey: string, docId: ApiId) => request(`/api/knowledge/${kbKey}/documents/${docId}`, { method: 'DELETE' }),
  retryKnowledgeDocument: (kbKey: string, docId: ApiId) => request(`/api/knowledge/${kbKey}/documents/${docId}/retry`, { method: 'POST' }),
  listRagLogs: (conversationKey = '', params: ApiParams = {}) => request(`/api/rag/query-logs${queryString({ ...params, conversation_key: conversationKey })}`)
};
