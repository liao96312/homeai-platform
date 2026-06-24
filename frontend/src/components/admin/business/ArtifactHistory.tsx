import React from 'react';
import { artifactStatusLabel, artifactTypeLabel } from './labels';

const FILTERS = [
  ['', '全部'],
  ['lead_score', '销售'],
  ['design_card', '设计'],
  ['promo_copy', '推广'],
  ['video_generation', '视频']
];

export default function ArtifactHistory({
  artifacts,
  artifactFilter,
  setArtifactFilter,
  loadArtifacts,
  designAssignees,
  assignmentDrafts,
  updateAssignmentDraft,
  assignDesignCard,
  updateArtifactStatus,
  removeArtifact,
  busy
}) {
  return (
    <div className="card tool-card tool-history">
      <div className="card-header">
        <span className="card-title">最近业务产物</span>
        <button className="btn btn-default" type="button" onClick={() => loadArtifacts(artifactFilter)}>刷新</button>
      </div>
      <div className="artifact-filters">
        {FILTERS.map(([value, label]) => (
          <button
            key={value || 'all'}
            className={'artifact-filter ' + (artifactFilter === value ? 'active' : '')}
            type="button"
            onClick={() => setArtifactFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="artifact-list">
        {artifacts.length === 0 && <div className="artifact-empty">暂无记录</div>}
        {artifacts.map((item) => (
          <div className="artifact-item" key={item.id}>
            <div>
              <b>{artifactTypeLabel(item.type)}</b>
              <span>{item.title}</span>
              <em>{artifactStatusLabel(item.status)}</em>
            </div>
            <small>{item.createdAt} · {item.owner || '系统'}</small>
            {item.type === 'design_card' && (
              <div className="artifact-assignment">
                <span>{item.assignment?.assignedDesignerName ? '已分配：' + item.assignment.assignedDesignerName : '未分配设计师'}</span>
                <select
                  value={assignmentDrafts[item.id]?.designerId || item.assignment?.assignedDesignerId || ''}
                  onChange={(e) => updateAssignmentDraft(item.id, { designerId: e.target.value })}
                >
                  <option value="">选择设计师</option>
                  {designAssignees.map((assignee) => (
                    <option key={assignee.id} value={assignee.id}>{assignee.fullName} / {assignee.role}</option>
                  ))}
                </select>
                <input
                  value={assignmentDrafts[item.id]?.notes || ''}
                  onChange={(e) => updateAssignmentDraft(item.id, { notes: e.target.value })}
                  placeholder="分配备注"
                />
                <button type="button" disabled={busy === 'assign-' + item.id} onClick={() => assignDesignCard(item.id, item.assignment?.assignedDesignerId)}>
                  {busy === 'assign-' + item.id ? '分配中...' : '分配'}
                </button>
              </div>
            )}
            <div className="artifact-actions">
              {item.status === 'draft' && (
                <button type="button" disabled={busy === 'artifact-' + item.id} onClick={() => updateArtifactStatus(item.id, 'confirmed')}>确认</button>
              )}
              {item.status !== 'completed' && item.status !== 'archived' && (
                <button type="button" disabled={busy === 'artifact-' + item.id} onClick={() => updateArtifactStatus(item.id, 'completed')}>完成</button>
              )}
              {item.status !== 'archived' && (
                <button type="button" disabled={busy === 'artifact-' + item.id} onClick={() => updateArtifactStatus(item.id, 'archived')}>归档</button>
              )}
              <button type="button" disabled={busy === 'artifact-' + item.id} onClick={() => removeArtifact(item.id, item.title)}>删除</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}



