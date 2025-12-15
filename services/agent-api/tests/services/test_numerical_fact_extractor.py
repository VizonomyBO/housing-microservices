from __future__ import annotations

import pytest

from models.retrieval import AttachmentDocument, AttachmentDocumentChunk
from services.numerical_fact_extractor import NumericFactExtractor


class StubLLMClient:
    async def complete(
        self, messages, *, temperature, max_tokens
    ):  # pragma: no cover - stub signature
        return """```json\n[{\"label\":\"Revenue Q1\",\"value\":12.5,\"unit\":\"m\",\"raw\":\"Revenue was 12.5m\"}]\n```"""


@pytest.mark.asyncio
async def test_numeric_fact_extractor_parses_llm_payload():
    extractor = NumericFactExtractor(client=StubLLMClient())
    document = AttachmentDocument(
        document_id="doc-1",
        canonical_name="Ledger",
        access_scope="base",
        chunks=[AttachmentDocumentChunk(chunk_id="chunk-1", text="Revenue was 12.5m last quarter")],
    )

    facts = await extractor.extract(document)

    assert facts
    row = facts[0].to_row()
    assert row["label"] == "Revenue Q1"
    assert row["value"] == 12.5
    assert row["unit"] == "m"
    assert row["source_chunk"] == "chunk-1"


@pytest.mark.asyncio
async def test_numeric_fact_extractor_falls_back_to_regex_without_llm():
    extractor = NumericFactExtractor(client=None)
    document = AttachmentDocument(
        document_id="doc-2",
        canonical_name="Notes",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="chunk-2", text="Arrears balance is 1,200 dollars total"
            )
        ],
    )

    facts = await extractor.extract(document)

    assert facts
    row = facts[0].to_row()
    assert row["value"] == 1200
    assert row["source_doc"] == "doc-2"
    assert row["source_chunk"] == "chunk-2"
