from __future__ import annotations

import re

from backend.app.api.schemas import DesignRequirementRequest, LeadScoreRequest, PromoCopyRequest
from backend.app.models.domain import PromoTemplate


def parse_promo_content(content: str, fallback_title: str) -> dict:
    text = (content or "").strip()
    lines = [line.strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    title = fallback_title.strip() or "推广文案"
    section = ""
    title_candidates: list[str] = []
    body_lines: list[str] = []
    heading_pattern = re.compile(r"标题|正文|标签|发布建议|素材|CTA|行动", re.I)

    for line in non_empty:
        heading = re.sub(r"^[#>*\-\s]+", "", line).strip("：: ")
        if heading_pattern.search(heading) and len(heading) <= 30:
            section = heading
            continue
        cleaned = re.sub(r"^\d+[.、]\s*", "", line).strip()
        cleaned = re.sub(r"^[#>*\-\s]+", "", cleaned).strip()
        if "标题" in section and cleaned:
            title_candidates.append(cleaned)
            continue
        if any(key in section for key in ("正文", "CTA", "行动")):
            body_lines.append(line)

    if title_candidates:
        title = title_candidates[0][:120]
    else:
        for index, line in enumerate(non_empty):
            cleaned = re.sub(r"^\d+[.、]\s*", "", line).strip()
            cleaned = re.sub(r"^[#>*\-\s]+", "", cleaned).strip()
            if heading_pattern.search(cleaned):
                continue
            if cleaned and len(cleaned) <= 100 and not cleaned.startswith("#"):
                title = cleaned
                body_lines = non_empty[index + 1 :] or non_empty
                break

    tags = []
    for match in re.finditer(r"#([^\s#，。；;]+)", text):
        tag = match.group(1).strip()
        if tag and tag not in tags:
            tags.append(tag)
    body = "\n".join(body_lines).strip() or text
    return {"title": title[:120], "body": body, "tags": tags[:12], "preview": body[:180]}


def score_lead(req: LeadScoreRequest) -> dict:
    text = req.content.strip()
    normalized = text.lower()
    inferred_budget = req.budget or extract_number(text, ["万", "预算"])
    inferred_area = req.area or extract_number(text, ["平", "㎡", "平方"])
    inferred_style = req.style or pick_first(text, ["现代简约", "新中式", "奶油风", "原木风", "轻奢", "北欧", "法式", "侘寂", "极简"])
    inferred_timeline = req.timeline or pick_first(text, ["本月", "下周", "近期", "年底", "年前", "马上", "三个月内"])
    score = 20
    signals: list[str] = []
    risks: list[str] = []

    if inferred_budget and inferred_budget > 0:
        score += 18
        signals.append(f"已提供预算：{inferred_budget:g}万")
    if inferred_area and inferred_area > 0:
        score += 14
        signals.append(f"已提供面积：{inferred_area:g}平")
    if inferred_style:
        score += 8
        signals.append(f"有风格偏好：{inferred_style}")
    if inferred_timeline:
        score += 10
        signals.append(f"有时间计划：{inferred_timeline}")
    if req.city:
        score += 5
        signals.append(f"有城市/门店线索：{req.city}")
    if req.phone:
        score += 10
        signals.append("已留联系方式")

    hot_words = ["量房", "到店", "定金", "报价", "预算", "合同", "本月", "近期", "马上", "急", "全屋", "环保", "板材"]
    soft_words = ["随便看看", "先了解", "以后", "过段时间", "不着急", "太贵", "再说"]
    matched_hot = [word for word in hot_words if word in text]
    matched_soft = [word for word in soft_words if word in text]
    if matched_hot:
        score += min(20, len(matched_hot) * 4)
        signals.append("高意向关键词：" + "、".join(matched_hot[:5]))
    if matched_soft:
        score -= min(18, len(matched_soft) * 6)
        risks.append("低意向/观望表达：" + "、".join(matched_soft[:4]))
    if any(word in normalized for word in ["竞品", "欧派", "索菲亚", "尚品宅配"]):
        score += 6
        signals.append("出现竞品对比需求，适合调用销售库中的竞品分析资料")

    score = max(0, min(100, score))
    if score >= 75:
        grade = "A"
        recommendation = "高意向客户，建议24小时内邀约到店或安排量房，并准备报价区间和案例。"
    elif score >= 55:
        grade = "B"
        recommendation = "中高意向客户，建议补齐预算、面积、风格和交付时间，再推送匹配案例。"
    else:
        grade = "C"
        recommendation = "培育型客户，先发送品牌、环保、工艺资料，降低决策门槛后再跟进。"

    next_actions = [
        "补充户型、面积、预算、所在城市和计划装修时间",
        "根据风格偏好从设计库挑选2-3个相似案例",
        "如客户提到竞品，调用销售库中的竞品分析资料准备差异化话术",
    ]
    if grade == "A":
        next_actions.insert(0, "立即邀约到店或预约量房")

    return {
        "score": score,
        "grade": grade,
        "signals": signals or ["文本信息较少，暂未识别到强意向信号"],
        "risks": risks,
        "recommendation": recommendation,
        "nextActions": next_actions,
        "extracted": {
            "budget": inferred_budget,
            "area": inferred_area,
            "style": inferred_style,
            "timeline": inferred_timeline,
            "city": req.city,
            "hasPhone": bool(req.phone),
        },
    }


def build_design_requirement_card(req: DesignRequirementRequest) -> dict:
    text = req.content.strip()
    area = req.area or extract_number(text, ["平", "㎡", "平方"])
    budget = req.budget or extract_number(text, ["万", "预算"])
    style = req.style or pick_first(text, ["现代简约", "新中式", "奶油风", "原木风", "轻奢", "北欧", "法式", "侘寂", "极简"])
    house_type = req.house_type or pick_first(text, ["三房两厅", "两房一厅", "四房两厅", "大平层", "别墅", "复式", "公寓"])
    timeline = req.timeline or pick_first(text, ["本月", "下周", "近期", "年底", "年前", "马上", "三个月内"])
    material_preferences = [word for word in ["ENF", "E0", "环保", "实木", "多层板", "颗粒板", "肤感", "耐磨", "防潮"] if word.lower() in text.lower()]
    spaces = [word for word in ["玄关", "客厅", "餐厅", "厨房", "卧室", "儿童房", "书房", "阳台", "衣帽间", "卫生间"] if word in text]
    pain_points = [word for word in ["收纳", "采光", "显大", "动线", "老人", "孩子", "宠物", "预算", "环保", "异味"] if word in text]
    missing = []
    if not area:
        missing.append("补充套内/建筑面积")
    if not house_type:
        missing.append("补充户型结构")
    if not style:
        missing.append("确认偏好风格")
    if not budget:
        missing.append("确认预算区间")
    if not timeline:
        missing.append("确认交付/开工时间")

    return {
        "customerName": req.customer_name or "待确认客户",
        "summary": text[:220],
        "area": area,
        "houseType": house_type or "待确认",
        "style": style or "待确认",
        "budget": budget,
        "timeline": timeline or "待确认",
        "materialPreferences": material_preferences or ["待确认"],
        "spaces": spaces or ["全屋"],
        "painPoints": pain_points or ["待确认"],
        "designerTodos": [
            "根据户型和面积准备2套风格方向参考",
            "输出重点空间的收纳与动线建议",
            "结合预算给出材料等级建议",
            "整理需要客户补充确认的问题",
        ],
        "missingFields": missing,
    }


def extract_number(text: str, markers: list[str]) -> float | None:
    for marker in markers:
        pattern = rf"(\d+(?:\.\d+)?)\s*{re.escape(marker)}"
        match = re.search(pattern, text, flags=re.I)
        if match:
            return float(match.group(1))
    return None


def pick_first(text: str, candidates: list[str]) -> str | None:
    return next((item for item in candidates if item in text), None)


def build_promo_prompt(req: PromoCopyRequest, template: PromoTemplate | None = None) -> str:
    points = "、".join(req.selling_points) if req.selling_points else "环保板材、全屋收纳、定制设计、售后保障"
    template_block = f"\nTemplate instruction: {template.prompt.strip()}\n" if template and template.prompt.strip() else ""
    return (
        f"{template_block}"
        f"请为家装定制品牌生成一份{req.platform}推广内容。\n"
        f"主题：{req.topic}\n"
        f"目标人群：{req.audience}\n"
        f"核心卖点：{points}\n"
        f"语气：{req.tone}\n\n"
        "输出格式必须包含：\n"
        "1. 标题：给出3个可选标题\n"
        "2. 正文：一版完整平台文案\n"
        "3. 标签：6-12个话题标签\n"
        "4. CTA：一句引导咨询、到店或预约量房的话术\n"
        "5. 发布建议：适合的图片或视频素材建议\n"
        "要求：不要夸大承诺，不要虚构价格；涉及产品、工艺、案例时优先结合知识库上下文。"
    )
