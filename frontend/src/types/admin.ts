import type { Dispatch, FormEvent, SetStateAction } from 'react';
import type { ApiId, ApiUser } from '../api/types';

export type UnknownRecord = Record<string, unknown>;
export type LooseRecord = Record<string, any>;
export type ToastSetter = (_message: string) => void;
export type MaybePromise<T = void> = T | Promise<T>;

export type Role = {
  key: string;
  name?: string;
  color?: string;
};

export type Permission = {
  view?: boolean;
  edit?: boolean;
  manage?: boolean;
};

export type PermissionMap = Record<string, Record<string, Permission>>;

export type KnowledgeBase = {
  key: string;
  name: string;
  description?: string;
  icon?: string;
  theme?: string;
  docs?: number;
  chunks?: number;
  hit_rate?: number | string;
  isSystem?: boolean;
};

export type AdminData = {
  currentUser?: ApiUser;
  metrics: LooseRecord[];
  weeklyUsage: LooseRecord[];
  logs: LooseRecord[];
  agents: LooseRecord[];
  knowledgeBases: KnowledgeBase[];
  permissions: LooseRecord[];
  permissionRoles: Role[];
  roles: Role[];
  configs: LooseRecord[];
  assignableRoles: Role[];
  allRoles: Role[];
  businessInsights?: LooseRecord;
};

export type AgentRun = LooseRecord & {
  id: ApiId;
  runKey?: string;
  status?: string;
  channel?: string;
  intent?: string;
  route?: string;
  toolName?: string;
  input?: string;
  output?: string;
  error?: string;
  steps?: LooseRecord[];
  toolCalls?: LooseRecord[];
};

export type Artifact = LooseRecord & {
  id: ApiId;
  title?: string;
  artifactType?: string;
  status?: string;
};

export type AdminComponentProps = {
  setToast?: ToastSetter;
  reload?: () => MaybePromise;
  isAdmin?: boolean;
};

export type Setter<T> = Dispatch<SetStateAction<T>>;
export type SubmitEvent = FormEvent<HTMLFormElement>;

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error || '请求失败');
}
