"""Pipecat's context/VAD APIs moved between 0.0.8x and 0.0.9x. This module hides the difference.

Every import is lazy so the REST API and tests run without pipecat installed.
"""
from __future__ import annotations

from typing import Any


def make_tools_schema(defs: list[dict]):
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    return ToolsSchema(standard_tools=[
        FunctionSchema(name=d["name"], description=d["description"], properties=d["properties"], required=d["required"])
        for d in defs])


def make_context(llm: Any, messages: list[dict], tools: Any, vad: Any) -> tuple[Any, Any, Any, bool]:
    """Returns (context, user_aggregator, assistant_aggregator, vad_attached_to_aggregator)."""
    try:
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import (LLMContextAggregatorPair,
                                                                           LLMUserAggregatorParams)
        context = LLMContext(messages, tools)
        try:
            pair = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(vad_analyzer=vad))
            return context, pair.user(), pair.assistant(), True
        except TypeError:           # new context classes, but VAD still configured on the transport
            pair = LLMContextAggregatorPair(context)
            return context, pair.user(), pair.assistant(), False
    except ImportError:
        from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
        context = OpenAILLMContext(messages, tools)
        pair = llm.create_context_aggregator(context)
        return context, pair.user(), pair.assistant(), False


def make_stt(api_key: str):
    try:
        from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService as Stt
    except ImportError:
        from pipecat.services.elevenlabs.stt import ElevenLabsSTTService as Stt
    return Stt(api_key=api_key)


async def trigger_llm(task: Any, user_aggregator: Any) -> None:
    """Ask the LLM to speak first (the greeting)."""
    try:
        from pipecat.frames.frames import LLMRunFrame
        await task.queue_frames([LLMRunFrame()])
    except ImportError:
        await task.queue_frames([user_aggregator.get_context_frame()])


def interruption_frame_types() -> tuple:
    import pipecat.frames.frames as f
    return tuple(getattr(f, n) for n in ("InterruptionFrame", "StartInterruptionFrame") if hasattr(f, n))
