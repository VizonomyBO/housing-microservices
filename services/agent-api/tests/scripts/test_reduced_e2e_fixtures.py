from __future__ import annotations

import pytest

from scripts.reduced_e2e_fixtures import (
    FixtureLoader,
    list_document_aliases,
    sha256_file,
)


@pytest.fixture(scope="module")
def loader() -> FixtureLoader:
    return FixtureLoader()


def test_manifest_documents_and_prompts_loaded(loader: FixtureLoader) -> None:
    aliases = [doc.spec.alias for doc in loader.documents()]
    assert aliases == ["DOC_POLICY", "DOC_LEDGER", "DOC_KPI"]

    policy = loader.get_document("DOC_POLICY")
    assert policy.spec.canonical_name.startswith("Metro Housing")
    assert policy.spec.metadata["document_alias"] == "DOC_POLICY"
    assert "reduced_e2e" in policy.spec.tags

    prompt_ids = [prompt.id for prompt in loader.prompts()]
    assert prompt_ids == ["Q_SIMPLE_QA", "Q_REASON", "Q_AGGREGATE", "Q_SQL"]


def test_documents_for_prompt(loader: FixtureLoader) -> None:
    docs = loader.documents_for_prompt("Q_REASON")
    assert [doc.spec.alias for doc in docs] == ["DOC_POLICY", "DOC_LEDGER"]

    with pytest.raises(KeyError):
        loader.documents_for_prompt("unknown")


def test_numeric_expectations_present(loader: FixtureLoader) -> None:
    ledger = loader.get_document("DOC_LEDGER")
    expectations = ledger.spec.numerical_expectations
    assert expectations is not None
    assert expectations["total_usd"] == 7_350_000
    assert expectations["highlight_city"] == "District 9"


def test_sha256_helper_matches_fixture(loader: FixtureLoader) -> None:
    policy_path = loader.get_document("DOC_POLICY").path
    digest_one = sha256_file(policy_path)
    digest_two = sha256_file(policy_path)
    assert digest_one == digest_two
    assert digest_one == loader.get_document("DOC_POLICY").content_hash


def test_list_document_aliases() -> None:
    aliases = list_document_aliases()
    assert aliases == ("DOC_POLICY", "DOC_LEDGER", "DOC_KPI")


def test_prompt_validation_rules_preserved(loader: FixtureLoader) -> None:
    simple_prompt = loader.get_prompt("Q_SIMPLE_QA")
    regex_rules = [rule for rule in simple_prompt.validation_rules if rule.type == "regex"]
    assert len(regex_rules) == 2
    patterns = {rule.pattern for rule in regex_rules}
    assert {"five\\s+districts", "32%"}.issubset(patterns)

    aggregate_prompt = loader.get_prompt("Q_AGGREGATE")
    keywords = next(rule for rule in aggregate_prompt.validation_rules if rule.type == "keyword")
    assert "District 9" in keywords.values
