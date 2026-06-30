# 视频生成和一键发布使用说明

本项目已经接入两类外部能力：

- MoneyPrinterTurbo：负责生成短视频。
- MultiPost-Extension：负责把文案、图片、视频交给浏览器扩展发布。

## 1. 启动 MoneyPrinterTurbo

在 MoneyPrinterTurbo 目录启动 API 服务：

```powershell
cd D:\workplace\MoneyPrinterTurbo
python main.py
```

本项目 `.env` 保持：

```env
MONEY_PRINTER_API_BASE_URL=http://127.0.0.1:8080/api/v1
MONEY_PRINTER_PROJECT_DIR=D:\workplace\MoneyPrinterTurbo
```

`MONEY_PRINTER_PROJECT_DIR` 用于把任务返回的文件 URL 映射成本地 mp4 路径，企微侧发送本地视频时会用到。

## 2. 提交视频生成任务

前端路径：后台 -> 业务工具 -> 视频生成。

API：

```http
POST /api/video/generate
Authorization: Bearer <token>
Content-Type: application/json

{
  "subject": "新中式全屋定制 30 秒宣传视频",
  "script": "突出环保板材、收纳设计、到店预约",
  "materials": ["living-room.mp4", "cabinet.png"]
}
```

`materials` 是 MoneyPrinterTurbo `/video_materials` 上传后返回的文件名。有素材时本项目会把 `video_source` 设置为 `local`，让 MoneyPrinterTurbo 直接使用本地素材剪辑。

返回里的 `taskId` 用于查询进度：

```http
GET /api/video/tasks/{taskId}/delivery
```

当 `ready=true` 时，取 `selectedFile.downloadUrl` 或 `selectedFile.localPath`。

## 3. 配置 MultiPost-Extension

`.env`：

```env
MULTIPOST_API_BASE_URL=https://api.multipost.app
MULTIPOST_API_KEY=<你的 MultiPost key>
MULTIPOST_TARGET_CLIENT_ID=<浏览器扩展 client id>
MULTIPOST_AUTO_PUBLISH=false
```

`MULTIPOST_AUTO_PUBLISH=false` 更适合演示和企业内网：先创建发布任务，再由浏览器登录态人工确认。

当前管理台只创建即时发布任务。`publish_jobs.scheduled_at` 保留为接口兼容字段，但没有后台执行器，不在前端展示定时发布。

## 4. 发布文案或视频

只发文案：

```http
POST /api/publish/jobs
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "新中式全屋定制怎么选",
  "content": "环保、收纳、预算都要提前规划。",
  "platforms": ["小红书", "抖音"],
  "tags": ["全屋定制", "家装"]
}
```

带视频发布：

```http
POST /api/publish/jobs
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "新中式全屋定制宣传片",
  "content": "30 秒看懂全屋定制方案。",
  "platforms": ["抖音"],
  "videos": ["http://127.0.0.1:8080/storage/tasks/<taskId>/final.mp4"],
  "tags": ["全屋定制", "装修"]
}
```

## 5. 当前边界

- 本项目不负责平台登录，登录态由 MultiPost-Extension 所在浏览器维护。
- 本项目不自研剪辑引擎，视频生成交给 MoneyPrinterTurbo。
- 云服务器部署时，MoneyPrinterTurbo 需要和 backend 网络互通；如果要发送本地文件，两个服务还要能访问同一份任务产物目录。
