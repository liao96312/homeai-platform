import { useState, type FormEvent } from 'react';
import { ChevronRight, LogIn, Sparkles } from 'lucide-react';
import { api, authStore } from '../api/client';
import type { CurrentUser } from '../App';

type LoginPageProps = {
  onLogin: (_user: CurrentUser) => void;
};

type DemoUser = [username: string, password: string, label: string];

const demoUsers: DemoUser[] = [
  ['admin', import.meta.env.VITE_DEMO_ADMIN_PASSWORD, '超级管理员'],
  ['sales', import.meta.env.VITE_DEMO_SALES_PASSWORD, '销售顾问'],
  ['designer', import.meta.env.VITE_DEMO_DESIGNER_PASSWORD, '设计师'],
  ['promo', import.meta.env.VITE_DEMO_PROMO_PASSWORD, '推广运营']
].filter(([, password]) => import.meta.env.VITE_SHOW_DEMO_USERS === 'true' && Boolean(password)) as DemoUser[];

function loginErrorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return '登录失败，请稍后再试';
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const cleanUsername = username.trim();
    if (!cleanUsername || !password) {
      setError('请输入账号和密码');
      return;
    }
    setLoading(true);
    try {
      const res = await api.login({ username: cleanUsername, password });
      authStore.setSession(res.user);
      onLogin(res.user);
    } catch (err) {
      setError(loginErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="login-brand">
          <span><Sparkles size={24} strokeWidth={2.5} /></span>
          <div>
            <h1>家装 AI 转型平台</h1>
            <p>登录后按角色加载权限与数据</p>
          </div>
        </div>

        <form onSubmit={submit} className="login-form">
          <label>
            账号
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="请输入账号"
            />
          </label>
          <label>
            密码
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
              placeholder="请输入密码"
            />
          </label>
          {error && <div className="login-error">⚠ {error}</div>}
          <button className="login-submit" disabled={loading}>
            {loading ? '登录中...' : '登录'}
            {!loading && <LogIn size={16} />}
          </button>
        </form>

        {demoUsers.length > 0 && (
          <div className="quick-users">
            {demoUsers.map(([demoUser, demoPassword, label]) => (
              <button key={demoUser} type="button" onClick={() => { setUsername(demoUser); setPassword(demoPassword); }}>
                <b>{label}</b>
                <span>{demoUser} / {demoPassword}</span>
                <ChevronRight size={14} className="quick-arrow" />
              </button>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
