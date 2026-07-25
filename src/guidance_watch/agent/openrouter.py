"""OpenRouter OpenAI-compatible provider (optional; requires API key)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from guidance_watch.agent.provider import AssistantMessage, CompletionResult, ToolCall
from guidance_watch.config import Settings


class OpenRouterProvider:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        key = (settings.openrouter_api_key or "").strip()
        if not key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouterProvider")
        self.model_id = settings.openrouter_model
        self._base_url = settings.openrouter_base_url.rstrip("/")
        self._api_key = key
        self._client = client

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CompletionResult:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        if self._client is not None:
            response = self._client.post(url, headers=headers, json=payload)
        else:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for tc in choice.get("tool_calls") or []:
            args_raw = tc.get("function", {}).get("arguments") or "{}"
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or "",
                    name=tc.get("function", {}).get("name") or "",
                    arguments=args,
                )
            )
        usage = data.get("usage") or {}
        return CompletionResult(
            message=AssistantMessage(content=choice.get("content"), tool_calls=tool_calls),
            model=data.get("model") or self.model_id,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
