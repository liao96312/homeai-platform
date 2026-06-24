import AiBot, { generateReqId } from '@wecom/aibot-node-sdk';
import dotenv from 'dotenv';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function loadProjectEnv() {
  const currentDir = path.dirname(fileURLToPath(import.meta.url));
  const envPath = path.resolve(currentDir, '../../.env');
  if (!fs.existsSync(envPath)) return;
  dotenv.config({ path: envPath, override: false });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

loadProjectEnv();

const botId = process.env.WECOM_BOT_ID || '';
const secret = process.env.WECOM_BOT_SECRET || '';
const apiBase = (process.env.PINAI_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '');
const internalToken = process.env.WECOM_INTERNAL_TOKEN || '';
const healthPort = Number(process.env.WECOM_HEALTH_PORT || 8787);

if (!botId || !secret) {
  throw new Error('WECOM_BOT_ID and WECOM_BOT_SECRET are required');
}

const wsClient = new AiBot.WSClient({
  botId,
  secret,
  wsUrl: process.env.WECOM_LONG_CONNECTION_URL || undefined
});

http
  .createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ status: 'ok', service: 'wecom-long-connection' }));
  })
  .listen(healthPort, '0.0.0.0', () => {
    console.log(`[wecom-long] health endpoint listening on :${healthPort}`);
  });

function isBackendUrl(url) {
  try {
    return new URL(url).origin === new URL(apiBase).origin;
  } catch {
    return false;
  }
}

function internalHeadersFor(url) {
  if (!internalToken || !isBackendUrl(url)) return {};
  return { 'X-PinAI-Wecom-Token': internalToken };
}

async function callBackend(pathname, options = {}) {
  const url = `${apiBase}${pathname}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...internalHeadersFor(url),
      ...(options.headers || {})
    }
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`PinAI backend returned ${res.status}: ${detail}`);
  }
  return res.json();
}

async function callAgent(frame) {
  const body = frame.body || {};
  const text = body.text?.content || body.content || '';
  const fromUser = body.from?.userid || body.from_user || body.sender?.userid || 'wecom-user';
  const conversationId = body.chatid || body.conversation_id || body.roomid || fromUser;
  const messageId = body.msgid || body.msg_id || body.message_id || frame.seq || '';

  return callBackend('/api/wecom/long-connection/inbound', {
    method: 'POST',
    body: JSON.stringify({
      msg_type: 'text',
      content: text,
      from_user: String(fromUser),
      conversation_id: String(conversationId),
      message_id: String(messageId),
      raw: body
    })
  });
}

async function fetchVideoDelivery(taskId) {
  return callBackend(`/api/wecom/video-tasks/${encodeURIComponent(taskId)}/delivery`);
}

async function downloadVideoBuffer(selectedFile) {
  const downloadUrl = selectedFile?.downloadUrl || selectedFile?.url;
  if (!downloadUrl) {
    throw new Error('视频下载地址为空');
  }
  const absoluteUrl = String(downloadUrl).startsWith('http')
    ? String(downloadUrl)
    : `${apiBase}${String(downloadUrl).startsWith('/') ? '' : '/'}${downloadUrl}`;
  const res = await fetch(absoluteUrl, { headers: internalHeadersFor(absoluteUrl) });
  if (!res.ok) {
    throw new Error(`视频下载失败 ${res.status}: ${await res.text()}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

function frameConversationId(frame) {
  const body = frame.body || {};
  return body.chatid || body.conversation_id || body.roomid || body.from?.userid || body.from_user || body.sender?.userid || '';
}

async function sendMarkdown(frame, content) {
  const chatid = frameConversationId(frame);
  if (!chatid) return;
  await wsClient.sendMessage(String(chatid), { msgtype: 'markdown', markdown: { content } });
}

async function sendVideoToWecom(frame, delivery) {
  const selectedFile = delivery?.selectedFile;
  if (!selectedFile) {
    throw new Error('没有可发送的视频文件');
  }
  const filename = path.basename(selectedFile.url || selectedFile.downloadUrl || `video-${delivery.taskId}.mp4`);
  const fileBuffer = await downloadVideoBuffer(selectedFile);
  const upload = await wsClient.uploadMedia(fileBuffer, { type: 'video', filename });
  const mediaId = upload.media_id || upload.mediaId;
  if (!mediaId) throw new Error('企微素材上传成功但没有返回 media_id');

  const videoOptions = {
    title: `视频生成完成：${delivery.taskId}`,
    description: filename
  };
  const chatid = frameConversationId(frame);
  if (chatid) {
    await wsClient.sendMediaMessage(String(chatid), 'video', mediaId, videoOptions);
  } else {
    await wsClient.replyMedia(frame, 'video', mediaId, videoOptions);
  }
}

async function waitAndDeliverVideo(frame, videoDelivery) {
  const taskId = videoDelivery?.taskId;
  if (!taskId) return;

  const pollIntervalSeconds = Number(videoDelivery.pollIntervalSeconds || process.env.VIDEO_GENERATION_POLL_INTERVAL_SECONDS || 15);
  const pollTimeoutSeconds = Number(videoDelivery.pollTimeoutSeconds || process.env.VIDEO_GENERATION_POLL_TIMEOUT_SECONDS || 900);
  const deadline = Date.now() + Math.max(30, pollTimeoutSeconds) * 1000;
  let lastProgress = -1;

  while (Date.now() < deadline) {
    const delivery = await fetchVideoDelivery(taskId);
    if (delivery.ready) {
      await sendVideoToWecom(frame, delivery);
      return;
    }
    if (delivery.failed) {
      await sendMarkdown(frame, `视频生成失败：${taskId}`);
      return;
    }
    if (delivery.progress !== lastProgress && frameConversationId(frame)) {
      lastProgress = delivery.progress;
      console.log(`[wecom-long-connection] video task ${taskId} progress ${delivery.progress}%`);
    }
    await sleep(Math.max(3, pollIntervalSeconds) * 1000);
  }

  await sendMarkdown(frame, `视频仍在生成中：${taskId}\n稍后可在平台视频任务里刷新状态。`);
}

wsClient.on('authenticated', () => {
  console.log('[wecom-long-connection] authenticated');
});

wsClient.on('message.text', async (frame) => {
  const streamId = generateReqId('pinai');
  try {
    await wsClient.replyStream(frame, streamId, '正在处理，请稍候...', false);
    const result = await callAgent(frame);
    await wsClient.replyStream(frame, streamId, result.reply || '已收到，但没有生成回复。', true);
    if (result.videoDelivery?.taskId) {
      waitAndDeliverVideo(frame, result.videoDelivery).catch((err) => {
        console.error('[wecom-long-connection] video delivery failed', err);
      });
    }
  } catch (err) {
    console.error('[wecom-long-connection] message failed', err);
    await wsClient.replyStream(frame, streamId, `处理失败：${err.message || 'unknown error'}`, true);
  }
});

wsClient.on('error', (err) => {
  console.error('[wecom-long-connection] socket error', err);
});

wsClient.connect();
