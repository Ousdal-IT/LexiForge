import xml.etree.ElementTree as ET
from pathlib import Path

from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.curation import build_curation_report, load_curation_data
from lexiforge.dataset import (
    balanced_selection,
    compare_languages,
    dataset_statistics,
    optimisation_report,
    release_plan,
)
from lexiforge.publication import publish_reports, render_dataset_html
from lexiforge.visualise import bar_chart_svg

runner = CliRunner()


def directory_bytes(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_extended_dataset_statistics() -> None:
    statistics = dataset_statistics("nb")
    assert statistics["total_records"] == 24
    assert sum(statistics["word_length_histogram"].values()) == 24
    assert sum(statistics["first_letter_frequency"].values()) == 24
    assert sum(statistics["last_letter_frequency"].values()) == 24
    assert statistics["bigram_frequency"]
    assert statistics["trigram_frequency"]
    assert 0 < statistics["vowel_consonant_statistics"]["vowel_ratio"] < 1
    assert statistics["release_eligibility"]["eligible"] == 16


def test_statistics_are_deterministic() -> None:
    assert dataset_statistics("en") == dataset_statistics("en")


def test_optimisation_is_advisory_and_deterministic() -> None:
    source = Path("data/languages/nb/candidates.csv")
    before = source.read_bytes()
    first = optimisation_report("nb")
    assert first == optimisation_report("nb")
    assert first["suggestions"]
    assert source.read_bytes() == before


def test_release_planner_reports_gaps() -> None:
    plan = release_plan("nb")
    assert plan["target_size"] == 2048
    assert plan["eligible_count"] == 16
    assert plan["missing_count"] == 2032
    assert not plan["ready"]
    assert set(plan["category_needs"]) == {
        "actions",
        "animals",
        "food",
        "household",
        "nature",
        "qualities",
    }


def test_language_comparison_is_structural() -> None:
    comparison = compare_languages("nb", "nn")
    assert comparison["languages"] == ["nb", "nn"]
    assert comparison["comparison"]["nb"]["candidate_count"] == 24
    assert "no_semantic" in comparison["scope"]


def test_balanced_selection_is_deterministic() -> None:
    _, candidates, _, _ = load_curation_data("nb")
    eligible = set(build_curation_report("nb")["release_eligible_ids"])
    records = [item for item in candidates if item.candidate.id in eligible]
    first = balanced_selection(records, "nb", 8)
    second = balanced_selection(records, "nb", 8)
    assert [item.candidate.id for item in first] == [item.candidate.id for item in second]
    assert len({item.candidate.category for item in first}) >= 5


def test_svg_is_deterministic_valid_xml_and_escaped() -> None:
    first = bar_chart_svg("A & B", {"<x>": 2, "y": 1})
    assert first == bar_chart_svg("A & B", {"y": 1, "<x>": 2})
    root = ET.fromstring(first)
    assert root.tag.endswith("svg")
    assert "&amp;" in first and "&lt;x&gt;" in first
    assert "javascript" not in first.lower()


def test_html_report_is_static_and_deterministic() -> None:
    statistics = dataset_statistics("en")
    plan = release_plan("en")
    first = render_dataset_html(statistics, plan)
    assert first == render_dataset_html(statistics, plan)
    assert first.startswith("<!doctype html>\n")
    assert "<script" not in first
    assert "Development data only" in first


def test_publication_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert len(publish_reports(first)) == 22
    assert len(publish_reports(second)) == 22
    assert directory_bytes(first) == directory_bytes(second)


def test_m2_cli_commands() -> None:
    assert runner.invoke(app, ["optimise", "--all"]).exit_code == 0
    assert runner.invoke(app, ["compare", "nb", "nn"]).exit_code == 0
    assert runner.invoke(app, ["release", "plan"]).exit_code == 0
    analysis = runner.invoke(app, ["analyse", "--language", "nb", "--format", "json"])
    assert analysis.exit_code == 0 and '"bigram_frequency"' in analysis.stdout


def test_balanced_build_is_reproducible(tmp_path: Path) -> None:
    outputs = []
    for name in ("first", "second"):
        directory = tmp_path / name
        result = runner.invoke(
            app,
            [
                "build",
                "--language",
                "nb",
                "--size",
                "16",
                "--allow-development-size",
                "--balanced",
                "--output-dir",
                str(directory),
            ],
        )
        assert result.exit_code == 0
        outputs.append(directory_bytes(directory))
    assert outputs[0] == outputs[1]
