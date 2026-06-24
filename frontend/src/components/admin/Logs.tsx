import { ScrollText } from 'lucide-react';
import type { LooseRecord } from '../../types/admin';
import { themeBg } from './AdminShared';

type LogsProps = {
  logs?: LooseRecord[];
  compact?: boolean;
};

export default function Logs({ logs = [], compact = false }: LogsProps) {
  const safeLogs = Array.isArray(logs) ? logs : [];
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title"><ScrollText size={18} /> {compact ? '最近操作' : '操作日志'}</span>
      </div>
      <div className="card-body log-list">
        {safeLogs.map((log, idx) => (
          <div className="log-item" key={`${log.title}-${log.time_label}-${idx}`}>
            <div className="log-icon" style={{ background: themeBg[String(log.theme || 'blue')] }}>{log.icon}</div>
            <div className="log-info">
              <div className="log-title">{log.title}</div>
              <div className="log-detail">{log.detail}</div>
            </div>
            <div className="log-time">{log.time_label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

