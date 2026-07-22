import hashlib
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from ..atomic import atomic_write_text
from ..blocklists import load_blocklists_with_metadata
from ..curation import build_curation_report
from ..io import load_language_candidates
from ..normalize import normalize_word
from ..profiles import load_categories, load_profiles
from ..repository import DatasetRepository
from ..validate import validate_candidates
from .changeset import ChangeSet, FileChange, ReleaseEligibilityImpact
from .errors import (
    DuplicateCandidateError,
    MutationRejectedError,
    RepositoryStateError,
    ValidationError,
)
from .operations import EditorialContextProtocol, EditorialOperation, OperationPlan


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class EditorialContext(EditorialContextProtocol):
    def __init__(self, repository: DatasetRepository):
        self.repository = repository
        self._profiles = load_profiles(repository.root)

    def read_bytes(self, relative_path: str) -> bytes:
        return (self.repository.root / relative_path).read_bytes()

    def normalize(self, language: str, word: str) -> str:
        return normalize_word(word, self._profiles[language])

    def candidate_exists(self, language: str, normalized_word: str) -> bool:
        return any(
            self.normalize(language, item.candidate.word) == normalized_word
            for item in load_language_candidates(language, self.repository.root)
        )


class EditorialService:
    """UI-independent coordinator for deterministic repository mutations."""

    def __init__(self, repository: DatasetRepository):
        self.repository = repository
        errors = repository.validate_layout()
        if errors:
            raise RepositoryStateError("invalid repository: " + "; ".join(errors))

    def preview(self, operation: EditorialOperation) -> ChangeSet:
        plan = operation.plan(EditorialContext(self.repository))
        files = self._file_changes(plan)
        with self._staged_repository(files) as staged:
            self._validate_repository(staged)
            impact = self._eligibility_impact(staged)
        identifier = self._changeset_id(operation.name, files)
        return ChangeSet(
            id=identifier,
            repository_root=self.repository.root,
            operation=operation.name,
            files=files,
            records_added=tuple(sorted(plan.records_added)),
            records_modified=tuple(sorted(plan.records_modified)),
            records_superseded=tuple(sorted(plan.records_superseded)),
            warnings=tuple(sorted(plan.warnings)),
            validation_status="valid",
            release_eligibility_impact=impact,
        )

    def apply(self, changeset: ChangeSet) -> None:
        if changeset.repository_root.resolve() != self.repository.root:
            raise RepositoryStateError("changeset belongs to a different repository")
        if changeset.validation_status != "valid":
            raise MutationRejectedError("only validated changesets can be applied")
        self._verify_current_state(changeset.files)
        with self._staged_repository(changeset.files) as staged:
            self._validate_repository(staged)
        originals = {
            item.relative_path: (
                (self.repository.root / item.relative_path).read_bytes() if item.existed else None
            )
            for item in changeset.files
        }
        applied: list[FileChange] = []
        try:
            for item in changeset.files:
                self._write(item.relative_path, item.content)
                applied.append(item)
            self._validate_repository(self.repository)
        except Exception as error:
            try:
                self._rollback(applied, originals)
            except Exception as rollback_error:
                raise RepositoryStateError(
                    f"mutation failed and rollback failed: {rollback_error}"
                ) from error
            if isinstance(error, (ValidationError, RepositoryStateError, MutationRejectedError)):
                raise
            raise MutationRejectedError(f"mutation failed; repository restored: {error}") from error

    def _file_changes(self, plan: OperationPlan) -> tuple[FileChange, ...]:
        paths = [item.relative_path for item in plan.files]
        if len(paths) != len(set(paths)):
            raise MutationRejectedError("operation proposes the same file more than once")
        changes = []
        for proposed in sorted(plan.files, key=lambda item: item.relative_path):
            relative = PurePosixPath(proposed.relative_path)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise MutationRejectedError(f"unsafe proposed path: {proposed.relative_path!r}")
            try:
                proposed.content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise MutationRejectedError(
                    f"proposed file is not UTF-8: {proposed.relative_path}"
                ) from error
            if proposed.content and not proposed.content.endswith(b"\n"):
                raise MutationRejectedError(
                    f"proposed text file lacks final newline: {proposed.relative_path}"
                )
            path = self.repository.root / relative
            existed = path.is_file()
            before = path.read_bytes() if existed else b""
            changes.append(
                FileChange(
                    relative_path=relative.as_posix(),
                    existed=existed,
                    before_sha256=_sha256(before),
                    after_sha256=_sha256(proposed.content),
                    content=proposed.content,
                )
            )
        if not changes:
            raise MutationRejectedError("operation proposes no file changes")
        return tuple(changes)

    def _validate_repository(self, repository: DatasetRepository) -> None:
        errors = repository.validate_layout()
        if errors:
            raise ValidationError("invalid resulting repository: " + "; ".join(errors))
        categories = {item.id for item in load_categories(repository.root).categories}
        for language, profile in sorted(load_profiles(repository.root).items()):
            records = load_language_candidates(language, repository.root)
            _, _, blocked = load_blocklists_with_metadata(
                repository.root / "languages" / language / "blocklists", profile
            )
            result = validate_candidates(records, profile, categories, blocked)
            if result.error_count:
                rules = sorted({item.rule_id for item in result.diagnostics})
                if "word.duplicate" in rules:
                    raise DuplicateCandidateError(f"duplicate normalized candidate in {language}")
                raise ValidationError(
                    f"candidate validation failed for {language}: {', '.join(rules)}"
                )

    def _eligibility_impact(
        self, staged: DatasetRepository
    ) -> tuple[ReleaseEligibilityImpact, ...]:
        manifest = staged.load_manifest()
        impacts = []
        for language in sorted(manifest.supported_languages):
            before = build_curation_report(language, self.repository.root)["release_eligible_count"]
            after = build_curation_report(language, staged.root)["release_eligible_count"]
            impacts.append(ReleaseEligibilityImpact(language=language, before=before, after=after))
        return tuple(impacts)

    def _verify_current_state(self, files: tuple[FileChange, ...]) -> None:
        for item in files:
            path = self.repository.root / item.relative_path
            if path.is_file() != item.existed:
                raise RepositoryStateError(f"repository state changed: {item.relative_path}")
            current = path.read_bytes() if path.is_file() else b""
            if _sha256(current) != item.before_sha256:
                raise RepositoryStateError(f"repository state changed: {item.relative_path}")

    def _staged_repository(self, files: tuple[FileChange, ...]) -> "_StagedRepository":
        return _StagedRepository(self.repository, files)

    def _write(self, relative_path: str, content: bytes) -> None:
        path = self.repository.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content.decode("utf-8"))

    def _rollback(self, applied: list[FileChange], originals: dict[str, bytes | None]) -> None:
        for item in reversed(applied):
            original = originals[item.relative_path]
            path = self.repository.root / item.relative_path
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_text(path, original.decode("utf-8"))

    @staticmethod
    def _changeset_id(operation: str, files: tuple[FileChange, ...]) -> str:
        digest = hashlib.sha256()
        digest.update(operation.encode("utf-8"))
        for item in files:
            digest.update(item.relative_path.encode("utf-8"))
            digest.update(item.before_sha256.encode("ascii"))
            digest.update(item.after_sha256.encode("ascii"))
        return digest.hexdigest()


class _StagedRepository:
    def __init__(self, source: DatasetRepository, files: tuple[FileChange, ...]):
        self.source = source
        self.files = files
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> DatasetRepository:
        self._temporary = tempfile.TemporaryDirectory(prefix="lexiforge-editorial-")
        root = Path(self._temporary.name) / "data"
        shutil.copytree(self.source.root, root)
        for item in self.files:
            path = root / item.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item.content)
        return DatasetRepository(root)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
