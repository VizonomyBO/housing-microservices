from __future__ import annotations

from typing import Iterable, Set

from sqlalchemy import event, inspect

from shared_data_layer.db.maintenance import (
    refresh_base_documents_cache_sync,
    refresh_graph_materializations_sync,
)
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.knowledge_graph import GraphEdge, GraphEvidence


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
    for country in countries:
        refresh_base_documents_cache_sync(connection, country)


@event.listens_for(Document, "after_insert")
def document_after_insert(mapper, connection, target) -> None:
    if target.access_scope == "base" and target.country_code:
        refresh_base_documents_cache_sync(connection, target.country_code)


@event.listens_for(Document, "after_update")
def document_after_update(mapper, connection, target) -> None:
    countries = _collect_base_countries(target)
    if countries:
        _refresh_countries(connection, countries)


@event.listens_for(Document, "after_delete")
def document_after_delete(mapper, connection, target) -> None:
    if target.access_scope == "base" and target.country_code:
        refresh_base_documents_cache_sync(connection, target.country_code)


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
