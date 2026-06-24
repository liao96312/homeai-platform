import { adminApi } from './admin';
import { agentApi } from './agent';
import { artifactApi } from './artifacts';
import { authApi } from './auth';
import { businessApi } from './business';
import { chatApi } from './chat';
import { authStore } from './http';
import { knowledgeApi } from './knowledge';

export { authStore };

export const api = {
  ...authApi,
  ...adminApi,
  ...knowledgeApi,
  ...businessApi,
  ...agentApi,
  ...artifactApi,
  ...chatApi
};
