const configuredApiBase = import.meta.env.VITE_API_BASE;
const API_BASE =
  configuredApiBase === undefined || configuredApiBase === ''
    ? ''
    : configuredApiBase.replace(/\/$/, '');

let authExpiredDispatched = false;
const RETRY_STATUSES = new Set([502, 503, 504]);
const STREAM_IDLE_TIMEOUT_MS = 300_000;

type QueryValue = string | number | boolean | null | undefined;
type QueryParams = Record<string, QueryValue>;

export type RequestOptions = RequestInit & {
  retry?: boolean;
};

type ApiErrorPayload = {
  detail?: string | Array<{ msg?: string; message?: string } | string>;
  message?: string;
};

export class ApiRequestError extends Error {
  status?: number;

  constructor(message: string, status?: number, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

export const authStore = {
  setSession: (user: unknown) => {
    sessionStorage.setItem('pinai_user', JSON.stringify(user));
  },
  clear: () => {
    sessionStorage.removeItem('pinai_user');
  }
};

export function queryString(params: QueryParams = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

function errorMessageFromPayload(payload: ApiErrorPayload) {
  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) => {
        if (typeof item === 'string') return item;
        return item?.msg || item?.message || String(item);
      })
      .filter(Boolean)
      .slice(0, 3)
      .join('；');
  }
  if (payload?.detail) return String(payload.detail);
  if (payload?.message) return String(payload.message);
  return '';
}

async function responseErrorMessage(res: Response) {
  const text = await res.text();
  if (!text) return friendlyStatusMessage(res.status);
  try {
    return errorMessageFromPayload(JSON.parse(text) as ApiErrorPayload) || friendlyStatusMessage(res.status);
  } catch {
    return text || friendlyStatusMessage(res.status);
  }
}

function friendlyStatusMessage(status: number) {
  const messages: Record<number, string> = {
    400: '请求内容不完整或格式不正确，请检查后重试',
    401: '登录状态已失效，请重新登录',
    403: '当前账号没有权限执行该操作',
    404: '请求的数据不存在或已被删除',
    409: '当前数据状态不允许重复操作，请刷新后再试',
    413: '上传文件过大，请压缩文件或联系管理员调整上传限制',
    422: '输入内容不符合要求，请检查必填项和格式',
    429: '操作过于频繁，请稍后再试',
    500: '后端服务异常，请查看后端日志',
    502: '外部服务调用失败，可能是 DeepSeek、视频服务或发布服务不可用',
    503: '服务暂不可用，请确认后端、数据库或外部模型服务已启动',
    504: '请求超时，请稍后重试'
  };
  return messages[status] || `请求失败：${status}`;
}

function shouldRetryRequest(res: Response, method: string, retry?: boolean) {
  if (retry === false) return false;
  const safeMethod = method === 'GET' || method === 'HEAD';
  return (safeMethod || retry === true) && RETRY_STATUSES.has(res.status);
}

function retryDelay(attempt: number) {
  return 300 * 2 ** attempt;
}

async function fetchWithRetry(url: string, options: RequestInit, retry?: boolean) {
  const method = (options.method || 'GET').toUpperCase();
  const maxAttempts = method === 'GET' || method === 'HEAD' || retry === true ? 3 : 1;
  let lastError: unknown;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const res = await fetch(url, options);
      if (!shouldRetryRequest(res, method, retry) || attempt === maxAttempts - 1) {
        return res;
      }
    } catch (err) {
      lastError = err;
      if (attempt === maxAttempts - 1 || retry === false || !(method === 'GET' || method === 'HEAD' || retry === true)) {
        if (err instanceof TypeError) {
          throw new ApiRequestError('无法连接后端服务，请确认 FastAPI 已启动，或检查 VITE_API_BASE 配置', 0, { cause: err });
        }
        throw err;
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, retryDelay(attempt)));
  }

  throw lastError || new ApiRequestError('网络请求失败，请检查后端服务和网络连接', 0);
}

export async function request<T = any>(path: string, options: RequestOptions = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const { headers: optionHeaders = {}, retry, ...fetchOptions } = options;
  const res = await fetchWithRetry(`${API_BASE}${path}`, {
    ...fetchOptions,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...optionHeaders
    }
  }, retry);
  if (res.status === 401 && path !== '/api/auth/login') {
    authStore.clear();
    if (!authExpiredDispatched) {
      authExpiredDispatched = true;
      window.dispatchEvent(new Event('pinai-auth-expired'));
      window.setTimeout(() => {
        authExpiredDispatched = false;
      }, 1000);
    }
    throw new ApiRequestError('登录已过期，请重新登录', 401);
  }
  if (!res.ok) {
    const message = await responseErrorMessage(res);
    throw new ApiRequestError(message || friendlyStatusMessage(res.status), res.status);
  }
  return res.json() as Promise<T>;
}

export async function streamRequest(
  path: string,
  payload: Record<string, unknown>,
  onDelta?: (_delta: string, _fullText: string, _chunk: unknown) => void,
) {
  const controller = new AbortController();
  let timeoutId = window.setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
  const refreshTimeout = () => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
  };
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      credentials: 'include',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ...payload, stream: true })
    });
    if (res.status === 401) {
      authStore.clear();
      window.dispatchEvent(new Event('pinai-auth-expired'));
      throw new ApiRequestError('登录已过期，请重新登录', 401);
    }
    if (!res.ok) {
      const message = await responseErrorMessage(res);
      throw new ApiRequestError(message || friendlyStatusMessage(res.status), res.status);
    }
    if (!res.body) throw new ApiRequestError('当前浏览器不支持流式响应');

    reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let fullText = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      refreshTimeout();
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const line = frame.split('\n').find((item) => item.startsWith('data:'));
        if (!line) continue;
        const data = line.slice(5).trim();
        if (!data || data === '[DONE]') continue;
        const chunk = JSON.parse(data) as { choices?: Array<{ delta?: { content?: string } }> };
        const delta = chunk.choices?.[0]?.delta?.content || '';
        if (delta) {
          fullText += delta;
          onDelta?.(delta, fullText, chunk);
        }
      }
    }
    return fullText;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiRequestError('流式响应超时，请稍后重试', 504, { cause: err });
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
    reader?.releaseLock();
  }
}
