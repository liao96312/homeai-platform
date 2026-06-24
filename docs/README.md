# 品爱 AI 平台全栈骨架

## 目录结构

```text
D:\project
├─ .github/workflows/      CI/CD 工作流
├─ backend/                 FastAPI 后端
│  ├─ app/
│  │  ├─ api/routes.py      主 API 路由
│  │  ├─ api/schemas.py     API 入参模型
│  │  ├─ api/payloads.py    响应 payload 转换
│  │  ├─ core/config.py     环境配置
│  │  ├─ db/session.py      SQLAlchemy 连接
│  │  ├─ models/domain.py   PostgreSQL ORM 表模型
│  │  ├─ services/business_tools.py 销售/设计/推广业务算法
│  │  ├─ services/seed.py   原型静态数据种子
│  │  └─ main.py            FastAPI 入口
│  └─ requirements.txt
├─ frontend/                React + Vite 前端
│  ├─ src/
│  │  ├─ api/client.js      API 客户端
│  │  ├─ pages/AdminApp.jsx Web 后台管理端入口
│  │  ├─ components/admin/  后台页面组件
│  │  ├─ App.jsx
│  │  ├─ main.jsx
│  │  └─ styles.css
│  ├─ vite.config.js        Vite React 插件、dev proxy 与 build 配置
│  └─ package.json
├─ docs/schema.sql          PostgreSQL 表设计
├─ docker-compose.yml       PostgreSQL、FastAPI、nginx 前端演示编排
├─ docker-compose.prod.yml  云服务器生产编排（Caddy/Postgres/Redis/Backend/Frontend）
├─ Caddyfile                HTTPS 反向代理配置
├─ .env.production.example  生产环境变量模板
├─ docs/deploy-cloud.md     云服务器部署、备份与运维说明
└─ package.json             根目录快捷脚本
```

## 启动命令

```bash
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
npm --prefix frontend install
npm --prefix frontend run dev
```

前端地址：`http://localhost:5173`

后端地址：`http://localhost:8000`

Windows 本地也可以使用：

```powershell
npm run start:dev
npm run db:migrate
npm run smoke
```

Docker 全栈演示：

```bash
docker compose up
```

该命令会启动 PostgreSQL、FastAPI 后端和 nginx 静态前端容器。前端镜像会先执行 `vite build`，再由 nginx 托管 `dist`，并将 `/api`、`/v1`、`/wecom`、`/health` 反代到后端；后端启动前会执行 Alembic 迁移。

## API

- `GET /health`：基础存活检查
- `GET /health/detail`：数据库、向量库、LLM、Embedding 配置健康检查，不返回密钥
- `POST /api/auth/login`：登录，返回 JWT 和当前用户角色
- `GET /api/auth/me`：读取当前登录用户
- `GET /api/admin/users`：管理员查看用户列表
- `POST /api/admin/users`：管理员创建用户
- `PATCH /api/admin/users/{id}`：管理员更新姓名、角色、启停状态或重置密码
- `DELETE /api/admin/users/{id}`：管理员删除非当前登录用户
- `GET /api/admin/bootstrap`：后台总览、Agent、知识库、角色权限、日志等数据
- `POST /api/chat/completions`：OpenAI Chat Completions 兼容格式聊天接口
- `POST /v1/chat/completions`：OpenAI-compatible base URL 入口
- `POST /api/chat`：旧版简化聊天接口，内部复用 Chat Completions 服务
- `GET /api/conversations`：按当前角色读取可访问 AI 会话列表和历史消息
- `GET /api/conversations/{conversation_key}`：读取单个 AI 会话历史，用于验证聊天持久化和后续 IM 入口复用
- `POST /api/admin/knowledge-bases`：管理员新建知识库
- `PATCH /api/admin/configs/{config_key}`：管理员更新系统配置开关
- `PATCH /api/admin/agents/{agent_key}`：管理员切换 AI 助手运行状态
- `PATCH /api/admin/permissions/{kb_key}/{role_key}`：管理员修改角色知识库权限
- `POST /api/knowledge/{kb_key}/documents`：上传知识库文档，解析文本、切 chunk、生成 embedding 并入库
- `GET /api/knowledge/{kb_key}/documents`：查看知识库文档列表
- `DELETE /api/knowledge/{kb_key}/documents/{doc_id}`：删除知识库文档和对应切片
- `POST /api/knowledge/{kb_key}/search`：对指定知识库执行向量检索
- `POST /api/sales/lead-score`：销售客户初筛，按预算、面积、风格、时间、联系方式、关键词和竞品意向生成评分与跟进建议
- `POST /api/design/requirement-card`：设计需求卡，将客户描述解析成户型、面积、风格、预算、材料偏好、重点空间和待办
- `POST /api/promo/copy`：推广文案生成，使用 DeepSeek + RAG 输出标题、正文、标签、CTA 和素材建议
- `POST /api/publish/jobs`：创建真实多平台发布任务；当前采用 MultiPost API 适配，按平台写入 `publish_jobs`，未配置 `MULTIPOST_API_KEY`/`MULTIPOST_TARGET_CLIENT_ID` 时返回 `needs_config`，不会标记为已发布
- `GET /api/publish/jobs`：查看最近发布任务状态、外部 taskId、错误原因和原始请求/响应
- `POST /api/publish/jobs/{id}/retry`：重试单个平台发布任务
- `POST /api/agent/dispatch`：兼容旧入口，统一 Agent 分流并返回 `run`，根据输入自动路由到销售初筛、设计需求卡、推广文案或普通聊天
- `POST /api/agent/run`：创建一次 Agent Runtime 运行，当前由 LangGraph 执行 `intent_classification -> tool_execution -> answer_generation`，返回 run、steps、toolCalls
- `GET /api/agent/tools`：查看当前可用 Agent 工具目录，按角色过滤销售、设计、推广和聊天工具
- `GET /api/agent/runs`：查看 Agent Run 列表，支持按 `status_filter`、`channel` 和 `limit` 筛选
- `GET /api/agent/runs/{id}`：查看一次 Agent Run 的状态、输入输出、步骤和工具调用记录
- `POST /api/agent/runs/{id}/retry`：基于原输入创建新的 Agent Run，可传 `max_attempts` 控制工具执行重试次数
- `POST /api/agent/runs/{id}/cancel`：取消未完成的 Agent Run
- `POST /api/agent/runs/{id}/handoff`：将 Agent Run 标记为等待人工接管
- `POST /api/agent/runs/{id}/resume`：提交人工决策并恢复/结束 Agent Run
- `GET /api/rag/query-logs`：查看最近 RAG 检索日志，包含命中数、是否注入 LLM、top sources 和召回分数
- `GET /api/artifacts`：查看最近业务产物，包含销售初筛、设计需求卡、推广文案
- `POST /api/artifacts`：保存业务产物，供后续审核、发布或流转
- `GET /api/artifacts/{id}`：查看单个业务产物详情
- `PATCH /api/artifacts/{id}`：更新标题、状态或结构化结果；状态支持 `draft/pending/confirmed/assigned/completed/archived`
- `DELETE /api/artifacts/{id}`：删除业务产物
- `GET /wecom/callback`：企业微信回调 URL 验证，支持 `msg_signature/timestamp/nonce/echostr`
- `POST /wecom/callback`：企业微信消息回调入口，支持加密 XML、普通 XML、JSON 文本消息
- `POST /api/wecom/robot/send`：管理员测试发送企业微信群机器人消息

知识库上传当前支持 `.txt`、`.md`、`.csv`、`.json`、`.html`、`.htm`、`.docx`、`.pdf`、`.xlsx`、`.xls`，单文件默认限制 10MB。Embedding 使用本地开源 `fastembed` 模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，模型缓存目录默认为 `./models/fastembed`。首次使用前运行 `.\scripts\init-embedding.ps1` 下载到本地；运行时默认 `EMBEDDING_ALLOW_DOWNLOAD=false`，只读本地模型，不再 fallback 到 hash embedding。旧 hash embedding 生成的 chunk 不会参与当前模型检索，需要重新上传或重建索引。向量写入 ChromaDB，同时在 SQL 表中保存文档、切片、embedding 和元数据。检索链路为 Guarded Hybrid RAG：先做业务意图 gate，再执行 Chroma 向量召回 + SQL BM25 关键词召回 + 本地轻量 rerank，最后用防御性 RRF 融合排序；相同 `query + kb + top_k + embedding_model` 会进入 10 分钟短期缓存，上传或删除文档后自动失效。接口返回 `score/vectorScore/bm25Score/rerankScore/searchMode/relevance/fusion`，聊天响应会在 `metadata.rag.citations` 中返回最终注入 LLM 的 ranked citations。

列表接口支持基础分页，常用参数为 `limit` 和 `offset`，例如 `/api/rag/query-logs?limit=20&offset=40`、`/api/artifacts?limit=20`、`/api/publish/jobs?limit=20`、`/api/knowledge/product/documents?limit=20`。返回体会包含 `total/limit/offset`。

运行时治理：

- `APP_ENV=development` 时允许开发态自动 `create_all`；`production/prod/staging` 必须使用 Alembic migration。
- 生产类环境必须显式配置 `JWT_SECRET_KEY` 和所有种子账号密码，不能使用默认演示密码。
- 每个请求会返回 `x-request-id` 和 `x-response-time-ms`，错误响应统一包含 `detail/code/requestId`。

注意：`score` 是融合后的排序分，不是概率意义上的“置信度”。RAG 判定分三层：

1. 意图分类：判断问题是不是业务知识库问题。只有家装定制业务问题或本项目平台问题才会进入 embedding、Chroma、BM25、rerank；日常饮食、天气时间、问候身份、情绪陪聊、个人生活和普通非业务泛问会直接跳过知识库。gate 会计算有效业务词命中率，并识别“板材、报价、环保、产品、柜子、材料、质量”等核心短词；但闲聊里偶然带少量业务词仍会被拦截。
2. Reranker 分数：判断召回内容是否真的相关。普通召回证据必须至少命中两类独立信号，例如关键词重合、向量相似、rerank 重合、业务强词等。对“板材环保/产品报价”这类短业务查询，允许“强业务词 + 高 BM25 或 rerank”作为单强信号通过。`retrieval.topRerankScore >= 0.55` 且存在高相关资料时视为强命中；`>= 0.34` 视为可能相关；低于阈值视为未命中。Hybrid 融合使用 RRF 排名分，向量相似度很低或业务命中率不足时会压低 BM25 权重，避免 BM25 min-max 归一化造成假高分。
3. RAG Triad：聊天生成后继续判断回答是否基于资料、是否切题、上下文是否相关，字段为 `triad.groundedness`、`triad.answerRelevance`、`triad.contextRelevance`。

接口最终返回 `ragStatus` / `metadata.rag.status`：`✅ 已命中知识库`、`⚠ 可能相关，建议人工确认`、`❌ 知识库未命中`。`ragGate`、`retrieval`、`triad` 和 `relevance.reasons` 会记录通过/拦截依据，便于在 RAG 观测页排查误召回。

浏览器管理台登录后使用 httpOnly Cookie 保存 JWT；外部 API/脚本仍可使用 `Authorization: Bearer <token>` 调用受保护接口。

Chat Completions 示例：

```json
{
  "model": "deepseek-chat",
  "messages": [
    { "role": "system", "content": "你是销售AI助手。" },
    { "role": "user", "content": "客户想了解120平新中式报价" }
  ],
  "temperature": 0.7,
  "metadata": { "conversation_key": "sales" }
}
```

DeepSeek 兼容示例：

```json
{
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "messages": [
    { "role": "user", "content": "生成一段新中式全屋定制销售话术" }
  ],
  "thinking": { "type": "disabled" },
  "metadata": { "conversation_key": "sales" }
}
```

本地开发时必须配置 `DEEPSEEK_API_KEY` 才能调用聊天接口；未配置时接口会返回明确错误，不再回退到本地模拟响应。配置后会转发到 `DEEPSEEK_BASE_URL/chat/completions`。

### API 版本策略

- `/api/*`：平台内部管理 API，供当前 React 管理台、企微 sidecar 和后台工具调用。
- `/v1/*`：对外兼容 API，目前用于 OpenAI-compatible `POST /v1/chat/completions`。
- 新的外部稳定接口优先放到 `/v1`，内部运营接口继续放到 `/api`。

### 安全与生产配置

- 生产或 staging 必须配置稳定的 `JWT_SECRET_KEY`，否则服务会拒绝启动。
- 密码哈希默认使用 PBKDF2-SHA256 600,000 次迭代；旧 120,000 次格式仍可验证。
- 浏览器写请求必须带可信 `Origin`/`Referer`；Origin 会按 scheme/host/port 精确匹配，避免相似域名前缀绕过。
- 服务端脚本可使用 `Authorization: Bearer` 调用 API；企微内部 token 只允许无浏览器 Origin/Referer 的 `/api/wecom/*` 内部请求绕过 CSRF。
- 可配置 `REDIS_URL` 启用 Redis 滑动窗口限流与知识库搜索缓存；未配置时本地开发回退到进程内限流/缓存。
- `KNOWLEDGE_SEARCH_CACHE_TTL_SECONDS` 控制知识库搜索缓存 TTL，默认 600 秒。
- `MAX_REQUEST_BODY_BYTES` 用于全局请求体大小保护，知识库上传仍有单文件 10MB 业务限制。
- `.env`、`dev.db`、`logs/`、`chroma_data/`、`models/` 只允许本地存在，不应提交。可运行 `powershell -ExecutionPolicy Bypass -File scripts/check-secrets.ps1` 做本地审计。

### 视频生成接入

视频生成暂时通过本机 MoneyPrinterTurbo 项目执行，当前后端会调用：

```text
POST http://127.0.0.1:8080/api/v1/videos
GET  http://127.0.0.1:8080/api/v1/tasks/{task_id}
```

启动 MoneyPrinterTurbo：

```powershell
cd D:\workplace\MoneyPrinterTurbo
python main.py
```

主项目可配置：

```env
MONEY_PRINTER_API_BASE_URL=http://127.0.0.1:8080/api/v1
MONEY_PRINTER_PROJECT_DIR=D:\workplace\MoneyPrinterTurbo
VIDEO_GENERATION_DEFAULT_SOURCE=pexels
VIDEO_GENERATION_DEFAULT_ASPECT=9:16
VIDEO_GENERATION_DEFAULT_CLIP_DURATION=5
VIDEO_GENERATION_DEFAULT_VOICE=zh-CN-XiaoxiaoNeural
VIDEO_GENERATION_POLL_INTERVAL_SECONDS=15
VIDEO_GENERATION_POLL_TIMEOUT_SECONDS=900
```

Agent 编排中新增了 `video_generation` 工具。网页业务工具和企微长连接入口都可以通过“生成视频/短视频/宣传片/剪辑/成片”等意图触发该工具，提交后会生成 `video_generation` 业务产物并返回 MoneyPrinterTurbo task id。

企微长连接 sidecar 会在视频任务提交后继续轮询 `/api/wecom/video-tasks/{task_id}/delivery`。当 MoneyPrinterTurbo 返回 `videos` 或 `combined_videos` 且本地 mp4 文件存在时，sidecar 会读取本地文件，调用企微 SDK `uploadMedia(type='video')` 上传临时素材，再通过 `sendMediaMessage` 把视频发回当前会话。

多平台发布采用 MultiPost 方案：该项目支持小红书、抖音、微博、知乎、公众号等国内常见平台，并提供 Extension API / REST API。后端通过环境变量保存密钥，前端不会接触 API Key：

```env
MULTIPOST_API_BASE_URL=https://api.multipost.app
MULTIPOST_API_KEY=
MULTIPOST_TARGET_CLIENT_ID=
MULTIPOST_AUTO_PUBLISH=true
```

未配置 `MULTIPOST_API_KEY` 或 `MULTIPOST_TARGET_CLIENT_ID` 时，`/api/publish/jobs` 只会创建 `needs_config` 任务，明确提示未真发；配置完成后会调用 `POST /extension/task` 创建真实发布任务，并保存外部 `taskId`。

也可以把本服务作为 OpenAI-compatible base URL 使用：

```python
from openai import OpenAI

client = OpenAI(
    api_key="<登录后拿到的 JWT>",
    base_url="http://localhost:8000/v1",
)

resp = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "客户关心环保板材，怎么回答？"}],
    extra_body={
        "provider": "deepseek",
        "metadata": {"conversation_key": "sales"},
    },
)
print(resp.choices[0].message.content)
```

## 演示账号

默认用户由 `SEED_*_PASSWORD` 环境变量创建。前端快捷登录按钮只有在 `VITE_SHOW_DEMO_USERS=true` 时显示，并读取 `VITE_DEMO_*_PASSWORD`。生产/预发环境必须显式配置强密码，不能使用 `.env.example` 中的本地演示值。

| 角色 | 用户名 | 密码来源 |
| --- | --- | --- |
| 超级管理员 | `admin` | `SEED_ADMIN_PASSWORD` |
| 销售团队 | `sales` | `SEED_SALES_PASSWORD` |
| 销售总监 | `sales_director` | `SEED_SALES_DIRECTOR_PASSWORD` |
| 设计师 | `designer` | `SEED_DESIGNER_PASSWORD` |
| 设计经理 | `design_manager` | `SEED_DESIGN_MANAGER_PASSWORD` |
| 推广团队 | `promo` | `SEED_PROMO_PASSWORD` |
| 推广经理 | `promo_manager` | `SEED_PROMO_MANAGER_PASSWORD` |
| 管理层 | `management` | `SEED_MANAGEMENT_PASSWORD` |

## 知识库权限分级

| 知识库 | 可访问角色 | 主要内容 |
| --- | --- | --- |
| 销售库 | 销售团队、销售总监 | 产品工艺、报价、话术、FAQ、竞品分析 |
| 设计库 | 设计师、设计经理 | 案例图库、工艺标准、材质规格 |
| 推广库 | 推广团队、推广经理 | 品牌规范、竞品分析、爆款文案模板 |
| 管理库 | 管理层 | 经营数据、人员绩效、战略资料 |
| 公共库 | 全体业务角色 | 公司介绍、规章制度、通用培训资料 |

## 数据库表设计

见 `docs/schema.sql`。核心表包括：

- `roles`：角色与人数
- `users`：登录用户、密码哈希、所属角色
- `knowledge_bases`：知识库基础信息
- `knowledge_permissions`：角色到知识库的查看、编辑、管理权限
- `knowledge_documents`：上传文档元数据
- `knowledge_chunks`：文档切片、embedding 模型名和检索元数据；完整向量写入 ChromaDB，不再重复存入 SQL
- `agents`：AI 岗位助手运行状态
- `dashboard_metrics`：运营总览指标
- `operation_logs`：操作日志
- `system_configs`：系统配置开关
- `conversations`：会话元数据、快捷动作和历史 JSON 兼容字段
- `conversation_messages`：规范化会话消息表，支持按消息分页/查询并避免单行 JSON 无限增长
- `marketing_platforms`：一键发布平台
- `business_artifacts`：销售初筛、设计需求卡、推广文案等业务产物及结果 JSON
- `publish_jobs`：多平台发布任务，记录 MultiPost 平台编码、外部 taskId、请求/响应、失败原因和状态
- `agent_runs`：Agent Runtime 主运行记录，包含渠道、会话、意图、路由、工具、输入输出、状态和 LangGraph state
- `agent_steps`：Agent Run 的步骤轨迹，如意图分类、工具执行、回答生成
- `agent_tool_calls`：Agent 工具调用审计，记录工具名、输入、输出、错误和状态
- `agent_handoffs`：人工接管记录，保存待审批原因、处理人和审批/恢复决策
- `rag_query_logs`：RAG 检索日志，记录查询、命中数量、注入状态、top sources 与召回分数
- `wecom_webhook_events`：企业微信 webhook 事件、AI回复与发送状态日志

## 看板统计口径

- 知识库命中率来自最近 500 条 `rag_query_logs`：按 `conversation_key` 或 `top_sources[].kbKey` 匹配知识库，命中数 / 查询数计算。
- 周用量来自当前自然周内的 RAG 查询日志和企业微信事件，按真实 `created_at` 的星期几聚合到 `sales/design/promo` 三类，不再按最近记录序号取模。

## 企业微信接入

`.env` 里配置：

```env
WECOM_CALLBACK_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_CORP_ID=
WECOM_ROBOT_WEBHOOK_URL=
WECOM_ROBOT_WEBHOOK_KEY=
WECOM_DEFAULT_CONVERSATION_KEY=sales
```

说明：

- 企业微信应用回调 URL 可填：`https://你的域名/wecom/callback`
- 如果配置了 `WECOM_CALLBACK_TOKEN` 和 `WECOM_ENCODING_AES_KEY`，会校验 `msg_signature` 并解密 `Encrypt`
- 群机器人可直接配置完整 `WECOM_ROBOT_WEBHOOK_URL`，或只配置 webhook `key`
- 当前收到文本消息后会先进入统一 Agent 分流：销售线索生成评分、设计需求生成需求卡、推广任务调用 DeepSeek + RAG 生成文案；其他问题进入默认聊天 Agent。回复会通过群机器人 webhook 发送，并写入 `wecom_webhook_events`。
