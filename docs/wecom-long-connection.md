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
HOMEAI_API_BASE=http://127.0.0.1:8000
VIDEO_MATERIAL_MAX_UPLOAD_BYTES=314572800
WECOM_CLIP_SESSION_TTL_MS=7200000
WECOM_CLIP_MAX_MATERIALS=20
WECOM_CLIP_MAX_TOTAL_BYTES=314572800
```

`WECOM_INTERNAL_TOKEN` 用于 sidecar 调后端时的 `X-HomeAI-Wecom-Token` 请求头。生产环境启用长连接时必须配置。

`VIDEO_MATERIAL_MAX_UPLOAD_BYTES` 同时作用于 sidecar 和 backend。企微 SDK 当前会先把素材下载到 sidecar 内存，再上传给 MoneyPrinterTurbo；如果调大这个值，也要同步调大 `WECOM_MEM_LIMIT`。

`WECOM_CLIP_SESSION_TTL_MS` 是企微剪辑会话最长保留时间，默认 2 小时。用户上传素材后长时间不提交剪辑要求，sidecar 会自动清理这组素材。

`WECOM_CLIP_MAX_MATERIALS` 和 `WECOM_CLIP_MAX_TOTAL_BYTES` 控制一次剪辑会话最多收多少个素材、总大小上限。超过后素材不会上传到 MoneyPrinterTurbo，用户可以先提交剪辑要求，或发送 `取消剪辑` 清空后重来。

## 启动

```powershell
npm run install:wecom
npm run api
npm run wecom:long
```

`npm run wecom:long` 会监听企微文本消息，先用流式回复发送“正在处理”，再把消息投递给 FastAPI。FastAPI 会调用 `run_agent(..., channel="wecom")`，执行意图分流、业务工具/RAG/LLM、失败重试和人工接管记录，并把最终回复返回给 sidecar。

如果 Agent 识别为视频生成，sidecar 会按后端返回的 `videoDelivery.taskId` 轮询 `/api/wecom/video-tasks/{taskId}/delivery`。任务完成后会下载 `selectedFile.downloadUrl`，上传为企微 video 素材并发送到当前会话。发送失败时会在企微里返回失败原因，用户仍可回到平台下载视频。

## 企微视频剪辑

在企微里给机器人发送 `剪辑`、`视频剪辑`、`做视频` 或 `生成视频`，机器人会返回按钮卡片：

- `有素材剪辑`：先上传图片、视频或文件素材，再发送自然语言剪辑要求。sidecar 会把素材上传到 MoneyPrinterTurbo 的 `/video_materials`，再创建本地素材视频任务。
- `无素材剪辑`：直接发送自然语言视频要求，后端会强制走视频生成工具，不再依赖意图分类猜测。

发送 `取消剪辑` 或 `重置剪辑` 可以清空当前素材和剪辑模式。

视频任务完成后，sidecar 会把生成的 mp4 上传为企微 video 素材并发回当前会话。

素材生命周期：

- 同一个企微会话里连续上传的素材会归到同一组，下一条剪辑要求会一次性带给 MoneyPrinterTurbo。
- 默认一组最多 20 个素材，总大小不超过 300MB，可通过环境变量调整。
- 如果提交视频任务失败，素材会留在当前会话，用户可以修改要求后重试，或发送 `取消剪辑` 清空。
- 取消/重置剪辑、切换剪辑模式、视频任务完成或失败后，会清理这组素材。
- 用户上传素材后长时间没有继续操作，超过 `WECOM_CLIP_SESSION_TTL_MS` 也会清理。
- 如果轮询超时但 MoneyPrinterTurbo 任务可能仍在执行，暂不删除素材，避免后台任务还没读完文件。
- 自动清理依赖 `MONEY_PRINTER_PROJECT_DIR` 指向 MoneyPrinterTurbo 项目目录；如果 MoneyPrinterTurbo 部署在另一台机器且目录不可见，只能跳过清理。
- sidecar 会在日志里输出素材清理的 deleted/skipped 数量，方便排查磁盘占用。

视频自动发送要满足两点：

- `MONEY_PRINTER_API_BASE_URL` 对 sidecar 可访问。Docker/云服务器里不要写 `127.0.0.1`，应写同网络服务名或内网地址。
- `WECOM_INTERNAL_TOKEN` 同时配置在 backend 和 sidecar，用于访问 `/api/wecom/video-tasks/{taskId}/delivery`。

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
