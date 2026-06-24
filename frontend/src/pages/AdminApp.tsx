import { useCallback, useEffect, useMemo, useState, type ComponentType } from 'react';
import type { LucideProps } from 'lucide-react';
import {
  Bot,
  BookOpen,
  LayoutDashboard,
  LogOut,
  Network,
  Plus,
  RefreshCw,
  ScrollText,
  SearchCheck,
  Settings,
  Shield,
  Sparkles,
  Users,
  Wrench
} from 'lucide-react';
import { api } from '../api/client';
import Agents from '../components/admin/Agents';
import Architecture from '../components/admin/Architecture';
import BusinessTools from '../components/admin/BusinessTools';
import Config from '../components/admin/Config';
import Knowledge from '../components/admin/Knowledge';
import Logs from '../components/admin/Logs';
import Overview from '../components/admin/Overview';
import Permission from '../components/admin/Permission';
import RagObservability from '../components/admin/RagObservability';
import UserManagement from '../components/admin/UserManagement';
import type { AdminData, PermissionMap } from '../types/admin';

type PageKey = 'overview' | 'agents' | 'tools' | 'knowledge' | 'rag' | 'arch' | 'config' | 'logs' | 'users' | 'permission';
type PageConfig = [key: PageKey, label: string, Icon: ComponentType<LucideProps>];

const primaryPages: PageConfig[] = [
  ['overview', '首页总览', LayoutDashboard],
  ['tools', '业务工具', Wrench],
  ['knowledge', '知识库管理', BookOpen],
  ['users', '用户管理', Users],
  ['permission', '权限管理', Shield]
];

const adminPages: PageConfig[] = [
  ['agents', 'AI运行状态', Bot],
  ['rag', 'RAG观测', SearchCheck],
  ['config', '系统配置', Settings],
  ['logs', '操作日志', ScrollText],
  ['arch', '系统架构', Network]
];

const pages: PageConfig[] = [...primaryPages, ...adminPages];

const EMPTY_ADMIN_DATA: AdminData = {
  metrics: [],
  weeklyUsage: [],
  logs: [],
  agents: [],
  knowledgeBases: [],
  permissions: [],
  permissionRoles: [],
  roles: [],
  configs: [],
  assignableRoles: [],
  allRoles: []
};

export default function AdminApp({ onLogout }: { onLogout?: () => void }) {
  const [data, setData] = useState<AdminData | null>(null);
  const [page, setPage] = useState<PageKey>('overview');
  const [role, setRole] = useState('admin');
  const [toast, setToast] = useState('');
  const [newKbOpen, setNewKbOpen] = useState(false);

  const loadData = useCallback(async (keepRole = false) => {
    const res = await api.getAdminData() as Partial<AdminData>;
    setData({ ...EMPTY_ADMIN_DATA, ...res });
    if (!keepRole) setRole(res.currentUser?.role?.key || 'sales');
  }, []);

  useEffect(() => {
    loadData().catch((err) => {
      if (err.status === 401 || err.message.includes('登录已过期')) onLogout?.();
      setToast(err.message);
    });
  }, [loadData, onLogout]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(''), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const permByKb = useMemo(() => {
    const map: PermissionMap = {};
    for (const permission of data?.permissions || []) {
      const kbKey = String(permission.kbKey || '');
      const roleKey = String(permission.roleKey || '');
      if (!kbKey || !roleKey) continue;
      map[kbKey] ||= {};
      map[kbKey][roleKey] = permission;
    }
    return map;
  }, [data]);

  if (!data) {
    return <div className="admin-shell"><div className="loading">正在加载 API 数据...</div></div>;
  }

  const currentUser = data.currentUser || { username: 'anonymous', fullName: '未登录用户', role: { key: 'sales', name: '未授权' } };
  const fullName = currentUser.fullName || currentUser.username || '未登录用户';
  const roleName = currentUser.role?.name || currentUser.role?.key || '未授权';
  const roleKey = currentUser.role?.key || 'sales';
  const isAdmin = roleKey === 'admin';
  const visiblePrimaryPages = primaryPages;
  const visibleAdminPages = isAdmin ? adminPages : [];
  const visibleMobilePages = [...visiblePrimaryPages, ...visibleAdminPages];
  const currentPage = pages.find(([key]) => key === page);
  const title = currentPage?.[1] || '运营总览';

  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">
            <Sparkles size={18} strokeWidth={2.5} />
          </div>
          <div>
            <div className="logo-text">品爱AI平台</div>
            <div className="logo-sub">Admin Console</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-group-title">常用功能</div>
          {visiblePrimaryPages.map(([key, label, Icon]) => (
            <button
              key={key}
              className={'nav-item ' + (page === key ? 'active' : '')}
              onClick={() => setPage(key)}
            >
              <span className="nav-icon"><Icon size={18} /></span>
              {label}
              {key === 'logs' && <span className="nav-badge">{(data.logs || []).length}</span>}
            </button>
          ))}
          {visibleAdminPages.length > 0 && (
            <details className="nav-more" open={visibleAdminPages.some(([key]) => key === page)}>
              <summary>管理设置</summary>
              {visibleAdminPages.map(([key, label, Icon]) => (
                <button
                  key={key}
                  className={'nav-item ' + (page === key ? 'active' : '')}
                  onClick={() => setPage(key)}
                >
                  <span className="nav-icon"><Icon size={18} /></span>
                  {label}
                  {key === 'logs' && <span className="nav-badge">{(data.logs || []).length}</span>}
                </button>
              ))}
            </details>
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{fullName.slice(0, 1)}</div>
            <div>
              <div className="user-name">{fullName}</div>
              <div className="user-role">{roleName}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={onLogout} title="退出登录">
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      <main className="main-wrap">
        <header className="topbar">
          <h1 className="page-title">{title}</h1>
          <span className="tag tag-blue">{roleName}</span>
          <button className="btn btn-default" onClick={() => loadData(true).then(() => setToast('已刷新'))}>
            <RefreshCw size={14} /> 刷新
          </button>
          <button className="btn btn-primary" disabled={!isAdmin} onClick={() => { setPage('knowledge'); setNewKbOpen(true); }}>
            <Plus size={14} /> 新建知识库
          </button>
        </header>

        <nav className="mobile-nav" aria-label="移动端页面导航">
          {visibleMobilePages.map(([key, label, Icon]) => (
            <button
              key={key}
              className={'mobile-nav-item ' + (page === key ? 'active' : '')}
              onClick={() => setPage(key)}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <section className="content-area">
          {page === 'overview' && <Overview data={data} />}
          {page === 'agents' && <Agents agents={data.agents} isAdmin={isAdmin} reload={() => loadData(true)} setToast={setToast} />}
          {page === 'tools' && <BusinessTools currentRole={roleKey} setToast={setToast} />}
          {page === 'knowledge' && (
            <Knowledge
              data={data}
              role={role}
              setRole={setRole}
              perms={permByKb}
              setToast={setToast}
              reload={() => loadData(true)}
              newKbOpen={newKbOpen}
              setNewKbOpen={setNewKbOpen}
              isAdmin={isAdmin}
            />
          )}
          {page === 'rag' && <RagObservability setToast={setToast} />}
          {page === 'arch' && <Architecture />}
          {page === 'config' && <Config configs={data.configs || []} isAdmin={isAdmin} reload={() => loadData(true)} setToast={setToast} />}
          {page === 'logs' && <Logs logs={data.logs || []} />}
          {page === 'users' && (
            <UserManagement
              roles={data.assignableRoles || data.allRoles || data.roles || []}
              currentUser={currentUser}
              reload={() => loadData(true)}
              setToast={setToast}
            />
          )}
          {page === 'permission' && <Permission data={data} perms={permByKb} isAdmin={isAdmin} reload={() => loadData(true)} setToast={setToast} />}
        </section>
      </main>
      {toast && <div className="toast-item show"><span>●</span>{toast}</div>}
    </div>
  );
}
