import React from 'react';
import { Settings } from 'lucide-react';
import { api } from '../../api/client';

export default function Config({ configs, isAdmin, reload, setToast }) {
  const safeConfigs = Array.isArray(configs) ? configs : [];
  async function toggle(config) {
    try {
      await api.updateConfig(config.key, { enabled: !config.enabled });
      setToast('配置已更新');
      await reload();
    } catch (err) {
      setToast(err.message);
    }
  }

  return (
    <div className="card">
      <div className="card-header"><span className="card-title"><Settings size={18} /> 系统配置</span></div>
      {safeConfigs.map((config) => (
        <div className="config-row" key={config.key}>
          <div>
            <div className="config-name">{config.name}</div>
            <div className="config-desc">{config.description}</div>
          </div>
          <button
            disabled={!isAdmin}
            className={'toggle ' + (config.enabled ? 'on' : '')}
            onClick={() => toggle(config)}
            aria-label={config.name + (config.enabled ? '已开启' : '已关闭')}
          />
        </div>
      ))}
    </div>
  );
}



