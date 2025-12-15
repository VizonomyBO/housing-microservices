"""Fixture helpers that wrap the shared loader from Task 02."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.reduced_e2e_fixtures import (
    DocumentFixture,
    FixtureLoader,
    PromptSpec,
    list_document_aliases,
)


@dataclass(slots=True)
class ScenarioFixtures:
    """Convenience wrapper exposing manifest, documents, and prompts."""

    loader: FixtureLoader

    @classmethod
    def load(cls, base_dir: Path | None = None) -> ScenarioFixtures:
        return cls(loader=FixtureLoader(base_dir))

    @property
    def manifest(self):  # type: ignore[override]
        return self.loader.manifest

    def documents(self) -> list[DocumentFixture]:
        return self.loader.documents()

    def prompts(self) -> list[PromptSpec]:
        return self.loader.prompts()

    def document_map(self) -> dict[str, DocumentFixture]:
        return {doc.spec.alias: doc for doc in self.loader.documents()}

    def documents_for_prompt(self, prompt: PromptSpec) -> list[DocumentFixture]:
        return [self.loader.get_document(alias) for alias in prompt.document_aliases]

    def list_aliases(self) -> Iterable[str]:
        return list_document_aliases(self.loader)


__all__ = ["ScenarioFixtures"]
