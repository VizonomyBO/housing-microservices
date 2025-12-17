"""LangGraph ReAct agent wiring."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval-first ReAct agent for housing finance Q&A. Always call the "
    "`retrieve_documents` tool before answering so you work from cited context. The tool returns "
    "context blocks labeled [c#] plus citation metadata; write concise answers that include those "
    "[c#] markers and avoid speculation. If the context is missing or weak, state that you cannot "
    "answer and ask for better documents instead of guessing. Use `document_status` only to confirm "
    "readiness and avoid `pyodide_sandbox` unless a calculation is explicitly requested."
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
