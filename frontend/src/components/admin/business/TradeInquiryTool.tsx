import React, { useState } from 'react';
import { api } from '../../../api/client';

export default function TradeInquiryTool({ setToast }) {
  const [content, setContent] = useState('Dear, we are a distributor in Germany. Please quote 500 pcs kitchen cabinet, FOB Shanghai, T/T. Need CE and RoHS certificates.');
  const [source, setSource] = useState('email');
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!content.trim()) {
      setToast?.('请输入外贸询盘内容');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzeTradeInquiry({ content, source });
      setResult(res);
      setToast?.(`询盘分析完成：${res.intentScore} 分 / ${res.riskLevel}`);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setLoading(false);
    }
  }

  const extracted = result?.extracted || {};

  return (
    <form className="lead-tool card" onSubmit={submit}>
      <div className="card-header">
        <span className="card-title">外贸询盘分析</span>
        <span className="tag tag-blue">二期 MVP</span>
      </div>
      <div className="lead-tool-grid">
        <label className="lead-text">
          海外客户询盘
          <textarea value={content} onChange={(e) => setContent(e.target.value)} />
        </label>
        <div className="lead-fields">
          <label>来源<input value={source} onChange={(e) => setSource(e.target.value)} /></label>
          <label>买家类型<input value={result?.buyerType || ''} readOnly /></label>
          <label>意向分<input value={result?.intentScore ?? ''} readOnly /></label>
          <label>风险等级<input value={result?.riskLevel || ''} readOnly /></label>
          <label>国家<input value={extracted.country || ''} readOnly /></label>
          <label>贸易条款<input value={extracted.tradeTerm || ''} readOnly /></label>
        </div>
      </div>
      <div className="lead-actions">
        <button className="btn btn-primary" disabled={loading} type="submit">
          {loading ? '分析中...' : '分析外贸询盘'}
        </button>
        {result && <span className="lead-summary">阶段 {result.stage} · 缺失 {result.missingFields?.length || 0} 项 · 风险 {result.riskPoints?.length || 0} 项</span>}
      </div>
      {result && (
        <div className="lead-result">
          <div>
            <b>下一步动作</b>
            {(result.nextActions || []).map((item) => <span key={item}>{item}</span>)}
          </div>
          <div>
            <b>英文回复草稿</b>
            <span>{result.replyDraft}</span>
          </div>
        </div>
      )}
    </form>
  );
}
