import sys
from pathlib import Path

import pytest
from shared_data_layer.config import DEFAULT_VOYAGE_EMBEDDING_DIMENSION

# ruff: noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SERVICE_SRC = ROOT / "services" / "ingestion-service" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from ingestion_service.pipeline import (
    IngestionError,
    IngestionPipeline,
    MarkdownChunker,
)
from ingestion_service.settings import Settings


def _make_settings(**overrides) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/housing",
        jwt_secret_key="secret",
        signing_secret="secret",
        voyage_api_key="dummy",
        voyage_output_dimension=DEFAULT_VOYAGE_EMBEDDING_DIMENSION,
        vector_store_dimension=DEFAULT_VOYAGE_EMBEDDING_DIMENSION,
        **overrides,
    )


def test_chunker_adds_contextual_rewrites() -> None:
    chunker = MarkdownChunker()
    text_body = (
        "This is a sample sentence about housing markets and affordability. "
        "Another detailed sentence covers compliance and funding cadence. "
        "The final sentence highlights reporting obligations and milestones."
    )
    content = "# Section One\n" + text_body

    chunks = chunker.chunk("doc-1", content)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert "Section: Section One" in chunk.contextual_text
    assert "Propositions:" in chunk.contextual_text
    assert "Hypothesis:" in chunk.contextual_text
    assert "Content:" in chunk.contextual_text
    assert chunk.propositions, "Contextual chunking should emit propositions"


def test_output_dimension_mismatch_rejected() -> None:
    pipeline = IngestionPipeline(_make_settings())
    with pytest.raises(IngestionError):
        pipeline._resolve_output_dimension(2048)


def test_chunk_metadata_preserves_publication_year() -> None:
    payload = {"publication_year": 2018, "other": "value"}
    embedding_meta = {"model": "voyage-context-3", "output_dimension": 1024}
    chunk_strategy = {"method": "unit-test"}

    result = IngestionPipeline._chunk_metadata(
        payload,
        embedding_meta=embedding_meta,
        chunk_strategy=chunk_strategy,
    )

    assert result["publication_year"] == 2018
    assert result["ingestion"]["embedding"] == embedding_meta
