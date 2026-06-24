import React, { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { formatScore, ragGateLabel, reasonLabel, relevanceLabel, Stat, themeBg } from './AdminShared';

function documentStatusLabel(status) {
  return {
    queued: '排队中',
    indexing: '索引中',
    indexed: '已索引',
    partial: '部分完成',
    failed: '索引失败',
    uploaded: '已上传',
  }[status] || status || '未知';
}

function documentErrorLabel(error) {
  return {
    staged_file_missing: '原始上传文件不存在，请重新上传',
    staged_file_missing_on_startup: '服务重启时未找到原始上传文件',
    empty_text: '文件未解析出有效文本',
    empty_chunks: '文件未生成有效切片',
    knowledge_base_missing: '知识库不存在',
  }[error] || error || '';
}

export default function Knowledge({ data, role, setRole, perms, setToast, reload, newKbOpen, setNewKbOpen, isAdmin }) {
  const [query, setQuery] = useState('');
  const [resultsByKb, setResultsByKb] = useState<Record<string, any>>({});
  const [ragGateByKb, setRagGateByKb] = useState<Record<string, any>>({});
  const [ragStatusByKb, setRagStatusByKb] = useState<Record<string, any>>({});
  const [busyKb, setBusyKb] = useState('');
  const [newKb, setNewKb] = useState({ name: '', description: '', icon: '📚', theme: 'blue' });
  const [docsByKb, setDocsByKb] = useState<Record<string, any>>({});
  const [pollingKbKeys, setPollingKbKeys] = useState<Record<string, boolean>>({});
  const pollingRef = useRef<Record<string, boolean>>({});
  const loadDocsRef = useRef<((_kbKey: string, _options?: { silent?: boolean }) => Promise<void>) | undefined>(undefined);
  const visible = data.knowledgeBases.filter((kb) => perms[kb.key]?.[role]?.view).length;

  useEffect(() => {
    pollingRef.current = pollingKbKeys;
  }, [pollingKbKeys]);

  useEffect(() => {
    const keys = Object.keys(pollingKbKeys).filter((key) => pollingKbKeys[key]);
    if (!keys.length) return undefined;
    const timer = window.setInterval(() => {
      keys.forEach((key) => {
        if (pollingRef.current[key]) void loadDocsRef.current?.(key, { silent: true });
      });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [pollingKbKeys]);

  async function upload(kbKey, file, inputEl) {
    if (!file) return;
    setBusyKb(kbKey);
    try {
      const res = await api.uploadKnowledgeDocument(kbKey, file);
      setToast(res.async ? '文件已上传，正在后台解析和索引' : '上传完成，已切片并写入向量库');
      await Promise.all([reload?.(), loadDocs(kbKey)]);
      if (res.async) markKbPolling(kbKey, true);
    } catch (err) {
      setToast(err.message);
    } finally {
      if (inputEl) inputEl.value = '';
      setBusyKb('');
    }
  }

  async function search(kbKey) {
    if (!query.trim()) return setToast('请输入检索问题');
    setBusyKb(kbKey);
    try {
      const res = await api.searchKnowledge(kbKey, { query, top_k: 5 });
      setResultsByKb((prev) => ({ ...prev, [kbKey]: res.results || [] }));
      setRagGateByKb((prev) => ({ ...prev, [kbKey]: res.ragGate }));
      setRagStatusByKb((prev) => ({ ...prev, [kbKey]: res.ragStatus }));
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusyKb('');
    }
  }

  async function loadDocs(kbKey, options: { silent?: boolean } = {}) {
    if (!options.silent) setBusyKb(kbKey);
    try {
      const res = await api.listDocuments(kbKey);
      const documents = res.documents || [];
      setDocsByKb((prev) => ({ ...prev, [kbKey]: documents }));
      markKbPolling(kbKey, documents.some((doc) => ['queued', 'indexing'].includes(String(doc.status || ''))));
    } catch (err) {
      if (!options.silent) setToast(err.message);
    } finally {
      if (!options.silent) setBusyKb('');
    }
  }

  useEffect(() => {
    loadDocsRef.current = loadDocs;
  });

  function markKbPolling(kbKey: string, active: boolean) {
    setPollingKbKeys((prev) => {
      if (Boolean(prev[kbKey]) === active) return prev;
      const next = { ...prev };
      if (active) next[kbKey] = true;
      else delete next[kbKey];
      return next;
    });
  }

  async function deleteDoc(kbKey, docId, filename) {
    if (!confirm(`确定删除文档“${filename}”？`)) return;
    setBusyKb(kbKey);
    try {
      await api.deleteKnowledgeDocument(kbKey, docId);
      setToast('文档已删除，检索缓存已失效');
      await Promise.all([reload?.(), loadDocs(kbKey)]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusyKb('');
    }
  }

  async function retryDoc(kbKey, docId) {
    setBusyKb(kbKey);
    try {
      await api.retryKnowledgeDocument(kbKey, docId);
      setToast('文档已重新进入索引队列');
      await loadDocs(kbKey);
      markKbPolling(kbKey, true);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusyKb('');
    }
  }

  async function createKnowledgeBase(e) {
    e.preventDefault();
    if (!newKb.name.trim()) return setToast('请输入知识库名称');
    setBusyKb('create');
    try {
      await api.createKnowledgeBase(newKb);
      setToast('知识库已创建');
      setNewKb({ name: '', description: '', icon: '📚', theme: 'blue' });
      setNewKbOpen(false);
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusyKb('');
    }
  }

  async function deleteKb(kb) {
    if (!confirm(`确定删除知识库“${kb.name}”？该操作会删除文档和向量索引。`)) return;
    setBusyKb(kb.key);
    try {
      await api.deleteKnowledgeBase(kb.key);
      setToast('知识库已删除');
      await reload?.();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusyKb('');
    }
  }

  return (
    <div className="knowledge-page">
      <div className="role-switcher">
        <div><b>权限视角</b><span>当前角色可见 {visible} 个知识库</span></div>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {(data.permissionRoles || data.roles || []).map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}
        </select>
      </div>

      {newKbOpen && isAdmin && (
        <form className="card kb-create-card" onSubmit={createKnowledgeBase}>
          <div className="card-header"><span className="card-title">新建知识库</span><button className="btn btn-default" type="button" onClick={() => setNewKbOpen(false)}>关闭</button></div>
          <div className="form-grid">
            <label>名称<input value={newKb.name} onChange={(e) => setNewKb({ ...newKb, name: e.target.value })} placeholder="例如 安装工艺库" /></label>
            <label>图标<input value={newKb.icon} onChange={(e) => setNewKb({ ...newKb, icon: e.target.value })} /></label>
            <label>主题<select value={newKb.theme} onChange={(e) => setNewKb({ ...newKb, theme: e.target.value })}>{Object.keys(themeBg).map((key) => <option key={key}>{key}</option>)}</select></label>
            <label className="wide">描述<input value={newKb.description} onChange={(e) => setNewKb({ ...newKb, description: e.target.value })} placeholder="这个知识库覆盖什么内容" /></label>
            <button className="btn btn-primary" disabled={busyKb === 'create'}>创建</button>
          </div>
        </form>
      )}

      <div className="kb-searchbar">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入问题，选择下方知识库执行向量检索" />
      </div>

      <div className="kb-grid">
        {data.knowledgeBases.map((kb) => {
          const perm = perms[kb.key]?.[role] || {};
          const docs = docsByKb[kb.key] || [];
          const results = resultsByKb[kb.key] || [];
          const gate = ragGateByKb[kb.key];
          const ragStatus = ragStatusByKb[kb.key];
          return (
            <div className={'kb-card ' + (perm.view ? '' : 'locked')} data-kb={kb.key} key={kb.key}>
              <div className="kb-header">
                <div className="kb-icon" style={{ background: themeBg[kb.theme] }}>{kb.icon}</div>
                <div><div className="kb-name">{kb.name}</div><div className="kb-desc">{kb.description}</div></div>
              </div>
              <div className="kb-stats"><Stat v={kb.docs} l="文档" /><Stat v={kb.chunks} l="切片" /><Stat v={kb.hit_rate} l="命中" /></div>
              <div className="kb-perm-tags">
                {perm.view && <span className="tag tag-blue">查看</span>}
                {perm.edit && <span className="tag tag-orange">编辑</span>}
                {perm.manage && <span className="tag tag-purple">管理</span>}
                {!perm.view && <span className="tag tag-red">无权限</span>}
              </div>
              {perm.view && (
                <div className="kb-tools">
                  <label className={'btn btn-default ' + (perm.edit ? '' : 'disabled')}>上传<input type="file" accept=".txt,.md,.csv,.json,.html,.htm,.docx,.pdf,.xlsx,.xls" disabled={!perm.edit || busyKb === kb.key} onChange={(e) => upload(kb.key, e.target.files?.[0], e.target)} /></label>
                  <button className="btn btn-default" disabled={busyKb === kb.key} onClick={() => loadDocs(kb.key)}>{pollingKbKeys[kb.key] ? '刷新中' : '文档'}</button>
                  <button className="btn btn-primary" disabled={busyKb === kb.key} onClick={() => search(kb.key)}>{busyKb === kb.key ? '处理中...' : '检索'}</button>
                  {isAdmin && !kb.isSystem && <button className="btn btn-danger" disabled={busyKb === kb.key} onClick={() => deleteKb(kb)}>删除</button>}
                </div>
              )}
              {docs.length > 0 && <div className="kb-doc-list"><div className="kb-doc-title">已上传文档</div>{docs.map((doc) => {
                const error = documentErrorLabel(doc.metadata?.error || doc.metadata?.vector_index_error);
                const canRetry = perm.edit && ['failed', 'partial'].includes(String(doc.status || ''));
                return (
                  <div className="kb-doc-row" key={doc.id}>
                    <span className="kb-doc-name">{doc.filename}</span>
                    <span className="kb-doc-meta">{documentStatusLabel(doc.status)} · {doc.chunkCount} chunks · {doc.charCount} 字{error ? ` · ${error}` : ''}</span>
                    {canRetry && <button className="kb-doc-del" onClick={() => retryDoc(kb.key, doc.id)}>重试</button>}
                    {perm.edit && <button className="kb-doc-del" onClick={() => deleteDoc(kb.key, doc.id, doc.filename)}>删除</button>}
                  </div>
                );
              })}</div>}
              {results.length > 0 && (
                <div className="kb-results">
                  <div className="kb-doc-title">检索结果 · {ragStatus?.label || 'RAG 状态待判断'}</div>
                  {gate?.allowed !== undefined && <div className="kb-relevance">第一层：{gate.intent} · {gate.reason}</div>}
                  {results.map((item) => <div className="kb-result" key={item.chunkId}><div><b>{item.filename || `Chunk ${item.chunkIndex}`}</b><span>排序分 {formatScore(item.score)} · {relevanceLabel(item.relevance)}</span></div>{item.relevance?.reasons?.length > 0 && <small className="kb-relevance">依据：{item.relevance.reasons.map(reasonLabel).join(' / ')}</small>}<p>{item.content}</p></div>)}
                </div>
              )}
              {gate && results.length === 0 && (
                <div className="kb-results">
                  <div className="kb-result">
                    <div><b>未进入知识库召回</b><span>{ragGateLabel(gate)}</span></div>
                    <small className="kb-relevance">前置 gate：{gate.intent} · {gate.reason}</small>
                    <p>当前问题未识别为业务知识库问题，因此不会检索知识库资料。</p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
