# 企业微信长连接机器人接入

本项目把企业微信长连接拆成两层：

1. Node sidecar 使用官方 `@wecom/aibot-node-sdk` 建立 WebSocket 长连接。
2. FastAPI 暴露 `/api/wecom/long-connection/inbound`，接收标准化文本消息并调用统一 Agent Runtime。

这样后端业务编排不依赖 Node SDK，后续更换适配层或接 OpenClaw 也不会影响 RAG、工具调用和人工接管逻辑。

## 环境变量

```env
WECOM_LONG_CONNECTION_ENABLED=true
WECOM_BOT_ID=your-bot-id
WECOM_BOT_SECRET=your-bot-secret
WECOM_LONG_CONNECTION_URL=wss://openws.work.weixin.qq.com
WECOM_INTERNAL_TOKEN=replace-with-random-token
PINAI_API_BASE=http://127.0.0.1:8000
```

`WECOM_INTERNAL_TOKEN` 用于 sidecar 调后端时的 `X-PinAI-Wecom-Token` 请求头。生产环境启用长连接时必须配置。

## 启动

```powershell
npm run install:wecom
npm run api
npm run wecom:long
```

`npm run wecom:long` 会监听企微文本消息，先用流式回复发送“正在处理”，再把消息投递给 FastAPI。FastAPI 会调用 `run_agent(..., channel="wecom")`，执行意图分流、业务工具/RAG/LLM、失败重试和人工接管记录，并把最终回复返回给 sidecar。

## 后端接口

- `GET /api/wecom/long-connection/status`：管理员查看长连接配置状态。
- `POST /api/wecom/long-connection/inbound`：sidecar 标准入站接口。
- `GET|POST /wecom/callback`：保留原 webhook callback，仍复用同一套 Agent 编排。

入站请求示例：

```json
{
  "msg_type": "text",
  "content": "客户预算25万，120平新中式全屋定制，本月量房，帮我判断下一步",
  "from_user": "zhangsan",
  "conversation_id": "zhangsan",
  "message_id": "msg-001",
  "raw": {}
}
```
