import React from 'react';
import VideoTaskPreview from './VideoTaskPreview';

export default function VideoGenerationCard({
  canPromo,
  video,
  setVideo,
  runVideo,
  videoResult,
  videoTaskResult,
  refreshVideoTask,
  busy
}) {
  return (
    <form className={'card tool-card ' + (canPromo ? '' : 'locked')} onSubmit={runVideo}>
      <div className="card-header">
        <span className="card-title">视频生成</span>
        <span className="tag tag-purple">MoneyPrinterTurbo</span>
      </div>
      <div className="tool-form-grid">
        <label className="wide">视频主题
          <input value={video.subject} disabled={!canPromo} onChange={(e) => setVideo({ ...video, subject: e.target.value })} />
        </label>
        <label className="wide">脚本
          <textarea value={video.script} disabled={!canPromo} onChange={(e) => setVideo({ ...video, script: e.target.value })} placeholder="可留空，由 MoneyPrinterTurbo 按主题生成脚本" />
        </label>
      </div>
      <button className="btn btn-primary" disabled={!canPromo || busy === 'video'} type="submit">
        {busy === 'video' ? '提交中...' : '提交视频任务'}
      </button>
      <VideoTaskPreview
        videoResult={videoResult}
        videoTaskResult={videoTaskResult}
        video={video}
        refreshVideoTask={refreshVideoTask}
        busy={busy}
      />
    </form>
  );
}



