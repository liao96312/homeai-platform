import { api } from '../../api/client';
import type { LooseRecord, MaybePromise, ToastSetter } from '../../types/admin';

const statusMap: Record<string, [label: string, dotClass: string]> = {
  online: ['在线', ''],
  paused: ['暂停', 'dot-orange'],
  maintenance: ['维护', 'dot-red']
};

type AgentsProps = {
  agents?: LooseRecord[];
  compact?: boolean;
  isAdmin?: boolean;
  reload?: () => MaybePromise;
  setToast?: ToastSetter;
};

export default function Agents({ agents = [], compact = false, isAdmin = false, reload, setToast }: AgentsProps) {
  async function changeStatus(agentKey: string, status: string) {
    try {
      await api.updateAgent(agentKey, { status });
      setToast?.('AI 状态已更新');
      await reload?.();
    } catch (err) {
      setToast?.(err.message);
    }
  }

  return (
    <div className={compact ? '' : 'page-block'}>
      <div className="agent-status-grid">
        {agents.map((agent) => {
          const [label, dotClass] = statusMap[String(agent.status || '')] || statusMap.online;
          return (
            <div className="agent-stat-card" key={String(agent.key)}>
              <div className="agent-stat-icon">{agent.icon}</div>
              <div className="agent-stat-name">{agent.name}</div>
              <div className="agent-stat-val">{agent.calls_today}</div>
              <div className="agent-stat-label">
                今日调用 / {agent.success_rate} / {agent.avg_latency}
              </div>
              <span className={'dot-status ' + dotClass}>{label}</span>
              {isAdmin && !compact && (
                <div className="agent-actions">
                  {Object.keys(statusMap).map((status) => (
                    <button
                      key={status}
                      className={'mini-btn ' + (agent.status === status ? 'active' : '')}
                      onClick={() => changeStatus(String(agent.key), status)}
                    >
                      {statusMap[status][0]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

