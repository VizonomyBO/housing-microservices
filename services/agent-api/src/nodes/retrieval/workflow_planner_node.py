"""WorkflowPlanner LangGraph node implementation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cache.cache_keys import RetrievalCacheKeyInputs, build_retrieval_cache_key
from models.retrieval import AttachmentScope
from nodes.retrieval.exceptions import (
    InputNormalizationError,
    WorkflowPlanningError,
)
from repositories.workflow_planner_repository import (
    WorkflowPlanCatalogProtocol,
    WorkflowPlanSource,
)
from state.agent_state import (
    AgentState,
    CacheMetadata,
    GraphContext,
    WorkflowPlan,
    WorkflowPlanStep,
)

CacheKeyBuilder = Callable[[RetrievalCacheKeyInputs], str]


def _intent_component(intent_tags: list[str]) -> str:
    if not intent_tags:
        return "general"
    return "|".join(sorted(intent_tags))


def _collect_document_hashes(scope: AttachmentScope) -> list[str | None]:
    document_hashes: list[str | None] = []
    for document in scope.documents:
        metadata = document.metadata or {}
        document_hashes.append(
            metadata.get("content_hash") or metadata.get("hash") or document.document_id
        )
    return document_hashes


def _collect_prerequisites(steps: list[WorkflowPlanStep]) -> list[str]:
    prerequisites: set[str] = set()
    for step in steps:
        for key in sorted(step.preconditions):
            value = step.preconditions[key]
            serialized = json.dumps(value, sort_keys=True)
            prerequisites.add(f"{key}:{serialized}")
    return sorted(prerequisites)


def _order_nodes(source: WorkflowPlanSource) -> list[WorkflowPlanStep]:
    ordered_nodes = sorted(source.nodes, key=lambda node: node.path)
    return [
        WorkflowPlanStep(
            key=node.key,
            description=node.description or node.key,
            preconditions=dict(node.preconditions),
            tool_hints=list(node.tool_hints),
            artifacts=dict(node.artifacts),
        )
        for node in ordered_nodes
    ]


def _update_cache_metadata(cache_metadata: CacheMetadata, cache_key: str) -> CacheMetadata:
    return cache_metadata.model_copy(update={"cache_key": cache_key, "hit": False, "hit_at": None})


def _update_graph_context(graph_context: GraphContext, version: str | None) -> GraphContext:
    return graph_context.model_copy(update={"workflow_plan_version": version})


@dataclass(slots=True)
class WorkflowPlannerNode:
    """Builds workflow plans from workflow graphs + cache metadata."""

    workflow_catalog: WorkflowPlanCatalogProtocol
    build_cache_key: CacheKeyBuilder = field(default=build_retrieval_cache_key)

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        normalized_input = state.normalized_input
        if normalized_input is None:
            raise InputNormalizationError(
                code="NORMALIZED_INPUT_MISSING",
                message="InputNormalizer must run before WorkflowPlanner",
            )
        attachment_scope = state.attachment_scope
        if attachment_scope is None:
            raise WorkflowPlanningError(
                code="ATTACHMENT_SCOPE_MISSING",
                message="AttachmentScopeLoader must run before WorkflowPlanner",
            )
        workflow = self._select_workflow(attachment_scope)
        if workflow is None:
            raise WorkflowPlanningError(
                code="WORKFLOW_ATTACHMENT_MISSING",
                message="At least one workflow attachment is required before planning",
            )

        plan_source = await self.workflow_catalog.fetch_plan_source(workflow.workflow_id)
        if plan_source is None:
            raise WorkflowPlanningError(
                code="WORKFLOW_PLAN_NOT_FOUND",
                message="Workflow graph not found or missing versions",
                details={"workflow_id": workflow.workflow_id},
            )

        steps = _order_nodes(plan_source)
        plan = WorkflowPlan(
            plan_id=plan_source.graph_id,
            version=plan_source.version,
            steps=steps,
            diff_summary=plan_source.diff_summary or plan_source.change_log,
            prerequisites=_collect_prerequisites(steps),
        )

        document_hashes = _collect_document_hashes(attachment_scope)
        cache_key = self.build_cache_key(
            RetrievalCacheKeyInputs(
                conversation_id=state.conversation_id,
                intent=_intent_component(normalized_input.intent_tags),
                workflow_version=plan.version,
                document_hashes=document_hashes,
            )
        )

        cache_metadata = _update_cache_metadata(state.cache_metadata, cache_key)
        graph_context = _update_graph_context(state.graph_context, plan.version)
        return {
            "workflow_plan": plan,
            "graph_context": graph_context,
            "cache_metadata": cache_metadata,
        }

    def _select_workflow(self, scope: AttachmentScope):
        if not scope.workflows:
            return None
        # Prefer explicitly provided workflows first (sorted upstream), fallback to first entry.
        return scope.workflows[0]


__all__ = ["WorkflowPlannerNode"]
