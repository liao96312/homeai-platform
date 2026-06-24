/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react';
import type { LooseRecord, Permission } from '../../types/admin';

export const themeBg: Record<string, string> = {
  blue: '#EEF2FF',
  green: '#ECFDF5',
  orange: '#FFF7ED',
  purple: '#FAF5FF',
  sales: '#EEF2FF',
  design: '#FFF7ED',
  promo: '#FAF5FF',
  management: '#ECFDF5'
};

export function formatJson(value: unknown) {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch {
    return String(value || '');
  }
}

export function formatScore(score: unknown) {
  if (score === undefined || score === null) return '0.000';
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(3) : '0.000';
}

export function relevanceLabel(relevance?: LooseRecord | null) {
  if (!relevance) return '未评估';
  if (relevance.accepted === false) return '已过滤';
  const labels: Record<string, string> = { high: '高相关', medium: '中相关', low: '低相关', rejected: '已过滤' };
  return labels[String(relevance.level || '')] || '未评估';
}

export function reasonLabel(reason: unknown) {
  const labels: Record<string, string> = {
    keyword_overlap: '关键词重合',
    bm25: '关键词匹配',
    bm25_strong: '关键词强匹配',
    rerank_overlap: '资料相关性较高',
    domain_vector: '向量相似'
  };
  return labels[String(reason || '')] || String(reason || '');
}

export function ragGateLabel(gate?: LooseRecord | null) {
  if (!gate) return '未判断';
  if (gate.allowed) return '进入知识库召回';
  const labels: Record<string, string> = {
    non_business_smalltalk: '日常闲聊，已拦截',
    too_short_without_domain_intent: '缺少业务意图，已拦截',
    no_domain_or_project_signal: '非业务知识库问题，已拦截',
    empty_query: '问题为空'
  };
  return labels[String(gate.reason || '')] || '未进入知识库召回';
}

export function agentRunStatusLabel(status: unknown) {
  const labels: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    waiting_human: '待人工',
    pending: '等待中'
  };
  return labels[String(status || '')] || String(status || '未知');
}

export function agentRunTagClass(status: unknown) {
  const labels: Record<string, string> = {
    completed: 'tag-blue',
    running: 'tag-orange',
    waiting_human: 'tag-orange',
    failed: 'tag-red',
    cancelled: 'tag-red'
  };
  return labels[String(status || '')] || 'tag-blue';
}

export function agentStepLabel(name: unknown) {
  const labels: Record<string, string> = {
    intent_classification: '意图分类',
    tool_execution: '工具调用',
    answer_generation: '回答生成',
    human_handoff: '转人工',
    human_resume: '人工恢复',
    cancelled: '取消',
    failed: '失败'
  };
  return labels[String(name || '')] || String(name || '步骤');
}

export function permissionLabel(p: Permission = {}) {
  if (p.manage) return '管理';
  if (p.edit) return '编辑';
  if (p.view) return '查看';
  return '无权限';
}

export function PermTag({ p = {} }: { p?: Permission }) {
  if (p.manage) return <span className="tag tag-green">查看/编辑/管理</span>;
  if (p.edit) return <span className="tag tag-blue">查看/编辑</span>;
  if (p.view) return <span className="tag tag-gray">仅查看</span>;
  return <span className="tag tag-red">无权限</span>;
}

export function Stat({ v, l }: { v?: ReactNode; l?: ReactNode }) {
  return (
    <div className="kb-stat">
      <div className="kb-stat-value">{v}</div>
      <div className="kb-stat-label">{l}</div>
    </div>
  );
}
