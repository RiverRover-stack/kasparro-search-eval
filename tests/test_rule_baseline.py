from __future__ import annotations

from tools.rule_baseline import baseline_labels


def test_absent_brand_gives_all_false_and_no_position() -> None:
    labels = baseline_labels("1. Acme is great.\n2. Other tools exist.")

    assert labels == {
        "brand_mentioned": False,
        "recommended": False,
        "negative_characterization": False,
        "observable_position": None,
    }


def test_plain_mention_is_not_recommended_or_negative() -> None:
    labels = baseline_labels("Kasparro is a company.")

    assert labels["brand_mentioned"] is True
    assert labels["recommended"] is False
    assert labels["negative_characterization"] is False


def test_mention_is_case_insensitive() -> None:
    assert baseline_labels("KASPARRO exists.")["brand_mentioned"] is True


def test_recommend_cue_must_be_in_a_brand_sentence() -> None:
    other_sentence = baseline_labels("Kasparro exists. We recommend Acme.")
    same_sentence = baseline_labels("We recommend Kasparro for this.")

    assert other_sentence["recommended"] is False
    assert same_sentence["recommended"] is True


def test_negative_cue_in_brand_sentence() -> None:
    labels = baseline_labels("There is limited public detail on Kasparro.\nAcme is solid.")

    assert labels["negative_characterization"] is True
    assert labels["recommended"] is False


def test_negative_cue_in_another_line_is_ignored() -> None:
    labels = baseline_labels("Kasparro is listed.\nAcme has a lack of features.")

    assert labels["negative_characterization"] is False


def test_position_is_number_of_first_brand_list_line() -> None:
    text = "Top tools:\n1. Acme\n2. Kasparro helps\n3. Kasparro again"
    assert baseline_labels(text)["observable_position"] == 2


def test_position_accepts_bullet_and_heading_prefixes() -> None:
    assert baseline_labels("- 3. Kasparro")["observable_position"] == 3
    assert baseline_labels("## 4) Kasparro")["observable_position"] == 4


def test_position_none_when_brand_not_in_numbered_line() -> None:
    assert baseline_labels("1. Acme\nKasparro is mentioned here.")["observable_position"] is None
