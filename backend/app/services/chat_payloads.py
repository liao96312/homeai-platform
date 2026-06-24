from typing import Any

from backend.app.core.config import settings


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_value = item.get("text")
                    if isinstance(text_value, dict):
                        parts.append(str(text_value.get("value") or ""))
                    else:
                        parts.append(str(text_value or ""))
                elif "text" in item:
                    parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def build_deepseek_payload(req: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": req.model or settings.deepseek_default_model,
        "messages": [message_to_deepseek(message) for message in req.messages],
    }
    optional_fields = [
        "temperature",
        "top_p",
        "stream",
        "stop",
        "max_tokens",
        "presence_penalty",
        "frequency_penalty",
        "response_format",
        "tools",
        "tool_choice",
        "thinking",
    ]
    data = req.model_dump(exclude={"n", "provider", "metadata", "user"}, exclude_none=True, mode="json")
    for field in optional_fields:
        value = data.get(field)
        if value is not None:
            payload[field] = value
    return payload


def merge_system_message(messages: list[dict[str, Any]], extra_system_prompt: str) -> None:
    system_indexes = [index for index, message in enumerate(messages) if message.get("role") == "system"]
    if system_indexes:
        first = system_indexes[0]
        original = str(messages[first].get("content") or "").strip()
        messages[first]["content"] = "\n\n".join(part for part in [original, extra_system_prompt.strip()] if part)
        for index in reversed(system_indexes[1:]):
            messages.pop(index)
    else:
        messages.insert(0, {"role": "system", "content": extra_system_prompt})


def message_to_deepseek(message: Any) -> dict[str, Any]:
    data = message.model_dump(exclude_none=True)
    if "content" in data and not isinstance(data["content"], str):
        data["content"] = extract_text(data["content"])
    return data
