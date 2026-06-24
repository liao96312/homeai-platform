from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol

import httpx

from backend.app.core.config import settings


class LLMProvider(Protocol):
    name: str
    default_model: str

    def available(self) -> bool: ...

    def chat_completion(self, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]: ...

    async def chat_completion_async(self, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]: ...

    def stream_chat_completion(self, payload: dict[str, Any], timeout: float | None = None) -> AsyncGenerator[str, None]: ...

    def health(self) -> dict[str, Any]: ...


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = settings.deepseek_default_model

    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat_completion(self, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=timeout or settings.ai_request_timeout_seconds) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    async def chat_completion_async(self, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        # Native async path for use inside async routes — avoids blocking the
        # event loop while waiting on the upstream LLM (default timeout 60s).
        async with httpx.AsyncClient(timeout=timeout or settings.ai_request_timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    async def stream_chat_completion(self, payload: dict[str, Any], timeout: float | None = None) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=timeout or settings.ai_request_timeout_seconds) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if isinstance(line, bytes):
                        yield line.decode("utf-8", errors="replace")
                    else:
                        yield line

    def health(self) -> dict[str, Any]:
        result = {"ok": False, "provider": self.name, "model": settings.deepseek_default_model}
        if not self.available():
            result["error"] = "missing_api_key"
            return result
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
            result["ok"] = response.status_code < 500
            result["statusCode"] = response.status_code
        except Exception as exc:
            result["error"] = type(exc).__name__
        return result


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    provider = (provider_name or settings.ai_provider or "deepseek").lower()
    if provider in {"deepseek", "openai-compatible", "openai_compatible"}:
        return DeepSeekProvider(settings.deepseek_api_key, settings.deepseek_base_url)
    raise ValueError(f"Unsupported LLM provider: {provider}")
