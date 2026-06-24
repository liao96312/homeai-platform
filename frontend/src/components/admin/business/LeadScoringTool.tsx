import React, { useState } from 'react';
import { api } from '../../../api/client';

export default function LeadScoringTool({ setToast }) {
  const [form, setForm] = useState({
    content: '客户想做120平新中式全屋定制，本月想量房，预算25万，比较过欧派，重点关心环保板材和收纳。',
    budget: '25',
    area: '120',
    style: '新中式',
    timeline: '本月量房',
    city: '本地',
    phone: ''
  });
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...form,
        budget: form.budget ? Number(form.budget) : null,
        area: form.area ? Number(form.area) : null
      };
      const res = await api.scoreLead(payload);
      setResult(res);
      setToast?.('客户初筛完成：' + res.score + ' 分 / ' + res.grade + ' 级');
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setLoading(false);
    }
  }

  const signals = Array.isArray(result?.signals) ? result.signals : [];
  const nextActions = Array.isArray(result?.nextActions) ? result.nextActions : [];

  return (
    <form className="lead-tool card" onSubmit={submit}>
      <div className="card-header">
        <span className="card-title">销售客户初筛</span>
        <span className="tag tag-orange">规则引擎</span>
      </div>
      <div className="lead-tool-grid">
        <label className="lead-text">
          客户描述
          <textarea value={form.content} onChange={(e) => update('content', e.target.value)} />
        </label>
        <div className="lead-fields">
          <label>预算(万)<input value={form.budget} onChange={(e) => update('budget', e.target.value)} inputMode="decimal" /></label>
          <label>面积(平)<input value={form.area} onChange={(e) => update('area', e.target.value)} inputMode="decimal" /></label>
          <label>风格<input value={form.style} onChange={(e) => update('style', e.target.value)} /></label>
          <label>时间<input value={form.timeline} onChange={(e) => update('timeline', e.target.value)} /></label>
          <label>城市<input value={form.city} onChange={(e) => update('city', e.target.value)} /></label>
          <label>电话<input value={form.phone} onChange={(e) => update('phone', e.target.value)} /></label>
        </div>
      </div>
      <div className="lead-actions">
        <button className="btn btn-primary" disabled={loading} type="submit">
          {loading ? '分析中...' : '生成意向评分'}
        </button>
        {result && <span className="lead-summary">评分 {result.score} · {result.grade}级 · {result.recommendation}</span>}
      </div>
      {result && (
        <div className="lead-result">
          <div>
            <b>识别信号</b>
            {signals.map((item) => <span key={item}>{item}</span>)}
          </div>
          <div>
            <b>下一步动作</b>
            {nextActions.map((item) => <span key={item}>{item}</span>)}
          </div>
        </div>
      )}
    </form>
  );
}
