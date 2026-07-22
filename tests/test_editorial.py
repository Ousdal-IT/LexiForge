import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.editorial import ChangeSet, EditorialError, EditorialService
from lexiforge.editorial.changeset import FileChange
from lexiforge.editorial.errors import (
    DuplicateCandidateError,
    MutationRejectedError,
    RepositoryStateError,
)
from lexiforge.editorial.operations import OperationPlan, ProposedFile
from lexiforge.editorial.preview import render_json, render_text
from lexiforge.repository import DatasetRepository


class FileOperation:
    def __init__(self, name: str, files: tuple[ProposedFile, ...]):
        self._name = name
        self._files = files

    @property
    def name(self) -> str:
        return self._name

    def plan(self, context) -> OperationPlan:
        return OperationPlan(
            files=self._files,
            records_modified=("fixture-record",),
            warnings=("fixture warning",),
        )


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "external-data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_editorial_service_creation_for_external_repository(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    assert service.repository.root == repository.root


def test_editorial_service_creation_for_bundled_repository() -> None:
    service = EditorialService(DatasetRepository(DEFAULT_DATA_ROOT))
    assert service.repository.source == "bundled"


def test_changeset_is_immutable_and_structured(tmp_path: Path) -> None:
    changeset = ChangeSet(
        id="fixture",
        repository_root=tmp_path,
        operation="test",
        files=(FileChange("note.txt", False, "a", "b", b"note\n"),),
    )
    assert changeset.affected_files == ("note.txt",)
    with pytest.raises(FrozenInstanceError):
        changeset.id = "changed"  # type: ignore[misc]


def test_preview_is_deterministic_and_performs_no_writes(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    operation = FileOperation("fixture", (ProposedFile("editorial-note.txt", b"proposed\n"),))
    before = snapshot(repository.root)
    first = service.preview(operation)
    second = service.preview(operation)
    assert first == second
    assert snapshot(repository.root) == before
    assert first.validation_status == "valid"
    assert first.records_modified == ("fixture-record",)


def test_preview_rendering_is_deterministic_and_content_free(tmp_path: Path) -> None:
    service = EditorialService(repository_copy(tmp_path))
    changeset = service.preview(
        FileOperation("fixture", (ProposedFile("editorial-note.txt", b"secret body\n"),))
    )
    assert render_json(changeset) == render_json(changeset)
    assert render_text(changeset) == render_text(changeset)
    assert "secret body" not in render_json(changeset)
    assert render_json(changeset).endswith("\n")
    assert render_text(changeset).endswith("\n")


def test_apply_validated_mock_operation(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    changeset = service.preview(
        FileOperation("fixture", (ProposedFile("editorial-note.txt", b"applied\n"),))
    )
    service.apply(changeset)
    assert (repository.root / "editorial-note.txt").read_bytes() == b"applied\n"
    assert repository.validate_layout() == []


def test_failed_preview_leaves_repository_unchanged(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidates = repository.root / "languages/nb/candidates.csv"
    content = candidates.read_bytes()
    duplicate_row = content.splitlines(keepends=True)[1]
    operation = FileOperation(
        "duplicate",
        (ProposedFile("languages/nb/candidates.csv", content + duplicate_row),),
    )
    before = snapshot(repository.root)
    with pytest.raises(DuplicateCandidateError):
        service.preview(operation)
    assert snapshot(repository.root) == before


def test_failed_apply_rolls_back_every_applied_file(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    normal = EditorialService(repository)
    changeset = normal.preview(
        FileOperation(
            "two-files",
            (
                ProposedFile("editorial-a.txt", b"one\n"),
                ProposedFile("editorial-b.txt", b"two\n"),
            ),
        )
    )

    class FailingService(EditorialService):
        writes = 0

        def _write(self, relative_path: str, content: bytes) -> None:
            self.writes += 1
            if self.writes == 2:
                raise OSError("fixture write failure")
            super()._write(relative_path, content)

    before = snapshot(repository.root)
    with pytest.raises(MutationRejectedError, match="repository restored"):
        FailingService(repository).apply(changeset)
    assert snapshot(repository.root) == before
    assert not (repository.root / "editorial-a.txt").exists()


def test_stale_changeset_is_rejected_without_overwrite(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    changeset = service.preview(
        FileOperation("fixture", (ProposedFile("editorial-note.txt", b"planned\n"),))
    )
    path = repository.root / "editorial-note.txt"
    path.write_text("external change\n", encoding="utf-8")
    with pytest.raises(RepositoryStateError, match="state changed"):
        service.apply(changeset)
    assert path.read_text(encoding="utf-8") == "external change\n"


def test_structured_editorial_exception_hierarchy() -> None:
    assert issubclass(DuplicateCandidateError, EditorialError)
    assert issubclass(RepositoryStateError, EditorialError)
    assert issubclass(MutationRejectedError, EditorialError)
