"""LLM provider interface.

OpenRouter free models still require an API key (they are just unbilled).
When no key is configured, the system uses ScriptedProvider / the
deterministic extractor and never contacts a network LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from guidance_watch.config import Settings, get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantMessage:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class CompletionResult:
    message: AssistantMessage
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None


@runtime_checkable
class LlmProvider(Protocol):
    """Minimal tool-calling LLM interface."""

    model_id: str

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CompletionResult: ...


class ScriptedProvider:
    """Offline provider that replays a fixed sequence of assistant turns.

    Used by tests and as the default when no OpenRouter key is configured.
    """

    def __init__(
        self,
        script: list[AssistantMessage] | None = None,
        *,
        model_id: str = "scripted-provider",
    ) -> None:
        self.model_id = model_id
        self._script = list(script or [])
        self._index = 0

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CompletionResult:
        _ = (messages, tools)
        if self._index >= len(self._script):
            # Default terminal turn: no further tool calls.
            msg = AssistantMessage(content='{"relevant": false, "reason": "script_exhausted"}')
        else:
            msg = self._script[self._index]
            self._index += 1
        return CompletionResult(message=msg, model=self.model_id)


class MissingLlmCredentialsError(RuntimeError):
    """Raised only when live LLM mode is explicitly requested without a key."""


def resolve_provider(
    settings: Settings | None = None,
    *,
    require_live: bool = False,
    script: list[AssistantMessage] | None = None,
) -> LlmProvider:
    """Return ScriptedProvider unless a live OpenRouter key is available.

    OpenRouter ``:free`` models still need ``OPENROUTER_API_KEY``. Without a
    key, callers must use the deterministic / scripted path.
    """
    settings = settings or get_settings()
    key = (settings.openrouter_api_key or "").strip()
    if require_live:
        if not key:
            raise MissingLlmCredentialsError(
                "OPENROUTER_API_KEY is not set. OpenRouter free models still require "
                "an API key. Use the deterministic/scripted path, or set a key later."
            )
        from guidance_watch.agent.openrouter import OpenRouterProvider

        return OpenRouterProvider(settings)
    # Default: scripted/deterministic path (D19) even if a key happens to be present.
    return ScriptedProvider(script, model_id="scripted-provider")


def llm_mode(settings: Settings | None = None) -> str:
    """Return 'live' if a key is present, else 'scripted'."""
    settings = settings or get_settings()
    key = (settings.openrouter_api_key or "").strip()
    return "live" if key else "scripted"
