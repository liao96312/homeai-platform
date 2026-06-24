import json
import logging
import re
import time
from typing import Any

from backend.app.core.config import settings
from backend.app.services.embeddings import tokenize
from backend.app.services.llm import get_llm_provider


logger = logging.getLogger(__name__)
_LLM_GATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


DOMAIN_TERMS = {
    "家装", "装修", "定制", "全屋", "橱柜", "衣柜", "板材", "环保", "甲醛", "enf", "e0",
    "设计", "户型", "风格", "新中式", "现代", "收纳", "厨房", "客厅", "卧室", "儿童房",
    "预算", "报价", "价格", "量房", "到店", "客户", "线索", "销售", "话术", "成交",
    "小红书", "抖音", "推广", "文案", "脚本", "案例", "竞品", "欧派", "索菲亚",
    "家装", "工艺", "安装", "售后", "门店", "方案", "效果图", "柜体", "五金", "台面",
    "产品", "柜子", "柜门", "柜类", "材料", "质量", "质保", "尺寸", "板件", "封边",
    "颗粒板", "多层板", "生态板", "肤感", "岩板", "套餐", "定金", "尾款", "合同", "交付",
    "复尺", "下单", "生产", "周期", "增项", "避坑", "验收", "保修", "门板", "拉手",
    "ai", "rag", "知识库", "embedding", "agent", "企微", "企业微信",
}
PROJECT_TERMS = {
    "openclaw", "deepseek", "openai", "chatgpt", "fastapi", "react", "vite", "jwt",
    "postgresql", "postgres", "chroma", "chromadb", "sqlite", "webhook", "api", "llm",
    "rerank", "bm25", "向量", "召回", "排序", "置信度", "登录", "权限", "角色",
}
INTENT_TERMS = {
    "food_drink": {
        "吃了啥", "吃什么", "吃饭", "早饭", "午饭", "晚饭", "夜宵", "小龙虾",
        "火锅", "烧烤", "奶茶", "咖啡", "喝", "eat", "drink", "lunch", "dinner",
    },
    "weather_time": {
        "天气", "几点", "几号", "星期几", "今天", "昨天", "明天", "周末",
        "weather", "time", "today", "tomorrow", "yesterday",
    },
    "greeting_identity": {
        "在吗", "你好", "hello", "hi", "你是谁", "你叫什么", "介绍一下你", "你能干嘛",
    },
    "emotional_chat": {
        "开心", "难过", "无聊", "焦虑", "哈哈", "讲个笑话", "陪我聊", "睡觉",
        "happy", "sad", "bored", "joke", "sleep",
    },
    "personal_life": {
        "你今天", "你昨天", "你明天", "你吃", "你喝", "你喜欢", "你家", "你在哪",
        "your favorite", "where are you", "did you eat",
    },
}
RELEVANCE_THRESHOLDS = {
    "keyword_overlap": 0.26,
    "bm25_strong": 0.8,
    "rerank_overlap": 0.28,
    "domain_vector": 0.28,
    "intent_hit_rate": 0.15,
    "min_signals": 2,
}
GENERIC_GATE_TERMS = {
    "今天", "昨天", "明天", "问题", "介绍", "系统", "平台", "内容", "生成",
    "怎么", "什么", "一下", "这个", "那个", "可以", "需要", "相关", "信息",
}
STRONG_BUSINESS_TERMS = {
    "板材", "报价", "环保", "预算", "量房", "定制", "全屋", "橱柜", "衣柜", "客户", "线索",
    "方案", "设计", "户型", "风格", "材料", "质量", "产品", "柜子", "甲醛", "五金", "台面",
    "工艺", "安装", "售后", "案例", "竞品", "成交", "复尺", "下单", "交付", "验收", "保修",
}
DIRECT_BUSINESS_GATE_TERMS = {
    "销售库", "设计库", "推广库", "管理库", "公共库", "知识库", "制度", "流程", "规章",
    "员工手册", "考勤", "请假", "报销", "审批", "绩效", "权限", "培训",
    "报价", "价格", "预算", "产品", "工艺", "安装", "售后", "质保", "合同", "交付",
    "板材", "环保", "甲醛", "enf", "e0", "五金", "台面", "柜门", "封边",
    "量房", "复尺", "下单", "定制", "全屋", "橱柜", "衣柜", "新中式",
    "话术", "成交", "线索", "异议", "客户问", "案例", "效果图", "户型",
    "小红书", "抖音", "推广", "文案", "脚本", "竞品", "爆款",
    "rag", "召回", "向量", "排序", "rerank", "agent", "企微", "企业微信",
}
INTERNAL_POLICY_TERMS = {
    "公司制度", "内部制度", "管理制度", "规章制度", "员工手册", "公司规定", "管理规定", "内部规定",
    "考勤制度", "打卡制度", "迟到", "早退", "请假", "调休", "加班", "休假", "年假", "病假", "事假",
    "报销制度", "报销流程", "费用报销", "差旅", "差旅标准", "出差", "借款", "发票", "审批流程",
    "绩效制度", "绩效考核", "人员绩效", "晋升", "转正", "试用期", "薪酬", "奖惩", "处罚", "奖励",
    "入职", "离职", "交接", "保密", "信息安全", "权限申请", "用章", "合同审批", "采购流程",
    "公共库", "管理库", "制度资料", "培训资料", "通用培训", "组织架构", "岗位职责", "工作流程",
}
DOMAIN_TERMS.update(INTERNAL_POLICY_TERMS)
STRONG_BUSINESS_TERMS.update(INTERNAL_POLICY_TERMS)

def classify_rag_query(query: str) -> dict:
    text = query.strip().lower()
    base = {
        "allowed": False,
        "intent": "empty",
        "reason": "empty_query",
        "domainIntent": False,
        "projectIntent": False,
        "casualIntent": False,
        "matchedSignals": [],
    }
    if not text:
        return base

    quality = query_quality(text)
    llm_gate = classify_rag_query_with_llm(text)
    if llm_gate:
        llm_gate["quality"] = quality
        return llm_gate

    return {
        "allowed": True,
        "intent": "classifier_unavailable",
        "reason": "rag_gate_classifier_unavailable_permissive",
        "domainIntent": True,
        "projectIntent": False,
        "casualIntent": False,
        "matchedSignals": [],
        "quality": quality,
        "classifier": "permissive_fallback",
        "confidence": 0.0,
        "latencyMs": 0,
        "cached": False,
    }


def should_skip_knowledge_search(query: str) -> bool:
    return not classify_rag_query(query)["allowed"]


def classify_rag_query_with_llm(text: str) -> dict[str, Any] | None:
    mode = (settings.rag_gate_classifier or "llm").lower().strip()
    if mode in {"off", "disabled", "permissive"}:
        return None

    cached = _get_cached_llm_gate(text)
    if cached is not None:
        result = dict(cached)
        result["cached"] = True
        result["latencyMs"] = 0
        return result

    started_at = time.perf_counter()
    try:
        provider = get_llm_provider()
        if not provider.available():
            return None
        prompt = (
            "你是 RAG 知识库前置意图门控。只输出 JSON，不要输出解释。\n"
            "任务：判断用户问题是否应该进入企业知识库检索。\n"
            "分类：\n"
            "- business_knowledge：产品、报价、工艺、设计、销售、推广、知识库资料等业务知识问题。\n"
            "- internal_policy：公司制度、考勤、请假、报销、审批、绩效、培训、权限等内部管理问题。\n"
            "- platform_project：本系统/API/RAG/Agent/企微/登录/权限/上传/向量检索等项目问题。\n"
            "- smalltalk：吃饭、天气、问候、情绪陪聊、个人生活等非业务闲聊。\n"
            "- general：与企业知识库无关的一般问题。\n"
            "- uncertain：信息不足，不能确定。\n"
            "规则：只在明确是 smalltalk 或 general 时阻止检索；uncertain 要放行给后续 reranker/triad 判断。\n"
            "返回格式：{\"intent\":\"...\",\"allowed\":true/false,\"confidence\":0到1,\"reason\":\"不超过30字\"}"
        )
        response = provider.chat_completion(
            {
                "model": settings.deepseek_default_model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text[:1200]},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=min(settings.ai_request_timeout_seconds, 8),
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        data = json.loads(content)
        result = normalize_llm_gate_result(data)
        result["latencyMs"] = round((time.perf_counter() - started_at) * 1000, 2)
        result["cached"] = False
        _set_cached_llm_gate(text, result)
        return result
    except Exception:
        logger.warning("RAG LLM intent gate failed", exc_info=True)
        return None


def normalize_llm_gate_result(data: dict[str, Any]) -> dict[str, Any]:
    allowed_intents = {"business_knowledge", "internal_policy", "platform_project", "smalltalk", "general", "uncertain"}
    intent = str(data.get("intent") or "uncertain").strip()
    if intent not in allowed_intents:
        intent = "uncertain"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0

    if intent == "uncertain" or confidence < settings.rag_gate_min_confidence:
        allowed = True
        reason = "classifier_uncertain_allow_rerank"
    elif intent in {"business_knowledge", "internal_policy", "platform_project"}:
        allowed = True
        reason = str(data.get("reason") or "llm_business_intent")
    else:
        allowed = False
        reason = str(data.get("reason") or "llm_non_business_intent")

    return {
        "allowed": allowed,
        "intent": intent,
        "reason": reason[:120],
        "domainIntent": intent in {"business_knowledge", "internal_policy"} or intent == "uncertain",
        "projectIntent": intent == "platform_project",
        "casualIntent": intent in {"smalltalk", "general"},
        "matchedSignals": [],
        "classifier": "llm",
        "confidence": round(confidence, 2),
    }


def rag_gate_observation(gate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not gate:
        return None
    return {
        "allowed": gate.get("allowed"),
        "intent": gate.get("intent"),
        "reason": gate.get("reason"),
        "classifier": gate.get("classifier"),
        "confidence": gate.get("confidence"),
        "latencyMs": gate.get("latencyMs"),
        "cached": gate.get("cached"),
    }


def _get_cached_llm_gate(text: str) -> dict[str, Any] | None:
    ttl = max(0, int(settings.rag_gate_cache_ttl_seconds or 0))
    if ttl <= 0:
        return None
    item = _LLM_GATE_CACHE.get(text)
    if not item:
        return None
    created_at, value = item
    if time.time() - created_at > ttl:
        _LLM_GATE_CACHE.pop(text, None)
        return None
    return value


def _set_cached_llm_gate(text: str, value: dict[str, Any]) -> None:
    ttl = max(0, int(settings.rag_gate_cache_ttl_seconds or 0))
    if ttl <= 0:
        return
    if len(_LLM_GATE_CACHE) > 512:
        oldest = min(_LLM_GATE_CACHE.items(), key=lambda item: item[1][0])[0]
        _LLM_GATE_CACHE.pop(oldest, None)
    _LLM_GATE_CACHE[text] = (time.time(), dict(value))



def query_quality(text: str) -> dict:
    terms = effective_query_terms(text)
    domain_hits = {term for term in terms if term in DOMAIN_TERMS or any(term in item for item in DOMAIN_TERMS if len(term) >= 3)}
    project_hits = {term for term in terms if term in PROJECT_TERMS or any(term in item for item in PROJECT_TERMS if len(term) >= 3)}
    total = max(1, len(terms))
    strong_domain_terms = {
        term for term in matched_domain_terms(text)
        if term not in GENERIC_GATE_TERMS and (is_strong_exact_term(term) or len(term) >= 3)
    }
    strong_project_terms = {
        term for term in matched_project_terms(text)
        if len(term) >= 4 or term in {"rag", "agent", "api", "jwt"}
    }
    return {
        "effectiveTokenCount": len(terms),
        "domainMatches": sorted(domain_hits)[:12],
        "projectMatches": sorted(project_hits)[:12],
        "domainMatchCount": len(domain_hits),
        "projectMatchCount": len(project_hits),
        "domainHitRate": round(len(domain_hits) / total, 4),
        "projectHitRate": round(len(project_hits) / total, 4),
        "strongDomainSignals": sorted(strong_domain_terms)[:12],
        "strongProjectSignals": sorted(strong_project_terms)[:12],
        "strongDomainSignalCount": len(strong_domain_terms),
        "strongProjectSignalCount": len(strong_project_terms),
    }


def effective_query_terms(text: str) -> set[str]:
    return {
        term
        for term in set(tokenize(text))
        if term_not_too_short(term) and term not in GENERIC_GATE_TERMS and not term.isdigit()
    }


def has_domain_intent(text: str) -> bool:
    return bool(matched_domain_terms(text))


def has_project_intent(text: str) -> bool:
    return bool(matched_project_terms(text))


def matched_domain_terms(text: str) -> list[str]:
    return matched_terms(text, DOMAIN_TERMS)


def matched_project_terms(text: str) -> list[str]:
    return matched_terms(text, PROJECT_TERMS)


def matched_terms(text: str, terms: set[str]) -> list[str]:
    lower = text.lower()
    ascii_words = set(re.findall(r"[a-z0-9_]+", lower))
    matched = []
    for term in terms:
        normalized = term.lower()
        if re.fullmatch(r"[a-z0-9_]+", normalized):
            if len(normalized) >= 3 and normalized in ascii_words:
                matched.append(term)
        elif normalized in lower:
            matched.append(term)
    return matched


def term_not_too_short(term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_]+", term):
        return len(term) >= 3
    return len(term) >= 2


def has_casual_intent(text: str) -> bool:
    return bool(detect_smalltalk_intent(text)["intent"])


def detect_smalltalk_intent(text: str) -> dict:
    for intent, terms in INTENT_TERMS.items():
        matched = matched_terms(text, terms)
        if matched:
            return {"intent": intent, "matchedTerms": matched}
    return {"intent": "", "matchedTerms": []}


def is_strong_exact_term(term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_]{3,}", term):
        return True
    if term in STRONG_BUSINESS_TERMS:
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{3,}", term))


def has_business_exact_term(terms: set[str]) -> bool:
    return bool(terms & DOMAIN_TERMS)
