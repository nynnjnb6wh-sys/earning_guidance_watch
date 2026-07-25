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
from guidance_watch.agent.runner import AgentRunResult, run_agent
from guidance_watch.agent.tools import AgentTools, ToolContext

__all__ = [
    "AgentRunResult",
    "AgentTools",
    "AssistantMessage",
    "CompletionResult",
    "LlmProvider",
    "MissingLlmCredentialsError",
    "ScriptedProvider",
    "ToolCall",
    "ToolContext",
    "llm_mode",
    "resolve_provider",
    "run_agent",
]
