"""LangGraph ReAct agent wiring."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval QA agent. Use the provided tools to gather evidence from attached "
    "documents. When answering, include concise sentences with [c#] citations that align to the "
    "context blocks returned by the retrieval tool. If context is insufficient, say so and avoid "
    "speculation."
)


def build_react_agent(
    *,
    llm: ChatOpenAI,
    tools: Iterable[Any],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
):
    checkpointer = MemorySaver()
    agent = create_agent(
        model=llm, tools=list(tools), system_prompt=system_prompt, checkpointer=checkpointer
    )
    return agent


__all__ = ["DEFAULT_SYSTEM_PROMPT", "build_react_agent"]
