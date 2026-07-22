from lexiforge.analyse import analyse_candidates
from lexiforge.models import ValidationResult
from lexiforge.report import render_analysis_markdown, render_json


def test_analysis_counts(nb_records, nb_profile) -> None:
    report = analyse_candidates(nb_records, nb_profile, ValidationResult())
    assert report["total_records"] == 8
    assert report["unique_normalized_words"] == 8
    assert report["records_by_status"]["approved"] == 6
    assert report["character_frequency"]["å"] == 1
    assert report["words_with_non_ascii_letters"] == 3


def test_analysis_rendering_is_deterministic(nb_records, nb_profile) -> None:
    report = analyse_candidates(nb_records, nb_profile, ValidationResult())
    assert render_json(report) == render_json(report)
    assert render_analysis_markdown(report).endswith("\n")
