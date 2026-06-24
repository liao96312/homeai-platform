import React from 'react';

type ErrorBoundaryProps = {
  children: React.ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Frontend render error', error, errorInfo);
    try {
      if (navigator.sendBeacon) {
        const apiBase = import.meta.env.VITE_API_BASE || '';
        const url = apiBase
          ? `${apiBase.replace(/\/$/, '')}/api/artifacts`
          : `${window.location.protocol}//${window.location.hostname}:8000/api/artifacts`;
        const payload = JSON.stringify({
          artifact_type: 'frontend_error',
          title: `Render Error: ${error.message ? error.message.substring(0, 200) : 'Unknown'}`,
          content: JSON.stringify({ error: String(error), componentStack: errorInfo.componentStack }),
        });
        navigator.sendBeacon(url, payload);
      }
    } catch {
      // Error reporting must never break the user-facing fallback.
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="admin-shell">
          <div className="error-fallback">
            <h1>页面加载失败</h1>
            <p>前端组件渲染异常，请刷新页面重试。</p>
            <button className="btn btn-primary" type="button" onClick={() => window.location.reload()}>
              刷新页面
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
