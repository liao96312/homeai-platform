import { queryString, request } from './http';
import type { ApiId, ApiParams, ApiPayload } from './types';

export const artifactApi = {
  listArtifacts: (type = '', params: ApiParams = {}) => request(`/api/artifacts${queryString({ ...params, artifact_type: type })}`),
  createArtifact: (payload: ApiPayload) => request('/api/artifacts', { method: 'POST', body: JSON.stringify(payload) }),
  getArtifact: (id: ApiId) => request(`/api/artifacts/${id}`),
  updateArtifact: (id: ApiId, payload: ApiPayload) => request(`/api/artifacts/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteArtifact: (id: ApiId) => request(`/api/artifacts/${id}`, { method: 'DELETE' }),
  createPublishJobs: (payload: ApiPayload) => request('/api/publish/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  listPublishJobs: (params: ApiParams = {}) => request(`/api/publish/jobs${queryString(params)}`),
  retryPublishJob: (id: ApiId) => request(`/api/publish/jobs/${id}/retry`, { method: 'POST' })
};
