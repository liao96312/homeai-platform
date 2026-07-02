import React, { useState } from 'react';
import { api } from '../../../api/client';

export default function TradeQuoteTool({ setToast }) {
  const [form, setForm] = useState({
    product: 'Kitchen cabinet',
    quantity: '500 pcs',
    currency: 'USD',
    unit_price: '12.5',
    trade_term: 'FOB',
    destination: 'Hamburg, Germany',
    payment_terms: 'T/T 30% deposit, 70% before shipment',
    lead_time: '25-30 days after deposit',
    moq: '100 pcs',
    validity_days: '7',
    notes: 'Final price depends on confirmed material, hardware and packaging.'
  });
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    if (!form.product.trim()) {
      setToast?.('请输入产品/型号');
      return;
    }
    setLoading(true);
    try {
      const res = await api.draftTradeQuote({
        ...form,
        unit_price: form.unit_price ? Number(form.unit_price) : null,
        validity_days: form.validity_days ? Number(form.validity_days) : 7
      });
      setResult(res);
      setToast?.('外贸报价草稿已生成');
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="tool-card card" onSubmit={submit}>
      <div className="card-header">
        <span className="card-title">外贸报价草稿</span>
        <span className="tag tag-green">人工确认</span>
      </div>
      <div className="tool-form-grid">
        <label>产品/型号<input value={form.product} onChange={(e) => update('product', e.target.value)} /></label>
        <label>数量<input value={form.quantity} onChange={(e) => update('quantity', e.target.value)} /></label>
        <label>币种<input value={form.currency} onChange={(e) => update('currency', e.target.value)} /></label>
        <label>单价<input value={form.unit_price} onChange={(e) => update('unit_price', e.target.value)} inputMode="decimal" /></label>
        <label>贸易条款<input value={form.trade_term} onChange={(e) => update('trade_term', e.target.value)} /></label>
        <label>目的地<input value={form.destination} onChange={(e) => update('destination', e.target.value)} /></label>
        <label>交期<input value={form.lead_time} onChange={(e) => update('lead_time', e.target.value)} /></label>
        <label>MOQ<input value={form.moq} onChange={(e) => update('moq', e.target.value)} /></label>
        <label className="wide">付款方式<input value={form.payment_terms} onChange={(e) => update('payment_terms', e.target.value)} /></label>
        <label className="wide">备注<input value={form.notes} onChange={(e) => update('notes', e.target.value)} /></label>
      </div>
      <button className="btn btn-primary" disabled={loading} type="submit">{loading ? '生成中...' : '生成报价草稿'}</button>
      {result && (
        <div className="tool-result-panel">
          <div className="tool-result-row"><b>总金额</b><span>{result.totalAmount ? `${result.currency} ${result.totalAmount}` : '待确认'}</span></div>
          <div className="tool-result-row"><b>风险项</b><span>{result.riskPoints?.length || 0} 项</span></div>
          <pre className="tool-output">{result.emailDraft}</pre>
        </div>
      )}
    </form>
  );
}
