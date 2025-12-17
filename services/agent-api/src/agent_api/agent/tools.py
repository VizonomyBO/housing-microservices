"""LangGraph tools used by the ReAct agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from agent_api.agent.tool_runtime import get_runtime
from agent_api.services.retrieval_scope import ConversationDocumentRecord
from agent_api.tools.pyodide import execute_in_pyodide

logger = logging.getLogger(__name__)


def _serialize_attachment(record: ConversationDocumentRecord) -> dict[str, Any]:
    return {
        "document_id": record.document_id,
        "canonical_name": record.canonical_name,
        "access_scope": record.access_scope,
        "country_code": record.country_code,
        "role": record.role,
        "visibility": record.visibility,
        "metadata": record.metadata,
    }


@tool("retrieve_documents", return_direct=False)
async def retrieve_documents(query: str) -> str:
    """
    Retrieve text chunks from attached documents using hybrid BM25+vector search and rerank.
    Returns formatted context blocks with [c#] headers and citations metadata.
    """

    runtime = get_runtime()
    ctx = await runtime.retrieval.retrieve(
        user_query=query,
        conversation_id=runtime.conversation_id,
    )
    runtime.last_retrieval = ctx
    payload = {
        "context": ctx.context_text,
        "citations": ctx.citations,
        "attachments": [_serialize_attachment(att) for att in ctx.attachments],
    }
    return json.dumps(payload)


@tool("document_status", return_direct=False)
async def document_status(document_id: str) -> str:
    """Return status/ingestion stage for a specific document id."""

    runtime = get_runtime()
    summaries = await runtime.retrieval.scope_repo.hydrate_documents([document_id])
    summary = summaries.get(document_id)
    if not summary:
        return json.dumps({"status": "not_found"})
    return json.dumps(
        {
            "status": summary.status,
            "access_scope": summary.access_scope,
            "country_code": summary.country_code,
            "language": summary.language,
            "tags": summary.tags or [],
            "metadata": summary.metadata or {},
        }
    )


@tool("list_attachments", return_direct=False)
async def list_attachments() -> str:
    """List attachments for the current conversation."""

    runtime = get_runtime()
    attachments = await runtime.retrieval.scope_repo.list_conversation_documents(
        runtime.conversation_id
    )
    return json.dumps([_serialize_attachment(att) for att in attachments])


@tool("pyodide_sandbox", return_direct=False)
async def pyodide_sandbox(code: str, packages: list[str] | None = None) -> str:
    """
    Execute Python code inside the Pyodide sandbox. Fails fast if the sandbox is not configured.
    """

    runtime = get_runtime()
    result = await execute_in_pyodide(
        code=code,
        packages=packages or [],
        request_id=runtime.request_id,
        config=runtime.pyodide,
    )
    return json.dumps(result)


__all__ = ["document_status", "list_attachments", "pyodide_sandbox", "retrieve_documents"]
