# 云服务器部署清单

## 推荐拓扑

```text
公网域名 / HTTPS
  -> Caddy :80/:443
      -> frontend nginx :8080
      -> /api /v1 /wecom /health 反向代理到 backend:8000
backend
  -> PostgreSQL
  -> Redis
  -> chroma_data volume
  -> embedding_models volume
wecom-long-connection（可选 profile）
  -> backend:8000
MoneyPrinterTurbo（单独部署）
  -> backend 通过 MONEY_PRINTER_API_BASE_URL 调用
```

## 首次部署

1. 安装 Docker 和 Docker Compose。
2. 上传项目代码到服务器。
3. 复制生产环境变量模板：

```bash
cp .env.production.example .env.production
```

必填项：

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `HASH_EMBEDDING_KEY`（仅当 `EMBEDDING_PROVIDER=hash` 时必填；默认 fastembed 不需要）
- `CORS_ORIGINS`，必须是实际访问域名，例如 `["https://ai.example.com"]`
- `SEED_*_PASSWORD`
- `DEEPSEEK_API_KEY`
- `CADDY_DOMAIN`，例如 `ai.example.com`
- 如启用企微长连接：`WECOM_BOT_ID`、`WECOM_BOT_SECRET`、`WECOM_INTERNAL_TOKEN`
- 如启用视频生成：`MONEY_PRINTER_API_BASE_URL`

启动：

```bash
chmod +x scripts/*.sh
scripts/check-production-env.sh .env.production
scripts/deploy-cloud.sh
```

启用企微长连接 profile：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production --profile wecom up -d --build
```

## CI/CD

仓库内置 GitHub Actions：

- `.github/workflows/ci.yml`：PR 和 push 时执行后端测试、前端构建、Docker 配置校验。
- `.github/workflows/deploy.yml`：CI 通过后，通过 SSH 到云服务器执行生产部署脚本。

需要配置的 GitHub Secrets：

| Secret | 说明 |
| --- | --- |
| `SSH_HOST` | 云服务器公网 IP 或域名 |
| `SSH_USER` | SSH 用户，例如 `root` 或部署用户 |
| `SSH_KEY` | 私钥内容，建议使用专用 deploy key |
| `SSH_PORT` | SSH 端口，未配置时使用 22 |
| `DEPLOY_PATH` | 服务器项目目录，例如 `/opt/homeai` |
| `ENABLE_WECOM` | 可选，`true` 时部署企微长连接 profile |

服务器目录需提前准备：

```bash
mkdir -p /opt/homeai
cd /opt/homeai
git clone <your-repo-url> .
cp .env.production.example .env.production
vim .env.production
bash scripts/check-production-env.sh .env.production
```

## 生产必查项

- 生产必须配置 `REDIS_URL`，登录限流、全局限流、RAG 搜索缓存都会使用 Redis；未配置时只能作为单机演示。
- 生产必须使用强随机 `JWT_SECRET_KEY`；如启用 `EMBEDDING_PROVIDER=hash`，也必须设置强随机 `HASH_EMBEDDING_KEY`。不要使用 `change-me` 或 `local-dev` 占位值。
- 生产建议设置 `AUTO_MIGRATE_ON_STARTUP=false`，由 `scripts/deploy-cloud.sh` 单独执行 `alembic upgrade head`，避免多实例同时启动时并发迁移。
- 生产必须设置 `EXPOSE_API_DOCS=false`，避免暴露 `/docs`、`/redoc`、`/openapi.json`。
- 如经过 nginx/Caddy 反代，`TRUSTED_PROXY_IPS` 只填写可信代理容器或内网 IP/CIDR。服务只会在请求来自这些 IP 时采信 `X-Forwarded-For`，不要配置 `0.0.0.0/0` 这类全网段。
- `docs/schema.sql` 只是参考快照，真实数据库结构以 Alembic 迁移为准。
- `CORS_ORIGINS` 必须包含浏览器实际访问 origin，否则 CSRF 中间件会拒绝写请求。
- Caddy 的 CSP 默认 `connect-src 'self'`，浏览器前端只能直连本域 API；如果要让第三方前端或浏览器扩展直接调用 `/v1/chat/completions`，需要显式调整 CSP 和 CORS。

检查：

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1/health
# /health/detail 需要管理员登录令牌；日常探活用 /health。
```

## 数据持久化

生产 compose 使用 Docker volumes：

- `postgres_data`：业务数据库
- `redis_data`：限流和搜索缓存
- `chroma_data`：知识库向量索引
- `embedding_models`：本地 embedding 模型缓存

不要删除这些 volume。升级代码时使用：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## 备份

PostgreSQL 和 Chroma 备份：

```bash
scripts/backup-cloud.sh
```

脚本会生成：

- `backups/postgres-*.sql.gz`
- `backups/chroma-data-*.tar.gz`

默认保留最近 7 天，可通过 `RETENTION_DAYS=14 scripts/backup-cloud.sh` 调整。

定时备份示例：

```bash
crontab -e
```

```cron
0 2 * * * cd /opt/homeai && /bin/bash scripts/backup-cloud.sh >> logs/backup.log 2>&1
```

## 本地 Embedding 模型

生产默认 `EMBEDDING_ALLOW_DOWNLOAD=false`。首次部署前需要确保模型已进入 `embedding_models` volume：

1. 临时把 `.env.production` 的 `EMBEDDING_ALLOW_DOWNLOAD=true`。
2. 启动一次容器，让服务下载模型。
3. 停机后改回 `false` 并重启。
4. 或在构建镜像时预置模型缓存。

## MoneyPrinterTurbo

云上不要使用 `http://127.0.0.1:8080/api/v1`，除非 MoneyPrinterTurbo 和 backend 在同一个容器内。推荐：

- 单独部署 MoneyPrinterTurbo 容器或服务。
- 设置 `MONEY_PRINTER_API_BASE_URL=http://moneyprinter:8080/api/v1` 或真实内网地址。
- 确认生成的视频文件能通过 MoneyPrinterTurbo API 返回为 backend 可下载的 URL，或将 `MONEY_PRINTER_PROJECT_DIR` 挂载到 backend 可访问路径，否则企微无法自动发送本地视频产物。

## 回滚

```bash
cd /opt/homeai
git log --oneline -5
git checkout <last-good-commit>
bash scripts/deploy-cloud.sh
```

如果数据库 migration 已执行，回滚代码前必须确认对应 migration 是否向后兼容。

## 仍需接入的生产能力

- 云厂商基础监控和告警：CPU、内存、磁盘、Docker 服务状态。
- Docker daemon 开机自启：`systemctl enable docker`。
- 日志采集和告警。生产 compose 已配置 Docker `json-file` 日志轮转。
- 资源监控，尤其是 embedding、Docling、PDF 解析的 CPU 和内存。
- 如果需要多个 backend 实例横向扩容，不建议多个实例同时写本地 Chroma 目录，应迁到独立向量数据库服务。
