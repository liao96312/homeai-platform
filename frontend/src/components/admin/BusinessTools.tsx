import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import AgentDispatchCard from './business/AgentDispatchCard';
import ArtifactHistory from './business/ArtifactHistory';
import DesignRequirementCard from './business/DesignRequirementCard';
import LeadScoringTool from './business/LeadScoringTool';
import PromoCopyCard from './business/PromoCopyCard';
import VideoGenerationCard from './business/VideoGenerationCard';

export default function BusinessTools({ currentRole, setToast }) {
  const [dispatchText, setDispatchText] = useState('客户120平三房两厅，想做新中式全屋定制，预算25万，本月量房，请判断意向并给下一步动作。');
  const [dispatchResult, setDispatchResult] = useState<any | null>(null);
  const [promo, setPromo] = useState({
    platform: '小红书',
    topic: '新中式全屋定制环保板材',
    audience: '准备装修、关注环保和收纳的家庭',
    selling_points: 'ENF环保板材,全屋收纳规划,设计师一对一方案',
    tone: '真实、有生活感、有转化力'
  });
  const [promoResult, setPromoResult] = useState<any | null>(null);
  const [promoTemplates, setPromoTemplates] = useState<any[]>([]);
  const [promoTemplateId, setPromoTemplateId] = useState('');
  const [video, setVideo] = useState({
    platform: '抖音',
    subject: '新中式全屋定制产品宣传短视频',
    script: ''
  });
  const [videoResult, setVideoResult] = useState<any | null>(null);
  const [videoTaskResult, setVideoTaskResult] = useState<any | null>(null);
  const [designText, setDesignText] = useState('客户王女士，120平三房两厅，喜欢新中式，预算25万，重点关注客厅收纳、儿童房环保和厨房动线，本月想确认方案。');
  const [designCard, setDesignCard] = useState<any | null>(null);
  const [designAssignees, setDesignAssignees] = useState<any[]>([]);
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, any>>({});
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [artifactFilter, setArtifactFilter] = useState('');
  const [busy, setBusy] = useState('');
  const canSales = currentRole === 'admin' || ['sales', 'sales_director'].includes(currentRole);
  const canPromo = currentRole === 'admin' || ['promo', 'promo_manager'].includes(currentRole);
  const canDesign = currentRole === 'admin' || ['designer', 'design_manager'].includes(currentRole);

  const loadArtifacts = useCallback(async (type = artifactFilter) => {
    try {
      const res = await api.listArtifacts(type);
      setArtifacts(res.artifacts || []);
    } catch (err) {
      setToast?.(err.message);
    }
  }, [artifactFilter, setToast]);

  const loadPromoTemplates = useCallback(async () => {
    try {
      const res = await api.listPromoTemplates();
      setPromoTemplates(res.templates || []);
    } catch (err) {
      setToast?.(err.message);
    }
  }, [setToast]);

  const loadDesignAssignees = useCallback(async () => {
    try {
      const res = await api.listDesignAssignees();
      setDesignAssignees(res.assignees || []);
    } catch (err) {
      setToast?.(err.message);
    }
  }, [setToast]);

  useEffect(() => {
    loadArtifacts(artifactFilter);
  }, [artifactFilter, loadArtifacts]);

  useEffect(() => {
    if (canPromo) loadPromoTemplates();
  }, [canPromo, loadPromoTemplates]);

  useEffect(() => {
    if (canDesign) loadDesignAssignees();
  }, [canDesign, loadDesignAssignees]);

  function applyPromoTemplate(templateId) {
    setPromoTemplateId(templateId);
    const template = promoTemplates.find((item) => String(item.id) === String(templateId));
    if (!template) return;
    setPromo((prev) => ({
      ...prev,
      platform: template.platform || prev.platform,
      audience: template.defaultAudience || prev.audience,
      selling_points: (template.defaultSellingPoints || []).join(',') || prev.selling_points,
      tone: template.defaultTone || prev.tone
    }));
  }

  async function runDispatch() {
    if (!dispatchText.trim()) {
      setToast?.('请输入要分流的业务问题');
      return;
    }
    setBusy('dispatch');
    try {
      const res = await api.dispatchAgent({ message: dispatchText });
      setDispatchResult(res);
      setToast?.('已分流到 ' + res.route + ' / ' + res.tool);
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function runPromo(e) {
    e.preventDefault();
    if (!promo.platform.trim() || !promo.topic.trim()) {
      setToast?.('请填写平台和主题');
      return;
    }
    setBusy('promo');
    try {
      const res = await api.generatePromoCopy({
        ...promo,
        template_id: promoTemplateId ? Number(promoTemplateId) : null,
        selling_points: promo.selling_points.split(',').map((item) => item.trim()).filter(Boolean)
      });
      setPromoResult(res);
      setToast?.('推广文案已生成');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function runDesign() {
    if (!designText.trim()) {
      setToast?.('请输入客户需求内容');
      return;
    }
    setBusy('design');
    try {
      const res = await api.createDesignCard({ content: designText });
      setDesignCard(res);
      setToast?.('设计需求卡已生成');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  function updateAssignmentDraft(artifactId, patch) {
    setAssignmentDrafts((prev) => ({
      ...prev,
      [artifactId]: { ...(prev[artifactId] || {}), ...patch }
    }));
  }

  async function assignDesignCard(artifactId, defaultDesignerId = '') {
    const draft = assignmentDrafts[artifactId] || {};
    const designerId = draft.designerId || defaultDesignerId;
    if (!designerId) {
      setToast?.('请选择设计师');
      return;
    }
    setBusy('assign-' + artifactId);
    try {
      const updated = await api.assignDesignCard(artifactId, {
        designer_id: Number(designerId),
        notes: draft.notes || '',
        status: 'confirmed'
      });
      setDesignCard((prev) => (prev?.artifactId === artifactId ? { ...prev, assignment: updated.assignment } : prev));
      setToast?.('设计需求卡已分配');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function copyPromo() {
    if (!promoResult) return;
    const text = (promoResult.title || promoResult.topic) + '\n\n' + (promoResult.body || promoResult.content);
    if (!text.trim()) {
      setToast?.('暂无可复制的文案');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setToast?.('文案已复制');
    } catch {
      setToast?.('复制失败，请手动选择文案');
    }
  }

  async function publishPromo() {
    if (!promoResult) return;
    const title = promoResult.title || promoResult.topic;
    const content = promoResult.body || promoResult.content;
    const platform = promoResult.platform || promo.platform;
    if (!title?.trim() || !content?.trim() || !platform?.trim()) {
      setToast?.('发布任务缺少标题、正文或平台');
      return;
    }
    setBusy('promo-publish');
    try {
      const res = await api.createPublishJobs({
        artifact_id: promoResult.artifactId,
        title,
        content,
        platforms: [platform],
        source: 'admin-tools',
        tags: promoResult.tags || []
      });
      const status = res.jobs?.[0]?.status;
      setPromoResult((prev) => ({ ...prev, publishJobs: res.jobs || [] }));
      setToast?.(status === 'needs_config' ? '发布任务已创建，配置 MultiPost 后可真实发布' : '发布任务已提交');
      if (res.requiresReview) setToast?.('发布前需要人工确认，已进入待审核');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function runVideo(e) {
    e.preventDefault();
    if (!video.subject.trim()) {
      setToast?.('请输入视频主题');
      return;
    }
    setBusy('video');
    setVideoTaskResult(null);
    try {
      const res = await api.generateVideo(video);
      setVideoResult(res);
      setToast?.('视频生成任务已提交');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function refreshVideoTask() {
    if (!videoResult?.taskId) return;
    setBusy('video-status');
    try {
      const res = await api.getVideoDelivery(videoResult.taskId);
      setVideoTaskResult(res);
      setToast?.('视频任务状态已刷新');
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function publishVideo() {
    const fileUrl = videoTaskResult?.selectedFile?.downloadUrl;
    if (!fileUrl) {
      setToast?.('请先刷新到可下载的视频文件');
      return;
    }
    setBusy('video-publish');
    try {
      const res = await api.createPublishJobs({
        artifact_id: videoResult?.artifactId,
        title: video.subject,
        content: video.script || video.subject,
        platforms: [video.platform || '抖音'],
        source: 'video-generation',
        videos: [fileUrl]
      });
      setVideoTaskResult((prev) => ({ ...prev, publishJobs: res.jobs || [] }));
      const status = res.jobs?.[0]?.status;
      setToast?.(status === 'needs_config' ? '视频发布任务已创建，配置 MultiPost 后可真实发布' : '视频发布任务已提交');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function updateArtifactStatus(id, status) {
    setBusy('artifact-' + id);
    try {
      await api.updateArtifact(id, { status });
      setToast?.('业务产物状态已更新');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  async function removeArtifact(id, title) {
    if (!confirm(`确定删除“${title}”？`)) return;
    setBusy('artifact-' + id);
    try {
      await api.deleteArtifact(id);
      setToast?.('业务产物已删除');
      await loadArtifacts(artifactFilter);
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="tools-grid">
      <AgentDispatchCard
        dispatchText={dispatchText}
        setDispatchText={setDispatchText}
        dispatchResult={dispatchResult}
        runDispatch={runDispatch}
        busy={busy}
      />

      {canSales && <LeadScoringTool setToast={setToast} />}

      <PromoCopyCard
        canPromo={canPromo}
        promo={promo}
        setPromo={setPromo}
        promoTemplates={promoTemplates}
        promoTemplateId={promoTemplateId}
        applyPromoTemplate={applyPromoTemplate}
        runPromo={runPromo}
        promoResult={promoResult}
        copyPromo={copyPromo}
        publishPromo={publishPromo}
        busy={busy}
      />

      <VideoGenerationCard
        canPromo={canPromo}
        video={video}
        setVideo={setVideo}
        runVideo={runVideo}
        videoResult={videoResult}
        videoTaskResult={videoTaskResult}
        refreshVideoTask={refreshVideoTask}
        publishVideo={publishVideo}
        busy={busy}
      />

      <DesignRequirementCard
        canDesign={canDesign}
        designText={designText}
        setDesignText={setDesignText}
        runDesign={runDesign}
        designCard={designCard}
        designAssignees={designAssignees}
        assignmentDrafts={assignmentDrafts}
        updateAssignmentDraft={updateAssignmentDraft}
        assignDesignCard={assignDesignCard}
        busy={busy}
      />

      <ArtifactHistory
        artifacts={artifacts}
        artifactFilter={artifactFilter}
        setArtifactFilter={setArtifactFilter}
        loadArtifacts={loadArtifacts}
        designAssignees={designAssignees}
        assignmentDrafts={assignmentDrafts}
        updateAssignmentDraft={updateAssignmentDraft}
        assignDesignCard={assignDesignCard}
        updateArtifactStatus={updateArtifactStatus}
        removeArtifact={removeArtifact}
        busy={busy}
      />
    </div>
  );
}




