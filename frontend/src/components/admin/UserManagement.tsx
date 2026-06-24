import React, { useCallback, useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { api } from '../../api/client';

export default function UserManagement({ roles, currentUser, reload, setToast }) {
  const [users, setUsers] = useState<any[]>([]);
  const defaultRoleKey = roles.find((role) => role.key !== 'admin')?.key || roles[0]?.key || 'sales';
  const [draft, setDraft] = useState({ username: '', fullName: '', password: '', roleKey: defaultRoleKey });
  const [passwordDrafts, setPasswordDrafts] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState('');

  const loadUsers = useCallback(async () => {
    setBusy('load');
    try {
      const res = await api.listUsers();
      setUsers(res.users || []);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy('');
    }
  }, [setToast]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  async function createUser(e) {
    e.preventDefault();
    setBusy('create');
    try {
      await api.createUser({ username: draft.username, full_name: draft.fullName, password: draft.password, role_key: draft.roleKey, is_active: true });
      setToast('用户已创建');
      setDraft({ username: '', fullName: '', password: '', roleKey: defaultRoleKey });
      await loadUsers();
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy('');
    }
  }

  async function updateUser(id, payload) {
    setBusy(`user-${id}`);
    try {
      await api.updateUser(id, payload);
      setToast('用户已更新');
      await loadUsers();
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy('');
    }
  }

  async function resetPassword(id) {
    const password = (passwordDrafts[id] || '').trim();
    if (password.length < 6) return setToast('新密码至少 6 位');
    await updateUser(id, { password });
    setPasswordDrafts((prev) => ({ ...prev, [id]: '' }));
  }

  async function deleteUser(user) {
    if (user.id === currentUser.id) return setToast('不能删除当前登录用户');
    if (!confirm(`确定删除用户“${user.fullName}（${user.username}）”？该操作不可撤销。`)) return;
    setBusy(`user-${user.id}`);
    try {
      await api.deleteUser(user.id);
      setToast('用户已删除');
      await loadUsers();
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy('');
    }
  }

  function roleOptions(user) {
    return !user || roles.some((role) => role.key === user.role.key) ? roles : [user.role, ...roles];
  }

  return (
    <div className="user-admin-grid">
      <form className="card user-create-card" onSubmit={createUser}>
        <div className="card-header"><span className="card-title"><Users size={18} /> 新建用户</span></div>
        <div className="user-form-grid">
          <label>用户名<input value={draft.username} onChange={(e) => setDraft({ ...draft, username: e.target.value })} placeholder="例如 sales02" /></label>
          <label>姓名<input value={draft.fullName} onChange={(e) => setDraft({ ...draft, fullName: e.target.value })} placeholder="例如 销售顾问小李" /></label>
          <label>初始密码<input type="password" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} placeholder="至少 6 位" /></label>
          <label>角色<select value={draft.roleKey} onChange={(e) => setDraft({ ...draft, roleKey: e.target.value })}>{roles.map((role) => <option value={role.key} key={role.key}>{role.name}</option>)}</select></label>
          <button className="btn btn-primary" type="submit" disabled={busy === 'create'}>{busy === 'create' ? '创建中...' : '创建用户'}</button>
        </div>
      </form>

      <div className="card user-list-card">
        <div className="card-header"><span className="card-title"><Users size={18} /> 用户列表</span><button className="btn btn-default" type="button" onClick={loadUsers} disabled={busy === 'load'}>刷新</button></div>
        <div className="user-table">
          {users.map((user) => (
            <div className="user-row" key={user.id}>
              <div className="user-cell main"><b>{user.fullName}</b><span>@{user.username}</span></div>
              <div className="user-cell"><select value={user.role.key} disabled={busy === `user-${user.id}` || user.id === currentUser.id} onChange={(e) => updateUser(user.id, { role_key: e.target.value })}>{roleOptions(user).map((role) => <option value={role.key} key={role.key}>{role.name}</option>)}</select></div>
              <div className="user-cell"><span className={'tag ' + (user.isActive ? 'tag-blue' : 'tag-red')}>{user.isActive ? '启用' : '停用'}</span></div>
              <div className="user-cell password"><input type="password" placeholder="新密码" value={passwordDrafts[user.id] || ''} onChange={(e) => setPasswordDrafts((prev) => ({ ...prev, [user.id]: e.target.value }))} /><button type="button" disabled={busy === `user-${user.id}`} onClick={() => resetPassword(user.id)}>重置</button></div>
              <div className="user-cell actions">
                <button type="button" disabled={busy === `user-${user.id}` || user.id === currentUser.id} onClick={() => updateUser(user.id, { is_active: !user.isActive })}>{user.isActive ? '停用' : '启用'}</button>
                <button type="button" className="danger" disabled={busy === `user-${user.id}` || user.id === currentUser.id} onClick={() => deleteUser(user)}>删除</button>
              </div>
            </div>
          ))}
          {users.length === 0 && <div className="artifact-empty">暂无用户</div>}
        </div>
      </div>
    </div>
  );
}



