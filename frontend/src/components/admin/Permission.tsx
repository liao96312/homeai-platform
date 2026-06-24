import React, { useState } from 'react';
import { Shield } from 'lucide-react';
import { api } from '../../api/client';
import { permissionLabel, PermTag } from './AdminShared';

export default function Permission({ data, perms, isAdmin, reload, setToast }) {
  const [editing, setEditing] = useState<any | null>(null);
  const [draft, setDraft] = useState({ view: false, edit: false, manage: false });
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const permissionRoles = data.permissionRoles || data.roles.filter((role) => role.key !== 'admin');
  const editKb = editing ? data.knowledgeBases.find((kb) => kb.key === editing.kbKey) : null;
  const editRole = editing ? permissionRoles.find((role) => role.key === editing.roleKey) : null;

  function openModal(kbKey, roleKey) {
    if (!isAdmin || roleKey === 'admin') return;
    const p = perms[kbKey]?.[roleKey] || {};
    setDraft({ view: !!p.view, edit: !!p.edit, manage: !!p.manage });
    setEditing({ kbKey, roleKey });
  }

  function toggle(key) {
    setDraft((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      if (key === 'manage' && next.manage) next.edit = next.view = true;
      if (key === 'edit' && next.edit) next.view = true;
      if (key === 'view' && !next.view) next.edit = next.manage = false;
      if (key === 'edit' && !next.edit) next.manage = false;
      return next;
    });
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    try {
      await api.updatePermission(editing.kbKey, editing.roleKey, draft);
      setToast('权限已更新');
      setEditing(null);
      setConfirming(false);
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="role-grid">
        {permissionRoles.map((role) => (
          <div className="role-card" key={role.key}>
            <div className="role-card-header">
              <div className="role-card-icon" style={{ background: `${role.color}22` }}><Shield size={20} /></div>
              <div><div className="role-card-name">{role.name}</div><div className="role-card-count">{role.user_count} 名成员</div></div>
            </div>
            <div className="role-card-perms">
              {data.knowledgeBases.map((kb) => <button disabled={!isAdmin || role.key === 'admin'} onClick={() => openModal(kb.key, role.key)} className={'role-perm-tag tag ' + (perms[kb.key]?.[role.key]?.view ? 'tag-blue' : 'tag-red')} key={kb.key}>{kb.icon} {permissionLabel(perms[kb.key]?.[role.key])}</button>)}
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">权限矩阵</span><span className="config-desc">按五大知识库分级；超级管理员固定拥有全部权限</span></div>
        <div className="card-body">
          <table className="data-table">
            <thead><tr><th>知识库</th>{permissionRoles.map((role) => <th key={role.key}>{role.name}</th>)}</tr></thead>
            <tbody>
              {data.knowledgeBases.map((kb) => <tr key={kb.key}><td>{kb.icon} {kb.name}</td>{permissionRoles.map((role) => <td key={role.key}><button disabled={!isAdmin || role.key === 'admin'} className="perm-cell" onClick={() => openModal(kb.key, role.key)}><PermTag p={perms[kb.key]?.[role.key]} /></button></td>)}</tr>)}
            </tbody>
          </table>
        </div>
      </div>

      {editing && editKb && editRole && (
        <div className="perm-modal-overlay" onClick={(e) => e.target === e.currentTarget && setEditing(null)}>
          <div className="perm-modal">
            <div className="perm-modal-header"><span className="perm-modal-title">修改权限</span><button className="perm-modal-close" onClick={() => setEditing(null)}>×</button></div>
            <div className="perm-modal-body">
              <div className="perm-modal-meta">{editKb.icon} <b>{editKb.name}</b><span>·</span><span style={{ color: editRole.color }}>● {editRole.name}</span></div>
              {[
                ['view', '查看权限', '允许查看该知识库的内容和检索结果'],
                ['edit', '编辑权限', '允许上传文档、管理该知识库的内容'],
                ['manage', '管理权限', '允许修改其他角色对该知识库的权限']
              ].map(([key, label, desc]) => (
                <div className="perm-toggle-row" key={key}>
                  <div className="perm-toggle-label"><span className="perm-toggle-name">{label}</span><span className="perm-toggle-desc">{desc}</span></div>
                  <button className={'toggle ' + (draft[key] ? 'on' : '')} onClick={() => toggle(key)} aria-label={label} />
                </div>
              ))}
            </div>
            <div className="perm-modal-footer"><button className="btn btn-default" onClick={() => setEditing(null)}>取消</button><button className="btn btn-primary" onClick={() => setConfirming(true)}>保存</button></div>
          </div>
        </div>
      )}

      {confirming && editing && editKb && editRole && (
        <div className="confirm-overlay" onClick={(e) => e.target === e.currentTarget && setConfirming(false)}>
          <div className="confirm-dialog">
            <div className="confirm-dialog-body">
              <div className="confirm-dialog-icon">!</div>
              <div className="confirm-dialog-msg">确认修改“{editRole.name}”对“{editKb.name}”的权限？</div>
              <div className="confirm-dialog-detail">查看：{draft.view ? '允许' : '禁止'} | 编辑：{draft.edit ? '允许' : '禁止'} | 管理：{draft.manage ? '允许' : '禁止'}</div>
            </div>
            <div className="confirm-dialog-footer"><button className="btn btn-default" onClick={() => setConfirming(false)} disabled={saving}>取消</button><button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? '保存中...' : '确认修改'}</button></div>
          </div>
        </div>
      )}
    </>
  );
}
