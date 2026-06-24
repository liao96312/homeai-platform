-- Reference snapshot only. The source of truth for database structure is Alembic
-- migrations under backend/alembic/versions/.

CREATE TABLE IF NOT EXISTS roles (
  id SERIAL PRIMARY KEY,
  key VARCHAR(40) UNIQUE NOT NULL,
  name VARCHAR(80) NOT NULL,
  color VARCHAR(20) NOT NULL,
  user_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  full_name VARCHAR(120) NOT NULL,
  hashed_password VARCHAR(256) NOT NULL,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
  id SERIAL PRIMARY KEY,
  key VARCHAR(40) UNIQUE NOT NULL,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(240) NOT NULL,
  icon VARCHAR(12) NOT NULL,
  theme VARCHAR(40) NOT NULL,
  docs INTEGER NOT NULL DEFAULT 0,
  chunks INTEGER NOT NULL DEFAULT 0,
  hit_rate VARCHAR(20) NOT NULL DEFAULT '0%',
  updated_at_label VARCHAR(40) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS knowledge_permissions (
  id SERIAL PRIMARY KEY,
  kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  can_view BOOLEAN NOT NULL DEFAULT FALSE,
  can_edit BOOLEAN NOT NULL DEFAULT FALSE,
  can_manage BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (kb_id, role_id)
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id SERIAL PRIMARY KEY,
  kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  filename VARCHAR(255) NOT NULL,
  content_type VARCHAR(120) NOT NULL DEFAULT '',
  status VARCHAR(40) NOT NULL DEFAULT 'indexed',
  char_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  uploader_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_kb_id ON knowledge_documents(kb_id);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id SERIAL PRIMARY KEY,
  kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  token_estimate INTEGER NOT NULL DEFAULT 0,
  embedding_model VARCHAR(120) NOT NULL DEFAULT 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
  embedding JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_kb_id ON knowledge_chunks(kb_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_document_id ON knowledge_chunks(document_id);

CREATE TABLE IF NOT EXISTS agents (
  id SERIAL PRIMARY KEY,
  key VARCHAR(40) UNIQUE NOT NULL,
  name VARCHAR(120) NOT NULL,
  icon VARCHAR(12) NOT NULL,
  theme VARCHAR(40) NOT NULL,
  status VARCHAR(40) NOT NULL,
  calls_today INTEGER NOT NULL DEFAULT 0,
  success_rate VARCHAR(20) NOT NULL DEFAULT '0%',
  avg_latency VARCHAR(20) NOT NULL DEFAULT '0s'
);

CREATE TABLE IF NOT EXISTS dashboard_metrics (
  id SERIAL PRIMARY KEY,
  label VARCHAR(80) NOT NULL,
  value VARCHAR(40) NOT NULL,
  trend VARCHAR(40) NOT NULL,
  icon VARCHAR(12) NOT NULL,
  theme VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_logs (
  id SERIAL PRIMARY KEY,
  icon VARCHAR(12) NOT NULL,
  title VARCHAR(160) NOT NULL,
  detail TEXT NOT NULL,
  time_label VARCHAR(40) NOT NULL,
  theme VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS system_configs (
  id SERIAL PRIMARY KEY,
  key VARCHAR(80) UNIQUE NOT NULL,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(240) NOT NULL DEFAULT '',
  enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_system_configs_key ON system_configs(key);

CREATE TABLE IF NOT EXISTS conversations (
  id SERIAL PRIMARY KEY,
  key VARCHAR(40) UNIQUE NOT NULL,
  name VARCHAR(120) NOT NULL,
  assistant_name VARCHAR(120) NOT NULL,
  icon VARCHAR(12) NOT NULL,
  theme VARCHAR(40) NOT NULL,
  preview VARCHAR(240) NOT NULL,
  time_label VARCHAR(40) NOT NULL,
  unread INTEGER NOT NULL DEFAULT 0,
  quick_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
  messages JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id SERIAL PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender VARCHAR(20) NOT NULL DEFAULT 'ai',
  message_type VARCHAR(20) NOT NULL DEFAULT 'text',
  content TEXT NOT NULL DEFAULT '',
  extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_conversation_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_conversation_messages_sender ON conversation_messages(sender);
CREATE INDEX IF NOT EXISTS ix_conversation_messages_created_at ON conversation_messages(created_at);

CREATE TABLE IF NOT EXISTS marketing_platforms (
  id SERIAL PRIMARY KEY,
  label VARCHAR(40) NOT NULL,
  icon VARCHAR(12) NOT NULL,
  theme VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_templates (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  platform VARCHAR(40) NOT NULL DEFAULT '小红书',
  scene VARCHAR(80) NOT NULL DEFAULT '',
  prompt TEXT NOT NULL DEFAULT '',
  default_audience VARCHAR(160) NOT NULL DEFAULT '准备装修的家庭客户',
  default_tone VARCHAR(160) NOT NULL DEFAULT '专业、真实、有转化力',
  default_selling_points JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_promo_templates_platform ON promo_templates(platform);
CREATE INDEX IF NOT EXISTS ix_promo_templates_is_active ON promo_templates(is_active);
CREATE INDEX IF NOT EXISTS ix_promo_templates_created_at ON promo_templates(created_at);

CREATE TABLE IF NOT EXISTS business_artifacts (
  id SERIAL PRIMARY KEY,
  artifact_type VARCHAR(40) NOT NULL,
  title VARCHAR(160) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'draft',
  owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  source TEXT NOT NULL DEFAULT '',
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_label VARCHAR(40) NOT NULL DEFAULT '刚刚'
);

CREATE INDEX IF NOT EXISTS ix_business_artifacts_artifact_type ON business_artifacts(artifact_type);

CREATE TABLE IF NOT EXISTS publish_jobs (
  id SERIAL PRIMARY KEY,
  artifact_id INTEGER REFERENCES business_artifacts(id) ON DELETE SET NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  provider VARCHAR(40) NOT NULL DEFAULT 'multipost',
  platform_label VARCHAR(80) NOT NULL DEFAULT '',
  platform_code VARCHAR(80) NOT NULL DEFAULT '',
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  external_task_id VARCHAR(120) NOT NULL DEFAULT '',
  title VARCHAR(160) NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT NOT NULL DEFAULT '',
  scheduled_at TIMESTAMPTZ,
  created_at_label VARCHAR(40) NOT NULL DEFAULT '刚刚',
  updated_at_label VARCHAR(40) NOT NULL DEFAULT '刚刚'
);

CREATE INDEX IF NOT EXISTS ix_publish_jobs_artifact_id ON publish_jobs(artifact_id);
CREATE INDEX IF NOT EXISTS ix_publish_jobs_status ON publish_jobs(status);
CREATE INDEX IF NOT EXISTS ix_publish_jobs_scheduled_at ON publish_jobs(scheduled_at);

CREATE TABLE IF NOT EXISTS agent_runs (
  id SERIAL PRIMARY KEY,
  run_key VARCHAR(64) NOT NULL UNIQUE,
  channel VARCHAR(40) NOT NULL DEFAULT 'web',
  conversation_id VARCHAR(160) NOT NULL DEFAULT '',
  sender_id VARCHAR(120) NOT NULL DEFAULT '',
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'running',
  intent VARCHAR(80) NOT NULL DEFAULT '',
  route VARCHAR(80) NOT NULL DEFAULT '',
  tool_name VARCHAR(120) NOT NULL DEFAULT '',
  input_text TEXT NOT NULL DEFAULT '',
  output_text TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_agent_runs_channel ON agent_runs(channel);
CREATE INDEX IF NOT EXISTS ix_agent_runs_conversation_id ON agent_runs(conversation_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_status ON agent_runs(status);

CREATE TABLE IF NOT EXISTS agent_steps (
  id SERIAL PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  name VARCHAR(120) NOT NULL DEFAULT '',
  status VARCHAR(40) NOT NULL DEFAULT 'completed',
  detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_agent_steps_run_id ON agent_steps(run_id);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id SERIAL PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  tool_name VARCHAR(120) NOT NULL DEFAULT '',
  status VARCHAR(40) NOT NULL DEFAULT 'completed',
  input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_run_id ON agent_tool_calls(run_id);
CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_tool_name ON agent_tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_status ON agent_tool_calls(status);

CREATE TABLE IF NOT EXISTS agent_handoffs (
  id SERIAL PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  reason TEXT NOT NULL DEFAULT '',
  assigned_to_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  decision_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_agent_handoffs_run_id ON agent_handoffs(run_id);
CREATE INDEX IF NOT EXISTS ix_agent_handoffs_status ON agent_handoffs(status);

CREATE TABLE IF NOT EXISTS rag_query_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  conversation_key VARCHAR(40) NOT NULL DEFAULT '',
  query TEXT NOT NULL DEFAULT '',
  top_k INTEGER NOT NULL DEFAULT 5,
  hit_count INTEGER NOT NULL DEFAULT 0,
  injected BOOLEAN NOT NULL DEFAULT FALSE,
  top_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at_label VARCHAR(40) NOT NULL DEFAULT '刚刚',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_rag_query_logs_conversation_key ON rag_query_logs(conversation_key);
CREATE INDEX IF NOT EXISTS ix_rag_query_logs_created_at ON rag_query_logs(created_at);

CREATE TABLE IF NOT EXISTS wecom_webhook_events (
  id SERIAL PRIMARY KEY,
  source VARCHAR(40) NOT NULL DEFAULT 'callback',
  msg_type VARCHAR(40) NOT NULL DEFAULT '',
  from_user VARCHAR(120) NOT NULL DEFAULT '',
  conversation_key VARCHAR(40) NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  reply TEXT NOT NULL DEFAULT '',
  status VARCHAR(40) NOT NULL DEFAULT 'received',
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_wecom_webhook_events_created_at ON wecom_webhook_events(created_at);
