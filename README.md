# 家装 AI 转型平台

![家装 AI 转型平台](docs/assets/home-ai-platform-hero.png)

面向家装定制企业的全栈 AI 转型 demo。项目把销售接待、设计需求梳理、内容推广、知识库问答、企业微信入口和 Agent 工具编排放在同一个可运行骨架里，适合用于内部演示、二次开发和上云部署验证。

## 适用场景

- 销售团队：客户初筛、报价解释、异议处理、产品工艺与 FAQ 问答。
- 设计团队：需求卡生成、案例与工艺标准检索、材料规格辅助说明。
- 推广团队：小红书、抖音、朋友圈、公众号等内容文案生成与发布任务沉淀。
- 管理层：公司制度、经营资料、人员绩效和战略资料的权限化问答。
- IM 入口：预留企业微信回调和长连接 sidecar，可把同一套 Agent 能力接入会话场景。

## 技术栈

- 前端：React + Vite + TypeScript
- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：PostgreSQL
- 向量检索：本地 fastembed 模型 + ChromaDB + BM25 + rerank + RAG Triad
- 大模型：OpenAI-compatible `/v1/chat/completions`，支持 DeepSeek 兼容调用
- 编排：LangGraph 风格 Agent Runtime，支持工具路由、审计日志和业务产物沉淀
- 部署：Docker Compose、Caddy、GitHub Actions

## 快速启动

```powershell
npm run start:dev
```

或手动启动：

```powershell
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
npm --prefix frontend install
npm --prefix frontend run dev
```

访问地址：

- 前端管理台：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 演示能力

- 登录、JWT、角色权限和用户管理
- 知识库创建、文档上传、异步解析、chunk、embedding、检索和删除
- 三层 RAG 判定：意图分类、reranker 分数、RAG Triad
- Chat Completions 兼容接口，支持 `/api/chat/completions` 和 `/v1/chat/completions`
- DeepSeek 真实接口配置，不再使用本地 mock 回答
- 企业微信 webhook 与长连接 sidecar 适配
- 内容生成、业务产物保存、多平台发布任务适配
- MoneyPrinterTurbo 视频生成工具接入编排
- 云服务器部署检查、密钥扫描、CI 检查

## 目录结构

```text
backend/       FastAPI 后端、数据库模型、RAG、Agent、企微和业务服务
frontend/      React + Vite 管理台
docs/          部署文档、数据库设计和项目说明
integrations/  企业微信长连接 sidecar
scripts/       本地启动、迁移、部署检查和运维脚本
.github/       GitHub Actions 工作流
```

## 关键配置

复制 `.env.example` 后按需配置：

```env
DATABASE_URL=postgresql+psycopg://homeai:change-me-in-local-env@localhost:5432/homeai_platform
JWT_SECRET_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_ALLOW_DOWNLOAD=false
```

生产环境请使用 `.env.production.example`，并确保所有默认演示密码、JWT 密钥和第三方 API Key 都已替换。

## 质量检查

```powershell
uv run --with-requirements backend\requirements.txt pytest -q
uvx ruff check backend scripts
npm run lint --prefix frontend
npm run build --prefix frontend
npm run check:deploy
```

`check:deploy` 会检查生产配置、密钥占位、迁移文件、Docker 配置和本地敏感文件状态。真实密钥只放在本地 `.env` 或服务器环境变量中，不要提交到仓库。

## 文档

- [项目说明](docs/README.md)
- [云服务器部署](docs/deploy-cloud.md)
- [企业微信长连接](docs/wecom-long-connection.md)
- [数据库表设计](schema.sql)
