from __future__ import annotations

import os
from typing import Iterable, Set

from sqlalchemy import event, inspect

from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view_sync,
    refresh_base_documents_cache_sync,
    refresh_graph_materializations_sync,
)
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.knowledge_graph import GraphEdge, GraphEvidence
from shared_data_layer.db.models.retrieval import Chunk


def _skip_view_refresh() -> bool:
    return os.getenv("SKIP_VIEW_REFRESH", "").lower() in ("true", "1", "yes")


def _collect_base_countries(target: Document) -> Set[str]:
    inspector = inspect(target)
    countries: Set[str] = set()

    if target.access_scope == "base" and target.country_code:
        countries.add(target.country_code)

    country_history = inspector.attrs.country_code.history
    scope_history = inspector.attrs.access_scope.history

    for previous in country_history.deleted:
        if previous:
            countries.add(previous)

    if any(scope == "base" for scope in scope_history.deleted):
        previous_country = None
        if country_history.deleted:
            previous_country = country_history.deleted[0]
        elif country_history.unchanged:
            previous_country = country_history.unchanged[0]
        else:
            previous_country = target.country_code
        if previous_country:
            countries.add(previous_country)

    return countries


def _refresh_countries(connection, countries: Iterable[str]) -> None:
    if _skip_view_refresh():
        return
    for country in countries:
        refresh_base_documents_cache_sync(connection, country)


def _refresh_active_chunks(connection) -> None:
    if _skip_view_refresh():
        return
    refresh_active_chunks_view_sync(connection, concurrently=False)


def _document_affects_active_chunks(target: Document) -> bool:
    inspector = inspect(target)
    status_history = inspector.attrs.status.history
    deleted_history = inspector.attrs.deleted_at.history

    if status_history.has_changes() or deleted_history.has_changes():
        return True
    return False


@event.listens_for(Document, "after_insert")
def document_after_insert(mapper, connection, target) -> None:
    if target.access_scope == "base" and target.country_code:
        refresh_base_documents_cache_sync(connection, target.country_code)
    if target.status == "active" and target.deleted_at is None:
        _refresh_active_chunks(connection)


@event.listens_for(Document, "after_update")
def document_after_update(mapper, connection, target) -> None:
    countries = _collect_base_countries(target)
    if countries:
        _refresh_countries(connection, countries)
    if _document_affects_active_chunks(target):
        _refresh_active_chunks(connection)


@event.listens_for(Document, "after_delete")
def document_after_delete(mapper, connection, target) -> None:
    if target.access_scope == "base" and target.country_code:
        refresh_base_documents_cache_sync(connection, target.country_code)
    _refresh_active_chunks(connection)


def _refresh_graph(connection) -> None:
    refresh_graph_materializations_sync(connection, concurrently=False)


@event.listens_for(GraphEdge, "after_insert")
@event.listens_for(GraphEdge, "after_update")
@event.listens_for(GraphEdge, "after_delete")
def graph_edge_changed(mapper, connection, target) -> None:
    _refresh_graph(connection)


@event.listens_for(GraphEvidence, "after_insert")
@event.listens_for(GraphEvidence, "after_update")
@event.listens_for(GraphEvidence, "after_delete")
def graph_evidence_changed(mapper, connection, target) -> None:
    _refresh_graph(connection)


@event.listens_for(Chunk, "after_insert")
def chunk_after_insert(mapper, connection, target) -> None:
    _refresh_active_chunks(connection)


@event.listens_for(Chunk, "after_update")
def chunk_after_update(mapper, connection, target) -> None:
    _refresh_active_chunks(connection)


@event.listens_for(Chunk, "after_delete")
def chunk_after_delete(mapper, connection, target) -> None:
    _refresh_active_chunks(connection)
