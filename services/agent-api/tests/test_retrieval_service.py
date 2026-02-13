import pytest

from agent_api.http.errors import GatewayError
from agent_api.services.retrieval import RetrievalService, RetrievedChunk


class _FakeScopeRepo:
    def __init__(self, chunks):
        self._chunks = chunks

    async def list_conversation_documents(self, conversation_id: str):
        return [
            type(
                "Att",
                (),
                {
                    "document_id": "doc1",
                    "attach_source": "test",
                    "role": "primary",
                    "visibility": "visible",
                    "canonical_name": "doc1",
                    "access_scope": "user_private",
                    "country_code": "USA",
                    "metadata": {},
                },
            )()
        ]

    async def hydrate_documents(self, ids):
        return {
            "doc1": type(
                "Summary",
                (),
                {
                    "status": "active",
                    "canonical_name": "doc1",
                    "access_scope": "user_private",
                    "country_code": "USA",
                    "language": "en",
                    "tags": [],
                    "metadata": {},
                },
            )()
        }

    async def load_document_chunk_previews(self, *args, **kwargs):
        return {}

    async def hybrid_chunk_search(
        self, *, query, document_ids, embedding, top_k, hybrid_weight, chunk_types
    ):
        return {"doc1": self._chunks}


class _FakeEmbed:
    async def embed(self, texts):
        return [[0.1] * 4 for _ in texts]


class _FakeRerank:
    async def rerank(self, query, documents, top_k):
        return [1.0 for _ in documents]


class _FakeChat:
    async def complete(self, messages, temperature=0.3, max_tokens=128):
        return "rewrite one\nrewrite two"


@pytest.mark.asyncio
async def test_retrieval_builds_citations_without_network():
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc1",
        text="hello world",
        score=0.5,
        page_number=1,
        position=0,
        canonical_name="doc1",
    )
    service = RetrievalService(
        scope_repo=_FakeScopeRepo([chunk]),  # type: ignore[arg-type]
        embedding_client=_FakeEmbed(),  # type: ignore[arg-type]
        rerank_client=_FakeRerank(),  # type: ignore[arg-type]
        chat_client=_FakeChat(),  # type: ignore[arg-type]
        top_k=3,
    )

    ctx = await service.retrieve(user_query="hi", conversation_id="conv1")

    assert ctx.citations
    assert ctx.citations[0]["doc_id"] == "doc1"
    assert "hello world" in ctx.context_text
    assert ctx.citations[0]["text"] == "hello world"


@pytest.mark.asyncio
async def test_retrieval_raises_without_attachments():
    class EmptyScope(_FakeScopeRepo):
        async def list_conversation_documents(self, conversation_id: str):
            return []

    service = RetrievalService(
        scope_repo=EmptyScope([]),  # type: ignore[arg-type]
        embedding_client=_FakeEmbed(),  # type: ignore[arg-type]
        rerank_client=_FakeRerank(),  # type: ignore[arg-type]
        chat_client=_FakeChat(),  # type: ignore[arg-type]
        top_k=3,
    )

    with pytest.raises(GatewayError) as excinfo:
        await service.retrieve(user_query="hi", conversation_id="conv1")
    assert excinfo.value.code == "ATTACHMENTS_REQUIRED"


@pytest.mark.asyncio
async def test_default_profile_applies_geo_weighting():
    from agent_api.services.retrieval import RetrievalProfile

    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc1",
        text="USA content",
        score=0.5,
        page_number=1,
        position=0,
        canonical_name="doc1",
    )

    class MultiDocScope(_FakeScopeRepo):
        async def hydrate_documents(self, ids):
            return {
                "doc1": type(
                    "Summary",
                    (),
                    {
                        "status": "active",
                        "canonical_name": "USA Doc",
                        "country_code": "USA",
                        "metadata": {},
                    },
                )()
            }

    service = RetrievalService(
        scope_repo=MultiDocScope([chunk]),  # type: ignore[arg-type]
        embedding_client=_FakeEmbed(),  # type: ignore[arg-type]
        rerank_client=_FakeRerank(),  # type: ignore[arg-type]
        chat_client=_FakeChat(),  # type: ignore[arg-type]
        top_k=3,
    )

    ctx = await service.retrieve(
        user_query="hi",
        conversation_id="conv1",
        profile=RetrievalProfile.DEFAULT,
        target_country_code="USA",
    )

    assert ctx.citations
    assert len(ctx.citations) > 0


@pytest.mark.asyncio
async def test_country_profile_filters_old_documents():
    from agent_api.services.retrieval import RetrievalProfile

    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc1",
        text="old content",
        score=0.5,
        page_number=1,
        position=0,
        canonical_name="doc1",
    )

    class OldDocScope(_FakeScopeRepo):
        async def list_conversation_documents(self, conversation_id: str):
            return [
                type(
                    "Att",
                    (),
                    {
                        "document_id": "doc1",
                        "attach_source": "test",
                        "role": "primary",
                        "visibility": "visible",
                        "canonical_name": "doc1",
                        "access_scope": "user_private",
                        "country_code": "USA",
                        "metadata": {"publication_year": 1995},
                    },
                )()
            ]

        async def hydrate_documents(self, ids):
            return {
                "doc1": type(
                    "Summary",
                    (),
                    {
                        "status": "active",
                        "canonical_name": "Old Doc 1995",
                        "country_code": "USA",
                        "metadata": {"publication_year": 1995},
                    },
                )()
            }

    service = RetrievalService(
        scope_repo=OldDocScope([chunk]),  # type: ignore[arg-type]
        embedding_client=_FakeEmbed(),  # type: ignore[arg-type]
        rerank_client=_FakeRerank(),  # type: ignore[arg-type]
        chat_client=_FakeChat(),  # type: ignore[arg-type]
        top_k=3,
    )

    with pytest.raises(GatewayError) as excinfo:
        await service.retrieve(
            user_query="hi",
            conversation_id="conv1",
            profile=RetrievalProfile.COUNTRY_PROFILE,
        )
    assert excinfo.value.code == "NO_RESULTS"


@pytest.mark.asyncio
async def test_default_profile_includes_old_documents():
    from agent_api.services.retrieval import RetrievalProfile

    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc1",
        text="old content",
        score=0.5,
        page_number=1,
        position=0,
        canonical_name="doc1",
    )

    class OldDocScope(_FakeScopeRepo):
        async def list_conversation_documents(self, conversation_id: str):
            return [
                type(
                    "Att",
                    (),
                    {
                        "document_id": "doc1",
                        "attach_source": "test",
                        "role": "primary",
                        "visibility": "visible",
                        "canonical_name": "doc1",
                        "access_scope": "user_private",
                        "country_code": "USA",
                        "metadata": {"publication_year": 1995},
                    },
                )()
            ]

        async def hydrate_documents(self, ids):
            return {
                "doc1": type(
                    "Summary",
                    (),
                    {
                        "status": "active",
                        "canonical_name": "Old Doc 1995",
                        "country_code": "USA",
                        "metadata": {"publication_year": 1995},
                    },
                )()
            }

    service = RetrievalService(
        scope_repo=OldDocScope([chunk]),  # type: ignore[arg-type]
        embedding_client=_FakeEmbed(),  # type: ignore[arg-type]
        rerank_client=_FakeRerank(),  # type: ignore[arg-type]
        chat_client=_FakeChat(),  # type: ignore[arg-type]
        top_k=3,
    )

    ctx = await service.retrieve(
        user_query="hi",
        conversation_id="conv1",
        profile=RetrievalProfile.DEFAULT,
    )

    assert ctx.citations
    assert len(ctx.citations) > 0
    assert ctx.citations[0]["text"] == "old content"
