"""Helper utilities for reduced profile E2E fixtures.

This module loads the markdown documents + scenario manifest introduced in Task 02.
It exposes typed models for automation scripts so future agents can re-use the
scenario without re-writing parsing logic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "data" / "reduced_e2e"
MANIFEST_FILENAME = "scenario_manifest.json"


class ScenarioDefaults(BaseModel):
    """Defaults applied to every document entry unless overridden."""

    country_code: str = "USA"
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    access_scope: str = "user_shared"


class ValidationRule(BaseModel):
    """Structured validation hints consumed by the CLI."""

    type: str
    pattern: str | None = None
    values: list[str] | None = None
    field: str | None = None
    tolerance: float | None = None
    comparison: str | None = None
    value: float | None = None


class PromptSpec(BaseModel):
    id: str
    question: str
    capability: str
    document_aliases: list[str]
    expected_traits: list[str]
    validation_rules: list[ValidationRule] = Field(default_factory=list)


class DocumentSpec(BaseModel):
    alias: str
    slug: str
    canonical_name: str
    filename: str
    doc_type: str
    description: str
    expected_citations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    numerical_expectations: dict[str, Any] | None = None
    kpi_expectations: dict[str, Any] | None = None
    country_code: str
    language: str
    tags: list[str]
    access_scope: str


class ReducedE2EManifest(BaseModel):
    scenario: str
    version: str
    defaults: ScenarioDefaults
    documents: list[DocumentSpec]
    prompts: list[PromptSpec]

    @model_validator(mode="before")
    @classmethod
    def _inject_defaults(cls, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data
        defaults = data.get("defaults") or {}
        doc_defaults = {
            "country_code": defaults.get("country_code", "USA"),
            "language": defaults.get("language", "en"),
            "tags": list(defaults.get("tags") or []),
            "access_scope": defaults.get("access_scope", "user_shared"),
        }
        for entry in data.get("documents", []):
            entry.setdefault("country_code", doc_defaults["country_code"])
            entry.setdefault("language", doc_defaults["language"])
            entry.setdefault("access_scope", doc_defaults["access_scope"])
            entry.setdefault("tags", list(doc_defaults["tags"]))
        return data


@dataclass(slots=True, frozen=True)
class DocumentFixture:
    spec: DocumentSpec
    path: Path
    content: str
    content_hash: str


class FixtureLoader:
    """Loads reduced E2E fixtures from disk."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_FIXTURE_DIR
        if not self.base_dir.exists():
            raise FileNotFoundError(f"Fixture directory missing: {self.base_dir}")
        self._manifest = self._load_manifest()
        self._documents = self._load_documents()
        self._document_by_alias = {doc.spec.alias: doc for doc in self._documents}
        self._prompt_by_id = {prompt.id: prompt for prompt in self._manifest.prompts}

    @property
    def manifest(self) -> ReducedE2EManifest:
        return self._manifest

    def documents(self) -> list[DocumentFixture]:
        return list(self._documents)

    def prompts(self) -> list[PromptSpec]:
        return list(self._manifest.prompts)

    def get_document(self, alias: str) -> DocumentFixture:
        try:
            return self._document_by_alias[alias]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"Unknown document alias: {alias}") from exc

    def get_prompt(self, prompt_id: str) -> PromptSpec:
        try:
            return self._prompt_by_id[prompt_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"Unknown prompt id: {prompt_id}") from exc

    def documents_for_prompt(self, prompt_id: str) -> list[DocumentFixture]:
        prompt = self.get_prompt(prompt_id)
        return [self.get_document(alias) for alias in prompt.document_aliases]

    def _load_manifest(self) -> ReducedE2EManifest:
        manifest_path = self.base_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            raise FileNotFoundError(f"Scenario manifest missing: {manifest_path}")
        with manifest_path.open("r", encoding="utf-8") as manifest_file:
            data = json.load(manifest_file)
        return ReducedE2EManifest.model_validate(data)

    def _load_documents(self) -> list[DocumentFixture]:
        fixtures: list[DocumentFixture] = []
        for spec in self._manifest.documents:
            md_path = self.base_dir / spec.filename
            if not md_path.exists():
                raise FileNotFoundError(f"Document fixture missing: {md_path}")
            content = md_path.read_text(encoding="utf-8")
            content_hash = sha256_file(md_path)
            fixtures.append(
                DocumentFixture(spec=spec, path=md_path, content=content, content_hash=content_hash)
            )
        return fixtures


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hash for a file using buffered reads."""

    if hasattr(hashlib, "file_digest"):
        with path.open("rb") as file_handle:
            return hashlib.file_digest(file_handle, "sha256").hexdigest()

    hasher = hashlib.sha256()
    with path.open("rb") as file_handle:  # pragma: no cover - fallback path
        for chunk in iter(lambda: file_handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def list_document_aliases(loader: FixtureLoader | None = None) -> Iterable[str]:
    loader = loader or FixtureLoader()
    return tuple(doc.spec.alias for doc in loader.documents())


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    loader = FixtureLoader()
    print(f"Scenario: {loader.manifest.scenario} ({loader.manifest.version})")
    print("Documents:")
    for fixture in loader.documents():
        print(
            f" - {fixture.spec.alias} :: {fixture.content_hash[:10]}... :: {fixture.spec.canonical_name}"
        )
    print("Prompts:")
    for prompt in loader.prompts():
        print(f" - {prompt.id} ({', '.join(prompt.document_aliases)})")
