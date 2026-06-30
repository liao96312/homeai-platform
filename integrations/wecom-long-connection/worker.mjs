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
const apiBase = (process.env.HOMEAI_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '');
const internalToken = process.env.WECOM_INTERNAL_TOKEN || '';
const healthPort = Number(process.env.WECOM_HEALTH_PORT || 8787);
const materialMaxBytes = Number(process.env.VIDEO_MATERIAL_MAX_UPLOAD_BYTES || 300 * 1024 * 1024);
const clipMaxMaterials = Number(process.env.WECOM_CLIP_MAX_MATERIALS || 20);
const clipMaxTotalBytes = Number(process.env.WECOM_CLIP_MAX_TOTAL_BYTES || materialMaxBytes);
const clipSessionTtlMs = Number(process.env.WECOM_CLIP_SESSION_TTL_MS || 2 * 60 * 60 * 1000);

if (!botId || !secret) {
  throw new Error('WECOM_BOT_ID and WECOM_BOT_SECRET are required');
}

const wsClient = new AiBot.WSClient({
  botId,
  secret,
  wsUrl: process.env.WECOM_LONG_CONNECTION_URL || undefined
});
const clipSessions = new Map();

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
  return { 'X-HomeAI-Wecom-Token': internalToken };
}

async function callBackend(pathname, options = {}) {
  const url = `${apiBase}${pathname}`;
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...internalHeadersFor(url),
      ...(options.headers || {})
    }
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`HomeAI backend returned ${res.status}: ${detail}`);
  }
  return res.json();
}

function sessionKey(frame) {
  return String(frameConversationId(frame) || frame.body?.from?.userid || frame.body?.from_user || 'wecom-user');
}

function sessionFor(frame) {
  const key = sessionKey(frame);
  if (!clipSessions.has(key)) clipSessions.set(key, { mode: '', materials: [], materialBytes: 0, createdAt: Date.now() });
  return clipSessions.get(key);
}

function resetSession(frame) {
  clipSessions.delete(sessionKey(frame));
}

async function cleanupMaterials(materials = []) {
  const files = [...new Set((materials || []).filter(Boolean))];
  if (!files.length) return;
  try {
    const result = await callBackend('/api/wecom/video-materials/cleanup', {
      method: 'POST',
      body: JSON.stringify({ files })
    });
    console.log(
      `[wecom-long-connection] material cleanup deleted=${(result.deleted || []).length} skipped=${(result.skipped || []).length}`
    );
  } catch (err) {
    console.error('[wecom-long-connection] material cleanup failed', err);
  }
}

async function clearSession(frame) {
  const session = sessionFor(frame);
  await cleanupMaterials(session.materials);
  resetSession(frame);
}

setInterval(() => {
  const now = Date.now();
  for (const [key, session] of clipSessions.entries()) {
    if (clipSessionTtlMs > 0 && now - (session.createdAt || now) > clipSessionTtlMs) {
      clipSessions.delete(key);
      cleanupMaterials(session.materials);
    }
  }
}, Math.min(Math.max(60_000, clipSessionTtlMs || 60_000), 10 * 60_000));

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / 1024 / 1024)}MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

function clipSessionStatusText(session) {
  const modeText = session.mode === 'with_materials' ? '有素材剪辑' : session.mode === 'without_materials' ? '无素材剪辑' : '未选择';
  const materialCount = session.materials.length;
  const remainingCount = clipMaxMaterials > 0 ? Math.max(0, clipMaxMaterials - materialCount) : '不限';
  const totalBytes = session.materialBytes || 0;
  const remainingBytes = clipMaxTotalBytes > 0 ? formatBytes(Math.max(0, clipMaxTotalBytes - totalBytes)) : '不限';
  return [
    `当前剪辑模式：${modeText}`,
    `已收素材：${materialCount} 个 / ${formatBytes(totalBytes)}`,
    `剩余额度：${remainingCount} 个 / ${remainingBytes}`,
    materialCount ? `素材：${session.materials.join('、')}` : '素材：暂无',
    '发送剪辑要求即可开始生成；发送“取消剪辑”可清空。'
  ].join('\n');
}

async function sendClipModeCard(frame) {
  const chatid = frameConversationId(frame);
  if (!chatid) return;
  await wsClient.sendMessage(String(chatid), {
    msgtype: 'template_card',
    template_card: {
      card_type: 'button_interaction',
      main_title: { title: '视频剪辑', desc: '选择是否使用你上传的素材' },
      button_list: [
        { text: '有素材剪辑', key: 'clip_with_materials', style: 1 },
        { text: '无素材剪辑', key: 'clip_without_materials', style: 2 }
      ],
      task_id: `clip_${Date.now()}`
    }
  });
}

async function callAgent(frame, videoMaterials = []) {
  const body = frame.body || {};
  const session = sessionFor(frame);
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
      force_video: session.mode === 'with_materials' || session.mode === 'without_materials',
      video_materials: videoMaterials,
      raw: body
    })
  });
}

function isClipSessionActive(session) {
  return session.mode === 'with_materials' || session.mode === 'without_materials';
}

async function uploadMaterialToBackend(filename, buffer) {
  const form = new FormData();
  form.append('file', new Blob([buffer]), filename || `material-${Date.now()}`);
  return callBackend('/api/wecom/video-materials', { method: 'POST', body: form });
}

async function storeFrameMaterial(frame, kind) {
  const body = frame.body || {};
  const item = body[kind] || {};
  const url = item.url;
  if (!url) throw new Error('素材下载地址为空');
  const downloaded = await wsClient.downloadFile(url, item.aeskey);
  const size = downloaded.buffer?.length || 0;
  if (materialMaxBytes > 0 && size > materialMaxBytes) {
    throw new Error(`素材过大：${formatBytes(size)}，当前限制 ${formatBytes(materialMaxBytes)}`);
  }
  const filename = downloaded.filename || `${kind}-${Date.now()}`;
  const session = sessionFor(frame);
  if (clipMaxMaterials > 0 && session.materials.length >= clipMaxMaterials) {
    throw new Error(`当前会话素材数量已达上限：${clipMaxMaterials} 个。请发送剪辑要求，或发送“取消剪辑”清空后重来。`);
  }
  const nextTotal = (session.materialBytes || 0) + size;
  if (clipMaxTotalBytes > 0 && nextTotal > clipMaxTotalBytes) {
    throw new Error(`当前会话素材总大小超限：${formatBytes(nextTotal)}，当前限制 ${formatBytes(clipMaxTotalBytes)}。请发送剪辑要求，或发送“取消剪辑”清空后重来。`);
  }
  const uploaded = await uploadMaterialToBackend(filename, downloaded.buffer);
  session.mode = 'with_materials';
  session.materials.push(uploaded.file);
  session.materialBytes = nextTotal;
  await sendMarkdown(frame, `已收到素材：${uploaded.file}\n当前素材数：${session.materials.length}\n请继续上传素材，或直接发送剪辑要求。`);
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

async function waitAndDeliverVideo(frame, videoDelivery, materialsToCleanup = []) {
  const taskId = videoDelivery?.taskId;
  if (!taskId) return;

  const pollIntervalSeconds = Number(videoDelivery.pollIntervalSeconds || process.env.VIDEO_GENERATION_POLL_INTERVAL_SECONDS || 15);
  const pollTimeoutSeconds = Number(videoDelivery.pollTimeoutSeconds || process.env.VIDEO_GENERATION_POLL_TIMEOUT_SECONDS || 900);
  const deadline = Date.now() + Math.max(30, pollTimeoutSeconds) * 1000;
  let lastProgress = -1;

  while (Date.now() < deadline) {
    const delivery = await fetchVideoDelivery(taskId);
    if (delivery.ready) {
      try {
        await sendVideoToWecom(frame, delivery);
      } catch (err) {
        await sendMarkdown(frame, `视频已生成，但发送到企微失败：${err.message || 'unknown error'}\n请在平台视频任务里下载。`);
      }
      await cleanupMaterials(materialsToCleanup);
      return;
    }
    if (delivery.failed) {
      await sendMarkdown(frame, `视频生成失败：${taskId}`);
      await cleanupMaterials(materialsToCleanup);
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
  const streamId = generateReqId('homeai');
  try {
    const text = (frame.body?.text?.content || '').trim();
    if (['取消剪辑', '重置剪辑'].includes(text)) {
      await clearSession(frame);
      await wsClient.replyStream(frame, streamId, '已取消当前剪辑任务。', true);
      return;
    }
    if (['当前素材', '素材状态', '查看素材'].includes(text)) {
      await wsClient.replyStream(frame, streamId, clipSessionStatusText(sessionFor(frame)), true);
      return;
    }
    if (['剪辑', '视频剪辑', '做视频', '生成视频'].includes(text)) {
      await sendClipModeCard(frame);
      return;
    }
    const session = sessionFor(frame);
    if (session.mode === 'with_materials' && session.materials.length === 0) {
      await wsClient.replyStream(frame, streamId, '请先上传图片/视频素材，再发送剪辑要求。发送“取消剪辑”可退出当前模式。', true);
      return;
    }
    await wsClient.replyStream(frame, streamId, '正在处理，请稍候...', false);
    const materialsForTask = session.mode === 'with_materials' ? [...session.materials] : [];
    const result = await callAgent(frame, materialsForTask);
    await wsClient.replyStream(frame, streamId, result.reply || '已收到，但没有生成回复。', true);
    if (result.videoDelivery?.taskId) resetSession(frame);
    if (result.videoDelivery?.taskId) {
      waitAndDeliverVideo(frame, result.videoDelivery, materialsForTask).catch((err) => {
        console.error('[wecom-long-connection] video delivery failed', err);
      });
    }
  } catch (err) {
    console.error('[wecom-long-connection] message failed', err);
    const session = sessionFor(frame);
    const retryHint = isClipSessionActive(session)
      ? '\n当前剪辑素材仍保留，可修改要求后重试；发送“取消剪辑”可清空素材。'
      : '';
    await wsClient.replyStream(frame, streamId, `处理失败：${err.message || 'unknown error'}${retryHint}`, true);
  }
});

for (const kind of ['image', 'file', 'video']) {
  wsClient.on(`message.${kind}`, async (frame) => {
    try {
      await storeFrameMaterial(frame, kind);
    } catch (err) {
      console.error('[wecom-long-connection] material upload failed', err);
      await sendMarkdown(frame, `素材上传失败：${err.message || 'unknown error'}`);
    }
  });
}

wsClient.on('event.template_card_event', async (frame) => {
  const key = frame.body?.event?.event_key || '';
  const taskId = frame.body?.event?.task_id || `clip_${Date.now()}`;
  const session = sessionFor(frame);
  if (key === 'clip_with_materials') {
    const oldMaterials = [...session.materials];
    session.mode = 'with_materials';
    session.materials = [];
    session.materialBytes = 0;
    session.createdAt = Date.now();
    await wsClient.updateTemplateCard(frame, {
      card_type: 'text_notice',
      main_title: { title: '已选择：有素材剪辑', desc: '请上传图片/视频素材，然后发送自然语言剪辑要求。' },
      task_id: taskId
    });
    cleanupMaterials(oldMaterials);
  }
  if (key === 'clip_without_materials') {
    const oldMaterials = [...session.materials];
    session.mode = 'without_materials';
    session.materials = [];
    session.materialBytes = 0;
    session.createdAt = Date.now();
    await wsClient.updateTemplateCard(frame, {
      card_type: 'text_notice',
      main_title: { title: '已选择：无素材剪辑', desc: '请直接发送自然语言视频要求。' },
      task_id: taskId
    });
    cleanupMaterials(oldMaterials);
  }
});

wsClient.on('error', (err) => {
  console.error('[wecom-long-connection] socket error', err);
});

wsClient.connect();
