import React, { useCallback, useEffect, useState } from 'react';
import { SearchCheck } from 'lucide-react';
import { api } from '../../api/client';
import { formatScore, relevanceLabel } from './AdminShared';

function gateSummary(gate?: any) {
  if (!gate) return '';
  const status = gate.allowed ? '进入知识库判断' : '未进入知识库';
  const confidence = Number.isFinite(Number(gate.confidence)) ? `${Math.round(Number(gate.confidence) * 100)}%` : '未知';
  const latency = Number.isFinite(Number(gate.latencyMs)) ? `${Number(gate.latencyMs).toFixed(0)}ms` : '未知耗时';
  const cached = gate.cached ? ' · 缓存' : '';
  return `${status} · ${gate.intent || 'unknown'} · 可信度 ${confidence} · ${latency}${cached}`;
}

export default function RagObservability({ setToast }) {
  const [logs, setLogs] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);

  const loadLogs = useCallback(async (nextFilter = filter) => {
    setBusy(true);
    try {
      const res = await api.listRagLogs(nextFilter);
      setLogs(res.logs || []);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy(false);
    }
  }, [filter, setToast]);

  useEffect(() => {
    loadLogs(filter);
  }, [filter, loadLogs]);

  const hitCount = logs.filter((item) => item.ragStatus?.code === 'hit').length;
  const maybeCount = logs.filter((item) => item.ragStatus?.code === 'maybe').length;
  const injectedCount = logs.filter((item) => item.injected).length;
  const filters = [['', '全部'], ['sales', '销售'], ['design', '设计'], ['promo', '推广'], ['product', '销售库'], ['promotion', '推广库'], ['management', '管理库'], ['public', '公共库']];

  return (
    <div className="rag-page">
      <div className="metric-grid compact">
        <div className="metric-card green"><div className="metric-value">{hitCount}</div><div className="metric-label">已命中知识库</div><div className="metric-trend">资料可用</div></div>
        <div className="metric-card orange"><div className="metric-value">{maybeCount}</div><div className="metric-label">建议人工确认</div><div className="metric-trend">资料可能相关</div></div>
        <div className="metric-card blue"><div className="metric-value">{injectedCount}</div><div className="metric-label">用于回答</div><div className="metric-trend">已带入知识资料</div></div>
      </div>
      <div className="card">
        <div className="card-header">
          <span className="card-title"><SearchCheck size={18} /> 知识库检索日志</span>
          <button className="btn btn-default" type="button" disabled={busy} onClick={() => loadLogs(filter)}>刷新</button>
        </div>
        <div className="artifact-filters">
          {filters.map(([key, label]) => <button className={'artifact-filter ' + (filter === key ? 'active' : '')} type="button" onClick={() => setFilter(key)} key={key || 'all'}>{label}</button>)}
        </div>
        <div className="rag-log-list">
          {logs.length === 0 && <div className="artifact-empty">暂无检索日志</div>}
          {logs.map((item) => {
            const sources = item.topSources || [];
            const gate = sources.find((source) => source.ragGate)?.ragGate;
            return (
              <div className="rag-log-item" key={item.id}>
                <div className="rag-log-main">
                  <div className="rag-log-title"><b>{item.conversationKey || '未指定'}</b><span>{item.ragStatus?.label || (item.injected ? '已注入' : '仅检索')}</span><em>{item.hitCount} hits</em></div>
                  <p>{item.query}</p><small>{item.createdAt} · {item.user || '系统'}</small>
                  {gate && <small className="rag-gate-line">问题判断：{gateSummary(gate)} · {gate.reason || '无原因'}</small>}
                </div>
                <div className="rag-source-list">
                  {sources.filter((source) => source.type !== 'status').slice(0, 3).map((source, idx) => (
                    <div className="rag-source" key={`${item.id}-${source.chunkId || idx}`}>
                      <b>{source.kbName || source.kbKey || '知识库'}</b><span>{source.filename || `chunk ${source.chunkId || idx + 1}`}</span><em>排序分 {formatScore(source.score)} · {relevanceLabel(source.relevance)}</em>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
