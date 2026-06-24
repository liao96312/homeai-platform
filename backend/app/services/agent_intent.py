import json
import logging
from typing import Any

from backend.app.core.config import settings
from backend.app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


AGENT_INTENT_CATEGORIES = {
    "video_generation": {
        "route": "video",
        "tool": "video_generation",
        "strong": ["视频", "短视频", "生成视频", "做视频", "剪辑", "成片", "口播视频", "产品视频", "宣传片"],
        "weak": ["分镜", "字幕", "配音", "bgm", "BGM", "素材", "脚本", "画面"],
    },
    "promo_copy": {
        "route": "promo",
        "tool": "promo_copy",
        "strong": ["小红书", "抖音", "朋友圈", "公众号", "推广", "爆款", "种草", "脚本", "发布"],
        "weak": ["文案", "标题", "标签", "素材"],
    },
    "design_requirement": {
        "route": "design",
        "tool": "requirement_card",
        "strong": ["需求卡", "户型", "设计", "风格", "效果图", "平面图", "方案", "客餐厅", "儿童房", "动线"],
        "weak": ["材料", "搭配", "收纳", "空间"],
    },
    "sales_lead": {
        "route": "sales",
        "tool": "lead_score",
        "strong": ["客户", "线索", "预算", "量房", "到店", "报价", "意向", "成交", "跟进"],
        "weak": ["面积", "电话", "城市", "本月", "近期"],
    },
}


def classify_agent_intent(text: str) -> dict[str, Any]:
    value = text.strip()
    if not value:
        return {"intent": "empty", "route": "", "tool": "", "score": 0.0, "confidence": 0.0, "classifier": "rules", "reason": "empty"}

    mode = (settings.agent_intent_classifier or "auto").lower().strip()
    if mode in {"auto", "llm"}:
        llm_plan = classify_agent_intent_with_llm(value)
        if llm_plan:
            return llm_plan
        if mode == "llm":
            logger.warning("Agent LLM intent classifier unavailable; using rules fallback")
    return classify_agent_intent_with_rules(value)


def classify_agent_intent_with_rules(value: str) -> dict[str, Any]:
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for intent, spec in AGENT_INTENT_CATEGORIES.items():
        strong_hits = [word for word in spec["strong"] if word in value]
        weak_hits = [word for word in spec["weak"] if word in value]
        scores[intent] = len(strong_hits) * 2.0 + len(weak_hits) * 0.8
        matched[intent] = strong_hits + weak_hits

    # "文案" alone is not enough to override explicit design/sales terms.
    if scores["promo_copy"] <= 0.8 and (scores["design_requirement"] > 0 or scores["sales_lead"] > 0):
        scores["promo_copy"] = 0
    priority = {"video_generation": 4, "design_requirement": 3, "sales_lead": 2, "promo_copy": 1}
    intent, score = max(scores.items(), key=lambda item: (item[1], priority[item[0]]))
    if score > 0:
        spec = AGENT_INTENT_CATEGORIES[intent]
        normalized_score = min(1.0, score / 6.0)
        return {
            "intent": intent,
            "route": spec["route"],
            "tool": spec["tool"],
            "score": round(normalized_score, 2),
            "confidence": round(normalized_score, 2),
            "classifier": "rules",
            "reason": f"rule_match:{','.join(matched[intent][:6])}",
        }
    return {"intent": "chat", "route": "chat", "tool": "chat", "score": 0.0, "confidence": 0.0, "classifier": "rules", "reason": "no_tool_intent"}


def classify_agent_intent_with_llm(value: str) -> dict[str, Any] | None:
    try:
        provider = get_llm_provider()
        if not provider.available():
            return None
        allowed_intents = {
            "sales_lead": ("sales", "lead_score"),
            "design_requirement": ("design", "requirement_card"),
            "promo_copy": ("promo", "promo_copy"),
            "video_generation": ("video", "video_generation"),
            "chat": ("chat", "chat"),
        }
        prompt = (
            "你是家装定制行业 AI Agent 的意图路由器。只输出 JSON，不要输出解释。\n"
            "可选 intent：sales_lead, design_requirement, promo_copy, video_generation, chat。\n"
            "分类原则：\n"
            "1. 视频/短视频/成片/剪辑/宣传片 → video_generation。\n"
            "2. 小红书/抖音/朋友圈/公众号/推广文案/爆款脚本 → promo_copy。\n"
            "3. 户型/设计/方案/风格/空间/效果图/需求整理 → design_requirement。\n"
            "4. 客户线索/预算/报价/量房/到店/成交/跟进 → sales_lead。\n"
            "5. 其他闲聊、知识库问答或无法判断 → chat。\n"
            "返回格式：{\"intent\":\"...\",\"confidence\":0到1,\"reason\":\"不超过30字\"}"
        )
        response = provider.chat_completion(
            {
                "model": settings.deepseek_default_model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": value[:1200]},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=min(settings.ai_request_timeout_seconds, 12),
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        data = json.loads(content)
        intent = str(data.get("intent") or "chat").strip()
        if intent not in allowed_intents:
            intent = "chat"
        route, tool = allowed_intents[intent]
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
        return {
            "intent": intent,
            "route": route,
            "tool": tool,
            "score": round(confidence, 2),
            "confidence": round(confidence, 2),
            "classifier": "llm",
            "reason": str(data.get("reason") or "llm_classified")[:120],
        }
    except Exception:
        logger.warning("Agent LLM intent classification failed", exc_info=True)
        return None

