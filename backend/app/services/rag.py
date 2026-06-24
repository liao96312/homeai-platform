import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.domain import KnowledgeBase
from backend.app.services.knowledge import search_chunks
from backend.app.services.memory import build_memory_context, recall, summarize_and_remember
from backend.app.services.rag_gate import classify_rag_query
from backend.app.services.runtime_metrics import record_runtime_failure

logger = logging.getLogger(__name__)

AGENT_KB_MAP: dict[str, list[str]] = {
    "sales": ["product", "public"],
    "design": ["design", "public"],
    "promo": ["promotion", "public"],
    "management": ["management", "public"],
}

ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "sales": (
        "你是家装企业的销售 AI 助手「销售顾问助手」，专门为家装定制行业提供销售咨询支持。"
        "你的职责包括：解答客户关于产品工艺、材质、报价、环保等级、安装流程的疑问；"
        "根据销售库提供异议处理、报价解释、FAQ、成交话术和竞品对比，辅助客户决策。"
        "请始终保持专业、热情、真诚，用简洁清晰的中文回答。"
        "回答时优先引用知识库中的具体数据、话术和案例；如果资料不足，请明确说明需要人工顾问确认。"
    ),
    "design": (
        "你是家装企业的设计 AI 助手「设计方案助手」，专门为室内设计师提供方案参考和技术支持。"
        "你的职责包括：根据设计库提供案例图库、工艺标准、材质规格、风格方案和材料搭配建议；"
        "必要时结合公共库中的公司标准和通用培训资料，生成结构化设计需求卡。"
        "请保持专业、细致、有创意，帮助设计师提升方案质量和沟通效率。"
    ),
    "promo": (
        "你是家装企业的推广 AI 助手「内容增长助手」，专门负责内容创作和营销推广支持。"
        "你的职责包括：生成小红书、抖音、朋友圈、公众号等平台的高转化文案和脚本；"
        "结合推广库中的品牌规范、竞品分析和爆款文案模板，提炼卖点、用户利益点和差异化表达。"
        "请保持有创意、有网感、有转化力，输出内容要适配平台语气，并带有互动引导。"
    ),
    "management": (
        "你是家装企业的管理 AI 助手，面向管理层提供经营分析、人员绩效、战略资料和制度解读支持。"
        "回答时优先基于管理库和公共库资料，涉及经营数据或人员绩效时保持审慎，不要编造未提供的数据。"
        "如果资料不足，请明确提示需要管理层人工确认。"
    ),
}

DEFAULT_SYSTEM_PROMPT = (
    "你是家装企业的 AI 智能助手，专门为家装定制行业提供专业支持。"
    "请根据提供的知识库内容准确、专业地回答用户问题。"
    "如果知识库中没有相关信息，请如实告知，不要编造。"
)


def retrieve_context(
    db: Session,
    query: str,
    conversation_key: str,
    user_id: str = "",
    top_k: int = 5,
    gate: dict | None = None,
) -> tuple[list[dict], str]:
    """Retrieve ranked chunks from agent-scoped knowledge bases plus memory."""
    gate = gate or classify_rag_query(query)
    if not gate["allowed"]:
        logger.info("RAG pre-gate blocked query: reason=%s", gate["reason"])
        return [], ""

    kb_keys = AGENT_KB_MAP.get(conversation_key)
    if not kb_keys:
        kb_keys = ["product", "design", "promotion", "management", "public"]

    all_chunks: list[dict] = []
    for kb_key in kb_keys:
        kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == kb_key))
        if not kb:
            continue
        try:
            results = search_chunks(db, kb, query, top_k=3, gate=gate)
        except Exception as exc:
            record_runtime_failure("knowledge_search_failed", exc)
            logger.warning("Knowledge search failed for kb=%s", kb_key, exc_info=True)
            continue
        for result in results:
            result["kb_name"] = kb.name
            result["kb_key"] = kb_key
        all_chunks.extend(results)

    all_chunks.sort(key=lambda item: item.get("score", 0), reverse=True)
    all_chunks = all_chunks[:top_k]
    for rank, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = rank

    memory_str = ""
    if user_id:
        try:
            memories = recall(user_id, query)
            if memories:
                memory_str = build_memory_context(memories)
        except Exception as exc:
            record_runtime_failure("memory_recall_failed", exc)
            logger.warning("Memory recall failed for user=%s", user_id, exc_info=True)

    context_str = _format_context(all_chunks, memory_str)
    return all_chunks, context_str


def save_conversation_turn(user_id: str, user_message: str, assistant_reply: str) -> None:
    """Save a conversation exchange to long-term memory."""
    if not user_id:
        return
    try:
        summarize_and_remember(user_id, user_message, assistant_reply)
    except Exception as exc:
        record_runtime_failure("memory_save_failed", exc)
        logger.warning("Failed to save conversation memory for user=%s", user_id, exc_info=True)


def _format_context(chunks: list[dict], memory_str: str = "") -> str:
    parts = []
    if chunks:
        parts.append("以下是知识库中检索到的相关信息，已按相关性从高到低排序：")
        parts.append("")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("kb_name", "未知知识库")
            filename = chunk.get("filename", "")
            score = chunk.get("score", 0)
            relevance_level = (chunk.get("relevance") or {}).get("level", "medium")
            parts.append(
                f"【参考资料{i}】来源：{source} | 文件：{filename} | 排序分：{score:.2f} | 相关性：{relevance_level}\n"
                f"{chunk.get('content', '')}\n"
            )

    if memory_str:
        parts.append(memory_str)
        parts.append("")

    return "\n".join(parts) if parts else ""


def build_rag_prompt(context_str: str, conversation_key: str) -> str:
    """Build a complete system prompt with role instruction and RAG context."""
    system_prompt = ROLE_SYSTEM_PROMPTS.get(conversation_key, DEFAULT_SYSTEM_PROMPT)

    if not context_str:
        return (
            f"{system_prompt}\n\n"
            "（本次未检索到相关知识库内容。"
            "请如实告知用户当前知识库无法回答该问题，建议用户联系人工顾问获取准确答案。"
            "不要编造任何产品参数、报价、工艺细节等专业知识。）"
        )

    return (
        f"{system_prompt}\n\n"
        f"{context_str}\n"
        "---\n"
        "【重要】请严格基于以上知识库参考资料回答用户问题。\n"
        "1. 只能使用参考资料中明确提到的数据、参数、事实。\n"
        "2. 不要编造、推测或补充参考资料中没有的信息。\n"
        "3. 如果参考资料不足以完整回答，请明确告知用户「知识库中暂无该信息，建议联系人工顾问」。\n"
        "4. 不要在回答中主动提及更高等级、更多选择等知识库未覆盖的内容。"
    )
