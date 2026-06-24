import { Network } from 'lucide-react';

type ArchitectureLayer = {
  name: string;
  color: string;
  nodes: string[];
};

const layers: ArchitectureLayer[] = [
  { name: '应用层', color: '#4F46E5', nodes: ['企微 AI 助手', 'Web 后台管理', '知识库上传'] },
  { name: '服务层', color: '#10B981', nodes: ['FastAPI', '权限服务', 'Chunk 服务', 'Embedding 服务'] },
  { name: '数据层', color: '#7C3AED', nodes: ['PostgreSQL', 'Chroma 向量库', '文档切片'] }
];

export default function Architecture() {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title"><Network size={18} /> 系统架构</span>
      </div>
      <div className="card-body arch-layers">
        {layers.map((layer) => (
          <div className="arch-layer" key={layer.name}>
            <div className="arch-layer-header" style={{ background: layer.color }}>{layer.name}</div>
            <div className="arch-layer-body">
              {layer.nodes.map((node) => <span className="arch-node" key={node}>{node}</span>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

