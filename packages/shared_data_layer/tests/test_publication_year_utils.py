from shared_data_layer.utils.publication_year import (
    coerce_publication_year,
    extract_years_from_text,
    normalize_metadata_publication_year,
)


def test_coerce_publication_year_accepts_int_and_str() -> None:
    assert coerce_publication_year(2016) == 2016
    assert coerce_publication_year("2016") == 2016
    assert coerce_publication_year("report_2016_final.pdf") == 2016


def test_coerce_publication_year_rejects_out_of_range_and_bool() -> None:
    assert coerce_publication_year(True) is None
    assert coerce_publication_year("1499") is None


def test_normalize_metadata_publication_year_sets_and_cleans() -> None:
    cleaned, year, provided = normalize_metadata_publication_year(
        {"publication_year": "2020", "other": "value"}
    )
    assert cleaned["publication_year"] == 2020
    assert year == 2020
    assert provided is True

    cleaned_blank, year_blank, provided_blank = normalize_metadata_publication_year(
        {"publication_year": " "}
    )
    assert "publication_year" not in cleaned_blank
    assert year_blank is None
    assert provided_blank is True


def test_extract_years_from_text_dedupes_and_sorts() -> None:
    assert extract_years_from_text("summary_2018_final_2018 2021") == [2018, 2021]
    assert extract_years_from_text(None) == []
