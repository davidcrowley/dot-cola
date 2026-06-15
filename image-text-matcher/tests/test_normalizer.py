from app.matching.normalizer import normalize_text


def test_normalize_text_lowercases_and_collapses_spaces() -> None:
    assert normalize_text("  Inspection   Passed  ") == "inspection passed"


def test_normalize_text_can_normalize_careful_identifier_confusions() -> None:
    assert normalize_text("ACME-O49I", normalize_ocr_confusions=True) == "acme-0491"


def test_normalize_text_does_not_change_words_by_default() -> None:
    assert normalize_text("I love O rings") == "i love o rings"

