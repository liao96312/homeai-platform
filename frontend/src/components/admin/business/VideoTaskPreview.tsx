import React from 'react';
import { publishStatusLabel } from './labels';

export default function VideoTaskPreview({ videoResult, videoTaskResult, video, refreshVideoTask, publishVideo, busy }) {
  if (!videoResult) return null;
  const selectedFile = videoTaskResult?.selectedFile;
  const files = videoTaskResult?.files || [];
  const progress = Number(videoTaskResult?.progress || 0);
  const taskStatus = videoTaskResult?.failed ? '失败' : videoTaskResult?.completed ? '完成' : videoTaskResult ? `处理中 ${progress}%` : videoResult.status;

  return (
    <div className="promo-preview">
      <div className="promo-preview-meta">
        <span>{videoResult.provider}</span>
        <span>{taskStatus}</span>
      </div>
      <h3>{videoResult.request?.video_subject || video.subject}</h3>
      <div className="promo-preview-body">
        <span>任务 ID：{videoResult.taskId || '未返回'}</span><br />
        <span>查询地址：{videoResult.statusUrl || '暂无'}</span><br />
        {videoTaskResult && <span>进度：{progress}%</span>}<br />
        {selectedFile?.downloadUrl && <a href={selectedFile.downloadUrl} target="_blank" rel="noreferrer">打开生成视频</a>}
        {!selectedFile?.downloadUrl && videoTaskResult?.completed && <span>任务已完成，但未返回可下载视频文件</span>}
      </div>
      {files.length > 0 && (
        <div className="publish-result compact">
          {files.map((file, index) => (
            <div className="publish-job publish-completed" key={file.downloadUrl || file.url || index}>
              <b>视频文件 {index + 1}</b>
              {file.downloadUrl ? <a href={file.downloadUrl} target="_blank" rel="noreferrer">下载/预览</a> : <span>无下载地址</span>}
              {file.localPath && <small>{file.localPath}</small>}
            </div>
          ))}
        </div>
      )}
      {videoTaskResult?.publishJobs?.length > 0 && (
        <div className="publish-result compact">
          {videoTaskResult.publishJobs.map((job) => (
            <div className={'publish-job publish-' + job.status} key={job.id}>
              <b>{job.platform}</b>
              <span>{publishStatusLabel(job.status)}</span>
              {job.error && <small>{job.error}</small>}
            </div>
          ))}
        </div>
      )}
      <div className="promo-preview-actions">
        <button className="btn btn-default" type="button" disabled={!videoResult.taskId || busy === 'video-status'} onClick={refreshVideoTask}>
          {busy === 'video-status' ? '查询中...' : '刷新任务状态'}
        </button>
        <button className="btn btn-primary" type="button" disabled={!selectedFile?.downloadUrl || busy === 'video-publish'} onClick={publishVideo}>
          {busy === 'video-publish' ? '发布中...' : '创建视频发布任务'}
        </button>
      </div>
      {videoTaskResult && (
        <details>
          <summary>查看原始状态</summary>
          <pre className="tool-output">{JSON.stringify(videoTaskResult, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
