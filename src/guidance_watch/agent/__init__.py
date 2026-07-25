"""LLM tool-calling agent (OpenRouter behind a provider interface)."""

from guidance_watch.agent.provider import (
    AssistantMessage,
    CompletionResult,
    LlmProvider,
    MissingLlmCredentialsError,
    ScriptedProvider,
    ToolCall,
    llm_mode,
    resolve_provider,
)

__all__ = [
    "AssistantMessage",
    "CompletionResult",
    "LlmProvider",
    "MissingLlmCredentialsError",
    "ScriptedProvider",
    "ToolCall",
    "llm_mode",
    "resolve_provider",
]
