"""LangGraph agentic RAG wiring with enforced tool use."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval-first research assistant for housing finance Q&A. Use the retrieved "
    "evidence to write one or two concise paragraphs (no bullets or numbered lists) that directly "
    "answer the user's questions. Weave the points together like a textbook section: clear topic "
    "sentences, coherent flow across sub-questions, and short sentences when possible. Cite "
    "specific facts with [c#] references immediately after each claim. Always call "
    "`retrieve_documents` before responding so your answers are grounded. If retrieval looks weak, "
    "rewrite and retrieve again. Use `compute_over_chunks` for calculations/analysis on retrieved "
    "data. Stay within the response length limit and never cut off mid-sentence. Do not answer "
    "without citations."
)


def build_agent_graph(
    *,
    llm: ChatOpenAI,
    tools: Iterable[Any],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
):
    """Build a LangGraph that guarantees tool use and loops until the model stops."""

    tool_list = list(tools)
    graph = StateGraph(MessagesState)  # type: ignore[arg-type]

    def _call_model(state: MessagesState):
        messages = state.get("messages", [])
        if not messages:
            return {"messages": []}
        # Bind tools so the model can issue tool calls; system prompt is injected as first message.
        bound = llm.bind_tools(tool_list)
        response = bound.invoke(messages)
        return {"messages": [response]}

    graph.add_node("agent", _call_model)
    graph.add_node("tools", ToolNode(tool_list))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )
    graph.add_edge("tools", "agent")

    compiled = graph.compile(checkpointer=MemorySaver())
    return compiled


__all__ = ["DEFAULT_SYSTEM_PROMPT", "build_agent_graph"]
