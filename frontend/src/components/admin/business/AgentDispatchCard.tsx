import React from 'react';

export default function AgentDispatchCard({ dispatchText, setDispatchText, dispatchResult, runDispatch, busy }) {
  const routeLabel = dispatchResult?.route || '未分流';
  const toolLabel = dispatchResult?.tool || '未调用工具';
  const reply = dispatchResult?.reply || dispatchResult?.result?.content || dispatchResult?.result?.message || '';
  const runStatus = dispatchResult?.run?.status || '';

  return (
    <div className="card tool-card">
      <div className="card-header">
        <span className="card-title">统一 Agent 分流</span>
        <span className="tag tag-blue">意图识别</span>
      </div>
      <textarea value={dispatchText} onChange={(e) => setDispatchText(e.target.value)} />
      <button className="btn btn-primary" disabled={busy === 'dispatch'} onClick={runDispatch}>
        {busy === 'dispatch' ? '分流中...' : '自动分流执行'}
      </button>
      {dispatchResult && (
        <div className="tool-result-panel">
          <div className="tool-result-row"><b>分流路线</b><span>{routeLabel}</span></div>
          <div className="tool-result-row"><b>调用工具</b><span>{toolLabel}</span></div>
          {runStatus && <div className="tool-result-row"><b>运行状态</b><span>{runStatus}</span></div>}
          {reply && <p className="tool-result-reply">{reply}</p>}
          <details>
            <summary>查看原始结果</summary>
            <pre className="tool-output">{JSON.stringify(dispatchResult, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}



