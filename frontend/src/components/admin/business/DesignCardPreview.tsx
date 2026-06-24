import React from 'react';
import { artifactStatusLabel } from './labels';

export default function DesignCardPreview({
  designCard,
  designAssignees,
  assignmentDrafts,
  updateAssignmentDraft,
  assignDesignCard,
  busy
}) {
  if (!designCard) return null;

  return (
    <div className="design-card-preview">
      <div className="design-card-head">
        <b>{designCard.customerName}</b>
        <span>{artifactStatusLabel(designCard.assignment?.status || 'draft')}</span>
      </div>
      <div className="design-card-grid">
        <span>面积：{designCard.area || '待确认'}</span>
        <span>户型：{designCard.houseType || '待确认'}</span>
        <span>风格：{designCard.style || '待确认'}</span>
        <span>预算：{designCard.budget || '待确认'}</span>
        <span>周期：{designCard.timeline || '待确认'}</span>
        <span>重点空间：{(designCard.spaces || []).join('、')}</span>
      </div>
      <div className="design-card-section">
        <b>设计待办</b>
        {(designCard.designerTodos || []).map((item) => <span key={item}>{item}</span>)}
      </div>
      <div className="design-card-section">
        <b>待补信息</b>
        {(designCard.missingFields?.length ? designCard.missingFields : ['已基本补齐']).map((item) => <span key={item}>{item}</span>)}
      </div>
      <div className="design-assign-row">
        <select
          value={assignmentDrafts[designCard.artifactId]?.designerId || designCard.assignment?.assignedDesignerId || ''}
          onChange={(e) => updateAssignmentDraft(designCard.artifactId, { designerId: e.target.value })}
        >
          <option value="">选择设计师</option>
          {designAssignees.map((item) => (
            <option key={item.id} value={item.id}>{item.fullName} / {item.role}</option>
          ))}
        </select>
        <input
          value={assignmentDrafts[designCard.artifactId]?.notes || ''}
          onChange={(e) => updateAssignmentDraft(designCard.artifactId, { notes: e.target.value })}
          placeholder="分配备注"
        />
        <button className="btn btn-primary" type="button" disabled={busy === 'assign-' + designCard.artifactId} onClick={() => assignDesignCard(designCard.artifactId, designCard.assignment?.assignedDesignerId)}>
          {busy === 'assign-' + designCard.artifactId ? '分配中...' : '分配'}
        </button>
      </div>
      {designCard.assignment?.assignedDesignerName && (
        <small className="design-assigned">已分配：{designCard.assignment.assignedDesignerName}</small>
      )}
    </div>
  );
}
