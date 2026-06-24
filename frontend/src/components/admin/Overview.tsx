import React from 'react';
import Agents from './Agents';
import Logs from './Logs';

export default function Overview({ data }) {
  const safeData = data || {};
  const insights = safeData.businessInsights || {};
  const sales = insights.sales || {};
  const design = insights.design || {};
  const content = insights.content || {};
  const rag = insights.rag || {};
  const agent = insights.agent || {};
  const summary = insights.summary || [];

  return (
    <>
      <div className="metric-grid">
        {(safeData.metrics || []).map((metric) => (
          <div className={'metric-card ' + metric.theme} key={metric.label}>
            <div className="metric-icon">{metric.icon}</div>
            <div className="metric-value">{metric.value}</div>
            <div className="metric-label">{metric.label}</div>
            <div className="trend-up">▲ {metric.trend}</div>
          </div>
        ))}
      </div>

      <div className="insight-grid">
        {summary.map((item) => (
          <div className="insight-card" key={item.label}>
            <span>{item.label}</span>
            <b>{item.value}</b>
            <em>{item.hint}</em>
          </div>
        ))}
      </div>

      <div className="ops-grid">
        <InsightPanel
          title="销售转化"
          rows={[
            ['线索总数', sales.totalLeads || 0],
            ['高意向线索', sales.highValueLeads || 0],
            ['已确认完成', sales.confirmedLeads || 0],
            ['转化率', sales.conversionRate || '0%']
          ]}
        />
        <InsightPanel
          title="设计流转"
          rows={[
            ['需求卡', design.totalCards || 0],
            ['已分配', design.assignedCards || 0],
            ['分配率', design.assignmentRate || '0%']
          ]}
        />
        <InsightPanel
          title="内容产出"
          rows={[
            ['推广文案', content.promoCopies || 0],
            ['可发布', content.publishReady || 0],
            ['就绪率', content.readyRate || '0%']
          ]}
        />
        <InsightPanel
          title="RAG / Agent"
          rows={[
            ['RAG 查询', rag.totalQueries || 0],
            ['命中/可能', `${rag.hits || 0}/${rag.maybes || 0}`],
            ['Agent 成功率', agent.successRate || '0%'],
            ['估算成本', agent.estimatedCost || '￥0.00']
          ]}
        />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">本周 AI 调用趋势</span>
          </div>
          <div className="card-body">
            <div className="line-chart-placeholder">
              {(safeData.weeklyUsage || []).map((day) => (
                <div className="lc-col" key={day.day}>
                  <div className="lc-bars">
                    <i style={{ height: day.sales + '%', background: 'linear-gradient(180deg,#4F46E5,#818CF8)' }} />
                    <i style={{ height: day.design + '%', background: 'linear-gradient(180deg,#F97316,#FB923C)' }} />
                    <i style={{ height: day.promo + '%', background: 'linear-gradient(180deg,#7C3AED,#A78BFA)' }} />
                  </div>
                  <span>{day.day}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <Logs logs={(safeData.logs || []).slice(0, 3)} compact />
      </div>

      <Agents agents={safeData.agents || []} compact />
    </>
  );
}

function InsightPanel({ title, rows }) {
  return (
    <div className="card insight-panel">
      <div className="card-header">
        <span className="card-title">{title}</span>
      </div>
      <div className="insight-rows">
        {rows.map(([label, value]) => (
          <div className="insight-row" key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}



