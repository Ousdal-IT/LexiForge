import json
import shutil
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexiforge.cli import app
from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.editorial import (
    AddCandidateOperation,
    AddProvenanceOperation,
    EditCandidateOperation,
    EditorialService,
    RecordReviewOperation,
    SupersedeCandidateOperation,
    SupersedeProvenanceOperation,
    WithdrawCandidateOperation,
)
from lexiforge.editorial.errors import DuplicateCandidateError, MutationRejectedError
from lexiforge.models import CriterionValue, ReviewCriteria, ReviewDecision, SourceKind, SourceType
from lexiforge.repository import DatasetRepository

runner = CliRunner()
STAMP = "2026-07-22T20:00:00+02:00"


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "external-data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def add_operation() -> AddCandidateOperation:
    return AddCandidateOperation(
        language="nb",
        word="soloppgang",
        category="nature",
        submitter_id="editor-pgo",
        source_type=SourceType.MANUAL,
        source_kind=SourceKind.MANUAL,
        source_reference="editorial-session-001",
        license_basis="contributor-assertion",
        license_eligible=True,
        created_at=datetime.fromisoformat(STAMP),
        comment="Independent editorial contribution.",
    )


def test_operation_inputs_are_immutable_and_ui_independent() -> None:
    operations = (
        add_operation(),
        EditCandidateOperation("candidate", category="nature"),
        WithdrawCandidateOperation("candidate", "editor-pgo", datetime.fromisoformat(STAMP), "x"),
        SupersedeCandidateOperation(
            "candidate", "replacement", "editor-pgo", datetime.fromisoformat(STAMP), "x"
        ),
        AddProvenanceOperation(
            "candidate",
            SourceKind.MANUAL,
            "ref",
            "editor-pgo",
            "basis",
            True,
            datetime.fromisoformat(STAMP),
        ),
        SupersedeProvenanceOperation(
            "provenance", "editor-pgo", datetime.fromisoformat(STAMP), "x"
        ),
    )
    assert all("typer" not in type(item).__module__ for item in operations)
    with pytest.raises(FrozenInstanceError):
        operations[0].word = "changed"  # type: ignore[misc]


def test_add_preview_is_deterministic_and_writes_nothing(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    before = snapshot(repository.root)
    first = service.preview(add_operation())
    second = service.preview(add_operation())
    assert first == second
    assert snapshot(repository.root) == before
    assert first.operation == "candidate.add"
    assert len(first.files) == 2
    assert first.status_transitions[0].after == "submitted"


def test_add_apply_writes_candidate_and_provenance_together(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    change = service.preview(add_operation())
    service.apply(change)
    candidate_id = dict(change.details)["candidate_id"]
    assert service.candidate(candidate_id).status.value == "submitted"
    assert len(service.provenance(candidate_id)) == 1
    assert repository.validate_layout() == []
    with pytest.raises(DuplicateCandidateError):
        service.preview(add_operation())


def test_unicode_equivalent_duplicate_is_rejected(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    operation = replace(add_operation(), word="ba\u030aten")
    with pytest.raises(DuplicateCandidateError):
        EditorialService(repository).preview(operation)


def test_edit_noop_has_no_files_and_apply_is_safe(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    before = snapshot(repository.root)
    change = service.preview(
        EditCandidateOperation("10000000-0000-4000-8000-000000000002", category="nature")
    )
    assert change.validation_status == "no_change"
    service.apply(change)
    assert snapshot(repository.root) == before


def test_edit_preserves_candidate_identity_and_history(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_id = "10000000-0000-4000-8000-000000000005"
    before_reviews = service.reviews(candidate_id)
    change = service.preview(EditCandidateOperation(candidate_id, notes="Editorial note."))
    service.apply(change)
    assert service.candidate(candidate_id).id == candidate_id
    assert service.reviews(candidate_id) == before_reviews


def test_provenance_supersession_fails_without_schema_extension(tmp_path: Path) -> None:
    service = EditorialService(repository_copy(tmp_path))
    operation = SupersedeProvenanceOperation(
        "unknown", "editor-pgo", datetime.fromisoformat(STAMP), "corrected assertion"
    )
    with pytest.raises(MutationRejectedError, match="schema 1"):
        service.preview(operation)


def test_candidate_add_cli_dry_run_and_apply(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    args = [
        "candidates",
        "add",
        "--data-root",
        str(repository.root),
        "--language",
        "nb",
        "--word",
        "soloppgang",
        "--category",
        "nature",
        "--submitter-id",
        "editor-pgo",
        "--source-type",
        "project-created",
        "--source-reference",
        "session-1",
        "--license-eligible",
        "true",
        "--license-basis",
        "contributor-assertion",
        "--created-at",
        STAMP,
        "--format",
        "json",
    ]
    before = snapshot(repository.root)
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["applied"] is False
    assert snapshot(repository.root) == before
    applied = runner.invoke(app, [*args, "--apply"])
    assert applied.exit_code == 0, applied.stdout
    assert json.loads(applied.stdout)["applied"] is True


def test_candidate_add_cli_expected_error_has_no_traceback(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    result = runner.invoke(
        app,
        [
            "candidates",
            "add",
            "--data-root",
            str(repository.root),
            "--language",
            "nb",
            "--word",
            "skog",
            "--category",
            "nature",
            "--submitter-id",
            "editor-pgo",
            "--source-type",
            "manual",
            "--source-reference",
            "session-1",
            "--license-eligible",
            "true",
            "--license-basis",
            "basis",
            "--created-at",
            STAMP,
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False
    assert "Traceback" not in result.stdout


def test_existing_batch_import_apply_uses_editorial_changeset(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    words = tmp_path / "words.txt"
    words.write_text("soloppgang\n", encoding="utf-8")
    args = [
        "candidates",
        "import",
        str(words),
        "--data-root",
        str(repository.root),
        "--language",
        "nb",
        "--source-type",
        "manual",
        "--submitted-by",
        "editor-pgo",
        "--license-eligibility",
        "eligible",
    ]
    before = snapshot(repository.root)
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0
    assert json.loads(preview.stdout)["change_set"]["operation"] == "candidate.import"
    assert snapshot(repository.root) == before
    applied = runner.invoke(app, [*args, "--apply"])
    assert applied.exit_code == 0
    assert (
        EditorialService(repository).candidate("9dcdcfbc-a27b-5afe-a980-a2d0344b5fcf").status.value
        == "submitted"
    )


@pytest.mark.parametrize(
    "command",
    [
        ["candidates", "add", "--help"],
        ["candidates", "edit", "--help"],
        ["candidates", "withdraw", "--help"],
        ["candidates", "supersede", "--help"],
        ["provenance", "show", "--help"],
        ["provenance", "add", "--help"],
        ["provenance", "supersede", "--help"],
        ["review", "start", "--help"],
        ["review", "flag", "--help"],
    ],
)
def test_new_command_help(command: list[str]) -> None:
    assert runner.invoke(app, command).exit_code == 0


def test_record_review_operation_is_exported() -> None:
    assert RecordReviewOperation.__module__ == "lexiforge.editorial.operations"


def yes_criteria() -> ReviewCriteria:
    return ReviewCriteria.model_validate(
        {name: CriterionValue.YES for name in ReviewCriteria.model_fields}
    )


def test_review_approval_appends_history_and_updates_status(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_id = "10000000-0000-4000-8000-000000000021"
    before = service.reviews(candidate_id)
    operation = RecordReviewOperation(
        candidate_id,
        ReviewDecision.APPROVE,
        "reviewer-001",
        datetime.fromisoformat(STAMP),
        yes_criteria(),
        comment="Criteria checked.",
    )
    change = service.preview(operation)
    assert service.candidate(candidate_id).status.value == "needs_review"
    service.apply(change)
    assert service.candidate(candidate_id).status.value == "approved"
    assert len(service.reviews(candidate_id)) == len(before) + 1


def test_withdrawal_preserves_candidate_and_makes_it_ineligible(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_id = "10000000-0000-4000-8000-000000000001"
    operation = WithdrawCandidateOperation(
        candidate_id, "editor-pgo", datetime.fromisoformat(STAMP), "Editorial withdrawal."
    )
    change = service.preview(operation)
    assert change.status_transitions[0].after == "withdrawn"
    service.apply(change)
    assert service.candidate(candidate_id).status.value == "withdrawn"
    assert service.provenance(candidate_id)


def test_supersession_rejects_self_and_does_not_approve_replacement(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_id = "10000000-0000-4000-8000-000000000001"
    with pytest.raises(MutationRejectedError, match="itself"):
        service.preview(
            SupersedeCandidateOperation(
                candidate_id,
                candidate_id,
                "editor-pgo",
                datetime.fromisoformat(STAMP),
                "Replacement.",
            )
        )
    replacement = "10000000-0000-4000-8000-000000000005"
    replacement_status = service.candidate(replacement).status
    change = service.preview(
        SupersedeCandidateOperation(
            candidate_id,
            replacement,
            "editor-pgo",
            datetime.fromisoformat(STAMP),
            "Replacement.",
        )
    )
    service.apply(change)
    assert service.candidate(replacement).status == replacement_status
