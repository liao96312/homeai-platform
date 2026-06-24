import React from 'react';
import { publishStatusLabel } from './labels';

export default function PromoPreview({ promoResult, copyPromo, publishPromo, busy }) {
  if (!promoResult) return null;

  return (
    <div className="promo-preview">
      <div className="promo-preview-meta">
        <span>{promoResult.platform}</span>
        <span>{promoResult.topic}</span>
      </div>
      <h3>{promoResult.title || promoResult.topic}</h3>
      <div className="promo-preview-body">
        {(promoResult.body || promoResult.content || '').split('\n').map((line, index) => (
          <span key={index}>{line}<br /></span>
        ))}
      </div>
      {promoResult.tags?.length > 0 && (
        <div className="promo-preview-tags">
          {promoResult.tags.map((tag) => <span key={tag}>#{tag}</span>)}
        </div>
      )}
      {promoResult.publishJobs?.length > 0 && (
        <div className="publish-result compact">
          {promoResult.publishJobs.map((job) => (
            <div className={'publish-job publish-' + job.status} key={job.id}>
              <b>{job.platform}</b>
              <span>{publishStatusLabel(job.status)}</span>
              {job.error && <small>{job.error}</small>}
            </div>
          ))}
        </div>
      )}
      <div className="promo-preview-actions">
        <button className="btn btn-default" type="button" onClick={copyPromo}>复制</button>
        <button className="btn btn-primary" type="button" disabled={busy === 'promo-publish'} onClick={publishPromo}>
          {busy === 'promo-publish' ? '发布中...' : '创建发布任务'}
        </button>
      </div>
    </div>
  );
}



