"""Provider resolution without OpenRouter credentials."""

from __future__ import annotations

import pytest

from guidance_watch.agent.provider import (
    MissingLlmCredentialsError,
    ScriptedProvider,
    llm_mode,
    resolve_provider,
)
from guidance_watch.config import Settings


@pytest.mark.unit
def test_defaults_to_scripted_without_key() -> None:
    settings = Settings(OPENROUTER_API_KEY=None)
    provider = resolve_provider(settings)
    assert isinstance(provider, ScriptedProvider)
    assert llm_mode(settings) == "scripted"


@pytest.mark.unit
def test_require_live_without_key_fails_clearly() -> None:
    settings = Settings(OPENROUTER_API_KEY="")
    with pytest.raises(MissingLlmCredentialsError, match="OPENROUTER_API_KEY"):
        resolve_provider(settings, require_live=True)


@pytest.mark.unit
def test_scripted_provider_replays_then_exhausts() -> None:
    from guidance_watch.agent.provider import AssistantMessage

    provider = ScriptedProvider(
        [AssistantMessage(content="first"), AssistantMessage(content="second")]
    )
    r1 = provider.complete_with_tools(messages=[], tools=[])
    r2 = provider.complete_with_tools(messages=[], tools=[])
    r3 = provider.complete_with_tools(messages=[], tools=[])
    assert r1.message.content == "first"
    assert r2.message.content == "second"
    assert r3.message.content is not None
    assert "script_exhausted" in r3.message.content
