import React from 'react';
import PromoPreview from './PromoPreview';

export default function PromoCopyCard({
  canPromo,
  promo,
  setPromo,
  promoTemplates,
  promoTemplateId,
  applyPromoTemplate,
  promoSchedule,
  setPromoSchedule,
  runPromo,
  promoResult,
  copyPromo,
  publishPromo,
  busy
}) {
  return (
    <form className={'card tool-card ' + (canPromo ? '' : 'locked')} onSubmit={runPromo}>
      <div className="card-header">
        <span className="card-title">推广文案生成</span>
        <span className="tag tag-purple">DeepSeek + RAG</span>
      </div>
      <div className="tool-form-grid">
        <label className="wide">模板
          <select value={promoTemplateId} disabled={!canPromo} onChange={(e) => applyPromoTemplate(e.target.value)}>
            <option value="">不使用模板</option>
            {promoTemplates.map((item) => (
              <option key={item.id} value={item.id}>{item.name} / {item.platform}</option>
            ))}
          </select>
        </label>
        <label>平台<input value={promo.platform} disabled={!canPromo} onChange={(e) => setPromo({ ...promo, platform: e.target.value })} /></label>
        <label>主题<input value={promo.topic} disabled={!canPromo} onChange={(e) => setPromo({ ...promo, topic: e.target.value })} /></label>
        <label className="wide">目标人群<input value={promo.audience} disabled={!canPromo} onChange={(e) => setPromo({ ...promo, audience: e.target.value })} /></label>
        <label className="wide">卖点<input value={promo.selling_points} disabled={!canPromo} onChange={(e) => setPromo({ ...promo, selling_points: e.target.value })} /></label>
        <label className="wide">语气<input value={promo.tone} disabled={!canPromo} onChange={(e) => setPromo({ ...promo, tone: e.target.value })} /></label>
        <label className="wide">定时发布<input type="datetime-local" value={promoSchedule} disabled={!canPromo} onChange={(e) => setPromoSchedule(e.target.value)} /></label>
      </div>
      <button className="btn btn-primary" disabled={!canPromo || busy === 'promo'} type="submit">
        {busy === 'promo' ? '生成中...' : '生成文案'}
      </button>
      <PromoPreview promoResult={promoResult} copyPromo={copyPromo} publishPromo={publishPromo} busy={busy} />
    </form>
  );
}



