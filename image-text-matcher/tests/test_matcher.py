from app.matching.matcher import (
    MatchPolicy,
    build_candidates,
    looks_like_alcohol_declaration,
    match_targets,
    normalize_alcohol_text,
)
from app.models import OCRTextBox


def box(text: str, confidence: float, left: float, top: float, right: float, bottom: float) -> OCRTextBox:
    return OCRTextBox(
        text=text,
        confidence=confidence,
        bbox=[[left, top], [right, top], [right, bottom], [left, bottom]],
    )


def test_match_single_box_with_ocr_confusion() -> None:
    results = match_targets([box("ACME-449I", 0.94, 120, 45, 260, 83)], ["ACME-4491"])

    assert results[0].found is True
    assert results[0].matched_text == "ACME-449I"
    assert results[0].candidate_source == "single_box"
    assert results[0].bbox is not None


def test_match_line_group() -> None:
    ocr_boxes = [
        box("INSPECTION", 0.92, 88, 220, 250, 265),
        box("PASSED", 0.90, 260, 222, 390, 265),
    ]

    results = match_targets(ocr_boxes, ["Inspection Passed"])

    assert results[0].found is True
    assert results[0].matched_text == "INSPECTION PASSED"
    assert results[0].candidate_source == "line_group"
    assert results[0].ocr_confidence == 0.91
    assert results[0].bbox == [[88.0, 220.0], [390.0, 220.0], [390.0, 265.0], [88.0, 265.0]]


def test_match_below_threshold_is_not_found_and_keeps_candidate_bbox() -> None:
    results = match_targets([box("unrelated", 0.8, 0, 0, 10, 10)], ["Serial Number"], match_threshold=95)

    assert results[0].found is False
    assert results[0].closest_text == "unrelated"
    assert results[0].bbox == [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]


def test_match_multi_word_phrase_when_words_are_split_across_boxes() -> None:
    ocr_boxes = [
        box("INSPE", 0.95, 88, 220, 145, 265),
        box("CTION", 0.94, 147, 220, 225, 265),
        box("PAS", 0.93, 260, 222, 305, 265),
        box("SED", 0.92, 307, 222, 355, 265),
    ]

    results = match_targets(ocr_boxes, ["Inspection Passed"])

    assert results[0].found is True
    assert results[0].matched_text == "INSPECTION PASSED"
    assert results[0].candidate_source in {"line_group", "adjacent_group"}
    assert results[0].bbox == [[88.0, 220.0], [355.0, 220.0], [355.0, 265.0], [88.0, 265.0]]


def test_build_candidates_merges_irregular_box_bounds() -> None:
    ocr_boxes = [
        OCRTextBox(
            text="Serial",
            confidence=0.9,
            bbox=[[12, 22], [48, 18], [52, 41], [10, 45]],
        ),
        OCRTextBox(
            text="Number",
            confidence=0.88,
            bbox=[[58, 20], [110, 19], [112, 44], [56, 46]],
        ),
    ]

    candidates = build_candidates(ocr_boxes, targets=["Serial Number"])
    grouped = next(
        candidate
        for candidate in candidates
        if candidate.source == "line_group" and candidate.text == "Serial Number"
    )

    assert grouped.bbox == [[10.0, 18.0], [112.0, 18.0], [112.0, 46.0], [10.0, 46.0]]


def test_word_match_checks_later_occurrences() -> None:
    ocr_boxes = [
        box("Casper", 0.91, 10, 10, 90, 35),
        box("Premium Lager Beer", 0.96, 10, 50, 250, 78),
    ]

    results = match_targets(
        ocr_boxes,
        ["Lager"],
        policies=[MatchPolicy(field="classType", mode="contains", max_lines=1)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "Premium Lager Beer"
    assert results[0].closest_text is None


def test_failed_match_reports_closest_text_separately() -> None:
    results = match_targets(
        [box("Casper", 0.91, 10, 10, 90, 35)],
        ["Lager"],
        match_threshold=95,
        policies=[MatchPolicy(field="classType", mode="contains", max_lines=1)],
    )

    assert results[0].found is False
    assert results[0].matched_text is None
    assert results[0].closest_text == "Casper"


def test_exactish_field_can_match_across_two_lines() -> None:
    ocr_boxes = [
        box("750", 0.94, 10, 10, 70, 35),
        box("ML", 0.93, 10, 45, 50, 70),
    ]

    results = match_targets(
        ocr_boxes,
        ["750 ml"],
        policies=[MatchPolicy(field="netContents", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "750 ML"
    assert results[0].candidate_source == "cross_line_group"


def test_address_can_match_expected_substring_across_two_lines() -> None:
    ocr_boxes = [
        box("BREWED AND CANNED BY OLD IRVING BREWING CO", 0.95, 10, 10, 500, 35),
        box("4415-19 W MONTROSE AVE.CHICAGO.IL 60641", 0.93, 10, 45, 500, 70),
    ]

    results = match_targets(
        ocr_boxes,
        ["OLD IRVING BREWING CO. 4415-19 W MONTROSE AVE, CHICAGO, IL 60641"],
        policies=[MatchPolicy(field="address", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].candidate_source == "cross_line_group"


def test_address_matches_compact_producer_line_with_phone_suffix() -> None:
    ocr_boxes = [
        box("PRODUCED &BOTTLED BYLECOLE NO41", 0.93, 496, 406, 675, 420),
        box("LOWDEN.WASHINGTON509.525.0940WWW.LECOLE.COM", 0.94, 448, 424, 728, 438),
    ]

    results = match_targets(
        ocr_boxes,
        ["L'Ecole No 41 Lowden, Washington"],
        policies=[MatchPolicy(field="address", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == (
        "PRODUCED &BOTTLED BYLECOLE NO41 "
        "LOWDEN.WASHINGTON509.525.0940WWW.LECOLE.COM"
    )
    assert results[0].score == 96.0


def test_separator_split_candidate_matches_left_side_of_combined_text() -> None:
    results = match_targets(
        [box("1PINT-7%ALC./VOL.", 0.92, 10, 10, 170, 35)],
        ["1 Pint"],
        policies=[MatchPolicy(field="netContents", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "1PINT"
    assert results[0].candidate_source == "split_text"


def test_separator_split_candidate_matches_right_side_of_combined_text() -> None:
    results = match_targets(
        [box("1PINT-7%ALC./VOL.", 0.92, 10, 10, 170, 35)],
        ["7% Alc./Vol."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "7%ALC./VOL."
    assert results[0].candidate_source == "split_text"


def test_exactish_field_matches_horizontally_aligned_stacked_lines() -> None:
    ocr_boxes = [
        box("5.0%", 0.94, 700, 10, 750, 35),
        box("5.0%", 0.93, 900, 10, 950, 35),
        box("Alc.by Vol.", 0.92, 700, 45, 780, 70),
        box("Alc.by Vol.", 0.91, 900, 45, 980, 70),
    ]

    results = match_targets(
        ocr_boxes,
        ["5.0% Alc. by Vol."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "5.0% Alc.by Vol."
    assert results[0].candidate_source == "cross_line_group"


def test_alcohol_normalization_ignores_optional_by_and_joined_punctuation() -> None:
    assert normalize_alcohol_text("Alc. 4.4% WT. 5.5% by Vol.") == "alc 4.4 wt 5.5 vol"
    assert (
        normalize_alcohol_text("ALC.4.4%by WT.5.5%by VOL.0.355 Litres")
        == "alc 4.4 wt 5.5 vol 0.355"
    )


def test_alcohol_declaration_matches_joined_ocr_with_trailing_label_text() -> None:
    results = match_targets(
        [box("ALC.4.4%by WT.5.5%by VOL.0.355 Litres", 0.95, 10, 10, 360, 35)],
        ["Alc. 4.4% WT. 5.5% by Vol."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].score == 100.0
    assert results[0].matched_text == "ALC.4.4%by WT.5.5%by VOL.0.355 Litres"


def test_alcohol_declaration_matches_by_before_weight_and_volume() -> None:
    results = match_targets(
        [box("ALC. 4.4% by WT. 5.5% by VOL.", 0.95, 10, 10, 320, 35)],
        ["Alc. 4.4% WT. 5.5% by Vol."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].score == 100.0


def test_alcohol_declaration_matches_joined_by_tokens() -> None:
    results = match_targets(
        [box("ALC.4.4%by WT.5.5%by VOL.", 0.95, 10, 10, 280, 35)],
        ["Alc. 4.4% WT. 5.5% by Vol."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].score == 100.0


def test_alcohol_declaration_matches_case_insensitive_variant() -> None:
    results = match_targets(
        [box("alc.4.4%BY wt.5.5%BY vol.", 0.95, 10, 10, 280, 35)],
        ["ALC. 4.4% wt. 5.5% BY VOL."],
        policies=[MatchPolicy(field="alcohol", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].score == 100.0


def test_alcohol_normalization_is_scoped_to_alcohol_policy() -> None:
    results = match_targets(
        [box("ALC.4.4%by WT.5.5%by VOL.0.355 Litres", 0.95, 10, 10, 360, 35)],
        ["Alc. 4.4% WT. 5.5% by Vol."],
        match_threshold=95,
        policies=[MatchPolicy(field="netContents", mode="exactish", max_lines=2)],
    )

    assert looks_like_alcohol_declaration("ALC.4.4%by WT.5.5%by VOL.0.355 Litres") is True
    assert results[0].found is False
    assert results[0].score < 95.0


def test_exactish_field_matches_when_expected_is_substring_of_candidate() -> None:
    results = match_targets(
        [box("Product of France", 0.95, 10, 10, 180, 35)],
        ["France"],
        policies=[MatchPolicy(field="origin", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "Product of France"
    assert results[0].score == 98.0


def test_exactish_field_prefers_tighter_equal_score_candidate() -> None:
    ocr_boxes = [
        box(
            "Gaps Crown vineyard located at the southern end of the Sonoma Coast appellation",
            0.95,
            350,
            10,
            780,
            35,
        ),
        box("SONOMA COAST - SONOMA COUNTY", 0.93, 10, 85, 240, 110),
    ]

    results = match_targets(
        ocr_boxes,
        ["Sonoma Coast"],
        policies=[MatchPolicy(field="origin", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "SONOMA COAST"
    assert results[0].candidate_source == "split_text"
    assert results[0].score == 100.0


def test_exactish_field_matches_noisy_front_label_origin_fragment() -> None:
    results = match_targets(
        [box("NOMA.COUNTY", 0.95, 200, 380, 330, 400)],
        ["Sonoma County"],
        policies=[MatchPolicy(field="origin", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "NOMA.COUNTY"
    assert results[0].score >= 85.0


def test_exactish_field_matches_when_ocr_joins_expected_words_to_year() -> None:
    results = match_targets(
        [box("LAKE ERIE2021", 0.95, 10, 10, 180, 35)],
        ["Lake Erie"],
        policies=[MatchPolicy(field="appellation", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "LAKE ERIE2021"
    assert results[0].score == 98.0


def test_exactish_field_matches_when_ocr_joins_expected_words_without_spaces() -> None:
    results = match_targets(
        [box("LAKEERIE2021", 0.95, 10, 10, 180, 35)],
        ["Lake Erie"],
        policies=[MatchPolicy(field="appellation", mode="exactish", max_lines=2)],
    )

    assert results[0].found is True
    assert results[0].matched_text == "LAKEERIE2021"
    assert results[0].score == 98.0


def test_exactish_one_line_field_does_not_match_across_two_lines() -> None:
    ocr_boxes = [
        box("123", 0.94, 10, 10, 70, 35),
        box("Main", 0.93, 10, 45, 80, 70),
    ]

    results = match_targets(
        ocr_boxes,
        ["123 Main"],
        policies=[MatchPolicy(field="address", mode="exactish", max_lines=1)],
    )

    assert results[0].found is False
    assert results[0].matched_text is None


def test_loose_field_can_match_multiline_warning_text() -> None:
    ocr_boxes = [
        box("Government Warning", 0.94, 10, 10, 220, 35),
        box("according to the surgeon general", 0.92, 10, 45, 360, 70),
    ]

    results = match_targets(
        ocr_boxes,
        ["government warning according to the surgeon general"],
        policies=[MatchPolicy(field="warning", mode="loose", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].candidate_source in {"cross_line_group", "full_text"}


def test_warning_field_matches_anchor_and_required_clauses_when_ocr_misses_tail() -> None:
    ocr_boxes = [
        box("GOVERNMENT WARNING:(1) ACCORDING TO THE SURGEON GENERAL WOMEN SHOULD", 0.94, 10, 10, 360, 25),
        box("NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF", 0.93, 10, 26, 360, 41),
        box("BIRTH DEFECTS (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY", 0.92, 10, 42, 360, 57),
    ]
    warning = (
        "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
        "or operate machinery, and may cause health problems."
    )

    results = match_targets(
        ocr_boxes,
        [warning],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].score >= 85.0
    assert "GOVERNMENT WARNING" in results[0].matched_text


def test_warning_field_trims_unrelated_text_from_display_match() -> None:
    ocr_boxes = [
        box("BREWED AND PACKED BY EXAMPLE CELLARS", 0.95, 10, 10, 380, 25),
        box(
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink",
            0.94,
            10,
            40,
            520,
            55,
        ),
        box(
            "alcoholic beverages during pregnancy because of the risk of birth defects.",
            0.93,
            10,
            56,
            500,
            71,
        ),
        box(
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery,",
            0.92,
            10,
            72,
            600,
            87,
        ),
        box(
            "and may cause health problems. Visit our tasting room for events and pairings.",
            0.91,
            10,
            88,
            560,
            103,
        ),
    ]
    warning = (
        "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
        "or operate machinery, and may cause health problems."
    )

    results = match_targets(
        ocr_boxes,
        [warning],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].matched_text.startswith("GOVERNMENT WARNING")
    assert "health problems" in results[0].matched_text
    assert "Visit our tasting room" not in results[0].matched_text


def test_warning_field_trims_to_raw_anchor_after_noisy_prefix() -> None:
    ocr_boxes = [
        box(
            "OTNOIE 2015PINOTNOI GOVERNMENT WARNING:(1)ACCORDING TO THE SURGEON GENERAL "
            "WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE "
            "RISK OF BIRTH DEFECTS.(2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR "
            "ABILITY TO DRIVE A CAR OR OPERATE MACHINERY AND MAY CAUSE HEALTH PROBLEMS.",
            0.92,
            10,
            10,
            700,
            35,
        )
    ]
    warning = (
        "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
        "or operate machinery, and may cause health problems."
    )

    results = match_targets(
        ocr_boxes,
        [warning],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].matched_text.startswith("GOVERNMENT WARNING")
    assert "OTNOIE" not in results[0].matched_text


def test_warning_field_matches_truncated_government_anchor_with_legal_fragments() -> None:
    ocr_boxes = [
        box(
            "ENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL WOMEN "
            "RINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK "
            "ECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR "
            "VE A CAR OR OPERATE MACHINERY AND MAY CAUSE HEALTH PROBLEMS.",
            0.95,
            10,
            10,
            700,
            35,
        )
    ]
    warning = (
        "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
        "or operate machinery, and may cause health problems."
    )

    results = match_targets(
        ocr_boxes,
        [warning],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].score >= 85.0


def test_warning_field_does_not_match_without_anchor() -> None:
    ocr_boxes = [
        box("ACCORDING TO THE SURGEON GENERAL WOMEN SHOULD NOT DRINK", 0.94, 10, 10, 330, 25),
        box("ALCOHOLIC BEVERAGES DURING PREGNANCY", 0.93, 10, 26, 250, 41),
    ]

    results = match_targets(
        ocr_boxes,
        ["GOVERNMENT WARNING: According to the Surgeon General"],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is False
    assert results[0].matched_text is None


def test_warning_field_matches_noisy_government_anchor_fragments() -> None:
    ocr_boxes = [
        box("GOVERNM", 0.93, 10, 10, 120, 25),
        box("DRINK ALC", 0.92, 10, 26, 130, 41),
        box("MACHINERY", 0.91, 10, 42, 150, 57),
    ]

    results = match_targets(
        ocr_boxes,
        ["GOVERNMENT WARNING: women should not drink alcoholic beverages and operate machinery"],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
    assert results[0].score >= 85.0


def test_warning_field_does_not_match_single_character_fuzzy_anchor_false_positive() -> None:
    for text in ["A", "I"]:
        results = match_targets(
            [box(text, 0.95, 10, 10, 20, 20)],
            ["GOVERNMENT WARNING: women should not drink alcoholic beverages"],
            policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
        )

        assert results[0].found is False
        assert results[0].score == 0.0


def test_warning_field_matches_fuzzy_anchor_when_candidate_is_meaningful() -> None:
    results = match_targets(
        [
            box(
                "GOVERNNENT WARNlNG ACCORDING TO THE SURGEON GENERAL WOMEN SHOULD NOT DRINK",
                0.95,
                10,
                10,
                520,
                25,
            )
        ],
        ["GOVERNMENT WARNING: According to the Surgeon General women should not drink"],
        policies=[MatchPolicy(field="warning", mode="warning", max_lines=None)],
    )

    assert results[0].found is True
