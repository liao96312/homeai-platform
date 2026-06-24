import { useEffect, useState } from 'react';
import ErrorBoundary from './components/ErrorBoundary';
import AdminApp from './pages/AdminApp';
import LoginPage from './pages/LoginPage';
import { api, authStore } from './api/client';

export interface CurrentUser {
  id?: number;
  username: string;
  fullName?: string;
  role?: {
    key: string;
    name?: string;
    color?: string;
  };
}

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api.me()
      .then((nextUser: CurrentUser) => setUser(nextUser))
      .catch(() => {
        authStore.clear();
      })
      .finally(() => setChecking(false));

    const onExpired = () => {
      authStore.clear();
      setUser(null);
    };
    window.addEventListener('pinai-auth-expired', onExpired);
    return () => window.removeEventListener('pinai-auth-expired', onExpired);
  }, []);

  function handleLogin(nextUser: CurrentUser) {
    setUser(nextUser);
  }

  function handleLogout() {
    authStore.clear();
    api.logout?.().catch(() => {});
    setUser(null);
  }

  if (checking) {
    return (
      <div className="admin-shell">
        <div className="loading">正在验证登录状态...</div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      {!user ? <LoginPage onLogin={handleLogin} /> : <AdminApp onLogout={handleLogout} />}
    </ErrorBoundary>
  );
}

