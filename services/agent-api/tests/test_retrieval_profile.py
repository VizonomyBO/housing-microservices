from types import SimpleNamespace

from agent_api.agent.runner import _cap_answer_length
from agent_api.services.retrieval import RetrievalProfile, RetrievalService
from agent_api.services.retrieval_scope import DocumentSummary


def _make_service() -> RetrievalService:
    return RetrievalService(
        scope_repo=SimpleNamespace(),
        embedding_client=SimpleNamespace(),
        rerank_client=SimpleNamespace(),
        chat_client=SimpleNamespace(),
    )


def test_apply_profile_filters_drops_pre_2000_metadata():
    service = _make_service()
    summaries = {
        "old": DocumentSummary(
            document_id="old",
            canonical_name=None,
            access_scope="base",
            country_code="MEX",
            language=None,
            status="active",
            tags=[],
            metadata={"publication_year": 1999},
        ),
        "new": DocumentSummary(
            document_id="new",
            canonical_name=None,
            access_scope="base",
            country_code="MEX",
            language=None,
            status="active",
            tags=[],
            metadata={"publication_year": 2005},
        ),
    }
    filtered = service._apply_profile_filters(
        doc_ids=["old", "new", "unknown"],
        summaries=summaries,
        profile=RetrievalProfile.COUNTRY_PROFILE,
    )
    assert "old" not in filtered
    assert "new" in filtered
    # Unknown summaries should be retained rather than dropped silently.
    assert "unknown" in filtered


def test_build_geo_weight_map_prioritizes_country_region_and_global():
    service = _make_service()
    summaries = {
        "country": DocumentSummary(
            document_id="country",
            canonical_name=None,
            access_scope="base",
            country_code="PER",
            language=None,
            status="active",
            tags=[],
            metadata=None,
        ),
        "region": DocumentSummary(
            document_id="region",
            canonical_name=None,
            access_scope="base",
            country_code="LAC",
            language=None,
            status="active",
            tags=[],
            metadata=None,
        ),
        "global": DocumentSummary(
            document_id="global",
            canonical_name=None,
            access_scope="base",
            country_code="GLO",
            language=None,
            status="active",
            tags=[],
            metadata=None,
        ),
        "other": DocumentSummary(
            document_id="other",
            canonical_name=None,
            access_scope="base",
            country_code="NGA",
            language=None,
            status="active",
            tags=[],
            metadata=None,
        ),
    }
    weights = service._build_geo_weight_map(summaries, target_country="PER")
    assert weights["country"] == 1.3
    assert weights["region"] == 1.1
    assert weights["global"] == 0.9
    assert weights["other"] == 1.0


def test_cap_answer_length_prefers_sentence_breaks_and_preserves_citations():
    content = (
        "First sentence. Second sentence with cite [c1]. Third sentence with cite [c2] trailing text."
    )
    limit = content.find("[c2") + 2  # Force truncation inside the final citation
    trimmed = _cap_answer_length(content, limit)
    assert len(trimmed) <= limit
    assert "[c2" not in trimmed
    assert trimmed.endswith("]") or trimmed.endswith(".")
