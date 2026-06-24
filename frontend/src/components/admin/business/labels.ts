export function artifactTypeLabel(type) {
  return {
    lead_score: '销售初筛',
    design_card: '设计需求卡',
    promo_copy: '推广文案',
    video_generation: '视频生成'
  }[type] || type;
}

export function artifactStatusLabel(status) {
  return {
    draft: '草稿',
    confirmed: '已确认',
    completed: '已完成',
    archived: '已归档'
  }[status] || status;
}

export function publishStatusLabel(status) {
  return {
    submitted: '已提交',
    scheduled: '已定时',
    pending: '等待执行',
    needs_config: '待配置',
    failed: '失败',
    completed: '已完成'
  }[status] || status;
}
