from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from lexiforge.atomic import atomic_write_text
from lexiforge.batch import import_candidate_batch, stable_candidate_id
from lexiforge.blocklists import load_blocklists_with_metadata
from lexiforge.cli import app
from lexiforge.curation import (
    build_curation_report,
    evaluate_release_eligibility,
    load_curation_data,
)
from lexiforge.errors import ValidationFailure
from lexiforge.models import (
    CandidateStatus,
    CriterionValue,
    ProvenanceRecord,
    ReviewCriteria,
    SourceType,
)
from lexiforge.moderation import latest_reviews, required_criteria_resolved
from lexiforge.scoring import score_candidate
from lexiforge.similarity import damerau_levenshtein, find_similar_words
from lexiforge.transitions import validate_transition

runner = CliRunner()


def yes_criteria() -> ReviewCriteria:
    return ReviewCriteria.model_validate({name: "yes" for name in ReviewCriteria.model_fields})


def test_development_curation_data_is_complete() -> None:
    for code in ("nb", "nn", "en"):
        _, candidates, provenance, reviews = load_curation_data(code)
        assert len(candidates) == 24
        assert len(provenance) == 24
        assert len(reviews) == 16


def test_third_party_provenance_requires_reference() -> None:
    with pytest.raises(ValidationError, match="source reference"):
        ProvenanceRecord(
            id="p1",
            candidate_id="c1",
            source_kind="third_party",
            contributor_assertion="derived",
            license_basis="unknown",
            independently_contributed=False,
            bulk_source=True,
        )


def test_bulk_cannot_be_independent() -> None:
    with pytest.raises(ValidationError, match="bulk"):
        ProvenanceRecord(
            id="p1",
            candidate_id="c1",
            source_kind="manual",
            contributor_assertion="test",
            license_basis="project",
            independently_contributed=True,
            bulk_source=True,
        )


@pytest.mark.parametrize(
    "previous,new",
    [
        ("submitted", "needs_review"),
        ("submitted", "rejected"),
        ("needs_review", "approved"),
        ("approved", "superseded"),
        ("approved", "withdrawn"),
        ("rejected", "needs_review"),
    ],
)
def test_allowed_transitions(previous: str, new: str) -> None:
    validate_transition(CandidateStatus(previous), CandidateStatus(new))


def test_invalid_and_override_transitions() -> None:
    with pytest.raises(ValidationFailure):
        validate_transition(CandidateStatus.AUTOMATIC_REJECT, CandidateStatus.APPROVED)
    validate_transition(
        CandidateStatus.AUTOMATIC_REJECT, CandidateStatus.NEEDS_REVIEW, override=True
    )


@pytest.mark.parametrize(
    "left,right,distance", [("bake", "bakke", 1), ("form", "from", 1), ("trail", "trial", 1)]
)
def test_damerau_similarity(left: str, right: str, distance: int) -> None:
    assert damerau_levenshtein(left, right) == distance


def test_similarity_pairs_are_stable_and_not_reversed() -> None:
    profile, candidates, _, _ = load_curation_data("en")
    first = find_similar_words(candidates, profile)
    assert first == find_similar_words(candidates, profile)
    assert all(item.word_a < item.word_b for item in first)


def test_scoring_is_explainable_and_does_not_mutate_status() -> None:
    _, candidates, _, _ = load_curation_data("nb")
    candidate = candidates[0].candidate
    original = candidate.status
    result = score_candidate(candidate, has_provenance=True, review_complete=True)
    assert result.total == 80
    assert [signal.id for signal in result.signals][0] == "base_score"
    assert candidate.status == original


def test_scoring_penalties_and_bounds() -> None:
    _, candidates, _, _ = load_curation_data("nb")
    result = score_candidate(
        candidates[0].candidate,
        has_provenance=False,
        review_complete=False,
        similarity_warning=True,
        blocklist_warning=True,
    )
    assert result.total == 0


def test_required_criteria() -> None:
    _, _, _, reviews = load_curation_data("nb")
    assert required_criteria_resolved(reviews[0], list(ReviewCriteria.model_fields))
    values = yes_criteria().model_copy(update={"common": CriterionValue.UNKNOWN})
    incomplete = reviews[0].model_copy(update={"criteria": values})
    assert not required_criteria_resolved(incomplete, ["common"])


def test_latest_review_is_authoritative() -> None:
    _, _, _, reviews = load_curation_data("nb")
    original = reviews[0]
    later = original.model_copy(
        update={"id": "later", "reviewed_at": original.reviewed_at.replace(year=2027)}
    )
    assert latest_reviews([later, original])[original.candidate_id].id == "later"


def test_release_eligibility_and_similarity_is_advisory() -> None:
    _, candidates, provenance, reviews = load_curation_data("nb")
    reasons = evaluate_release_eligibility(
        candidates[0], provenance[0], reviews[0], list(ReviewCriteria.model_fields), set()
    )
    assert reasons == []
    assert "missing_provenance" in evaluate_release_eligibility(
        candidates[0], None, reviews[0], list(ReviewCriteria.model_fields), set()
    )


def test_curation_report_is_deterministic() -> None:
    first = build_curation_report("nb")
    assert first == build_curation_report("nb")
    assert first["release_eligible_count"] == 16
    assert first["candidate_count"] == 24


def test_batch_dry_run_stable(tmp_path: Path) -> None:
    path = tmp_path / "words.txt"
    path.write_text("måne\n", encoding="utf-8")
    first = import_candidate_batch(
        path, "nb", SourceType.MANUAL, "fixture:test", True, data_root=Path("data")
    )
    second = import_candidate_batch(
        path, "nb", SourceType.MANUAL, "fixture:test", True, data_root=Path("data")
    )
    assert first == second
    assert first["applied"] is False
    assert first["candidates"][0]["id"] == stable_candidate_id("nb", "måne")


def test_batch_duplicate_detection(tmp_path: Path) -> None:
    path = tmp_path / "words.txt"
    path.write_text("måne\nmåne\n", encoding="utf-8")
    with pytest.raises(ValidationFailure, match="duplicate"):
        import_candidate_batch(path, "nb", SourceType.MANUAL, "fixture:test", True)


def test_atomic_failed_write_preserves_file(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("original\n", encoding="utf-8")
    with pytest.raises(ValueError, match="final newline"):
        atomic_write_text(path, "invalid")
    assert path.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.iterdir()) == [path]


def test_m1_cli_commands() -> None:
    assert runner.invoke(app, ["similarity", "--language", "nb"]).exit_code == 0
    assert runner.invoke(app, ["score", "--language", "nb"]).exit_code == 0
    assert runner.invoke(app, ["curate", "report", "--all", "--format", "json"]).exit_code == 0
    assert runner.invoke(app, ["candidates", "validate", "--language", "nb"]).exit_code == 0


def test_blocklist_metadata_loads_for_all_languages() -> None:
    for code in ("nb", "nn", "en"):
        profile, _, _, _ = load_curation_data(code)
        metadata, entries, words = load_blocklists_with_metadata(
            Path("data/languages") / code / "blocklists", profile
        )
        assert len(metadata) == 1
        assert entries == [] and words == set()


def test_candidate_license_eligibility_compatibility() -> None:
    _, candidates, _, _ = load_curation_data("nb")
    assert candidates[0].candidate.is_license_eligible
    explicit = candidates[0].candidate.model_copy(
        update={"license_eligibility": "ineligible", "license_eligible": True}
    )
    assert not explicit.is_license_eligible


def test_import_cli_is_dry_run_and_does_not_modify_source(tmp_path: Path) -> None:
    path = tmp_path / "words.txt"
    path.write_text("måne\n", encoding="utf-8")
    source = Path("data/languages/nb/candidates.csv")
    before = source.read_bytes()
    result = runner.invoke(
        app,
        [
            "candidates",
            "import",
            str(path),
            "--language",
            "nb",
            "--source-type",
            "manual",
            "--submitted-by",
            "fixture:test",
            "--license-eligibility",
            "eligible",
        ],
    )
    assert result.exit_code == 0
    assert '"applied": false' in result.stdout
    assert source.read_bytes() == before


def test_review_approve_dry_run_does_not_modify_source(tmp_path: Path) -> None:
    criteria = tmp_path / "criteria.yaml"
    criteria.write_text(
        "".join(f"{name}: yes\n" for name in ReviewCriteria.model_fields), encoding="utf-8"
    )
    source = Path("data/languages/nb/candidates.csv")
    before = source.read_bytes()
    result = runner.invoke(
        app,
        [
            "review",
            "approve",
            "10000000-0000-4000-8000-000000000021",
            "--reviewer",
            "fixture:test",
            "--criteria-file",
            str(criteria),
        ],
    )
    assert result.exit_code == 0
    assert '"applied": false' in result.stdout
    assert source.read_bytes() == before
