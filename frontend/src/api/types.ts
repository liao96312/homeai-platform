export type ApiPayload = Record<string, unknown>;
export type ApiParams = Record<string, string | number | boolean | null | undefined>;
export type ApiId = string | number;

export type LoginPayload = {
  username: string;
  password: string;
};

export type ApiUser = {
  id?: number;
  username: string;
  fullName?: string;
  role?: {
    key: string;
    name?: string;
    color?: string;
  };
};

export type LoginResponse = {
  accessToken: string;
  user: ApiUser;
};

export type StreamDeltaHandler = (_delta: string, _fullText: string, _chunk: unknown) => void;
