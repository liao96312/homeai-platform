import React from 'react';
import DesignCardPreview from './DesignCardPreview';

export default function DesignRequirementCard({
  canDesign,
  designText,
  setDesignText,
  runDesign,
  designCard,
  designAssignees,
  assignmentDrafts,
  updateAssignmentDraft,
  assignDesignCard,
  busy
}) {
  return (
    <div className={'card tool-card ' + (canDesign ? '' : 'locked')}>
      <div className="card-header">
        <span className="card-title">设计需求卡</span>
        <span className="tag tag-orange">结构化解析</span>
      </div>
      <textarea value={designText} disabled={!canDesign} onChange={(e) => setDesignText(e.target.value)} />
      <button className="btn btn-primary" disabled={!canDesign || busy === 'design'} onClick={runDesign}>
        {busy === 'design' ? '解析中...' : '生成需求卡'}
      </button>
      <DesignCardPreview
        designCard={designCard}
        designAssignees={designAssignees}
        assignmentDrafts={assignmentDrafts}
        updateAssignmentDraft={updateAssignmentDraft}
        assignDesignCard={assignDesignCard}
        busy={busy}
      />
    </div>
  );
}



