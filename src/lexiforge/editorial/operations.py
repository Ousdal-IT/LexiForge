import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from ..models import (
    CandidateStatus,
    CriterionValue,
    LanguageProfile,
    ProvenanceRecord,
    ReviewCriteria,
    ReviewDecision,
    ReviewRecord,
    SourceKind,
    SourceType,
    WordCandidate,
)
from ..transitions import validate_transition
from .changeset import FieldChange, StatusTransition
from .errors import DuplicateCandidateError, MutationRejectedError


@dataclass(frozen=True, slots=True)
class ProposedFile:
    relative_path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class OperationPlan:
    files: tuple[ProposedFile, ...]
    records_added: tuple[str, ...] = ()
    records_modified: tuple[str, ...] = ()
    records_superseded: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    field_changes: tuple[FieldChange, ...] = ()
    status_transitions: tuple[StatusTransition, ...] = ()
    details: tuple[tuple[str, str], ...] = ()


class EditorialContextProtocol(Protocol):
    def read_bytes(self, relative_path: str) -> bytes: ...

    def normalize(self, language: str, word: str) -> str: ...

    def candidate_exists(self, language: str, normalized_word: str) -> bool: ...

    def candidate(self, candidate_id: str) -> WordCandidate: ...

    def profile(self, language: str) -> LanguageProfile: ...

    def categories(self) -> set[str]: ...

    def provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]: ...

    def reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]: ...

    def required_criteria(self) -> tuple[str, ...]: ...

    def error_blocklisted(self, language: str, word: str) -> bool: ...

    def similarity_warnings(
        self, language: str, word: str, exclude_candidate_id: str | None = None
    ) -> tuple[str, ...]: ...


class EditorialOperation(Protocol):
    @property
    def name(self) -> str: ...

    def plan(self, context: EditorialContextProtocol) -> OperationPlan: ...


def _aware(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MutationRejectedError(f"{field} must include an explicit UTC offset")
    return value.isoformat()


def _read_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    return list(reader.fieldnames or ()), list(reader)


def _render_csv(fieldnames: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _candidate_path(language: str) -> str:
    return f"languages/{language}/candidates.csv"


def _provenance_path(language: str) -> str:
    return f"languages/{language}/provenance.csv"


def _reviews_path(language: str) -> str:
    return f"languages/{language}/reviews.csv"


def _candidate_id(language: str, normalized_word: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"lexiforge:candidate:{language}:{normalized_word}"))


def _provenance_id(candidate_id: str, source_reference: str | None, created_at: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"lexiforge:provenance:{candidate_id}:{source_reference or ''}:{created_at}",
        )
    )


def _review_id(
    candidate_id: str, decision: ReviewDecision, reviewer_id: str, reviewed_at: str
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"lexiforge:review:{candidate_id}:{decision.value}:{reviewer_id}:{reviewed_at}",
        )
    )


def _criteria_text(criteria: ReviewCriteria) -> str:
    return ";".join(f"{name}={value}" for name, value in criteria.model_dump(mode="json").items())


def _candidate_row(candidate: WordCandidate, fieldnames: list[str]) -> dict[str, str]:
    values = candidate.model_dump(mode="json")
    result: dict[str, str] = {}
    for field in fieldnames:
        value = values.get(field)
        if value is None:
            result[field] = ""
        elif isinstance(value, bool):
            result[field] = str(value).lower()
        else:
            result[field] = str(value)
    return result


@dataclass(frozen=True, slots=True)
class AddCandidateOperation:
    language: str
    word: str
    category: str
    submitter_id: str
    source_type: SourceType
    source_kind: SourceKind
    source_reference: str | None
    license_basis: str
    license_eligible: bool
    created_at: datetime
    comment: str = ""
    independently_contributed: bool = True
    bulk_source: bool = False

    @property
    def name(self) -> str:
        return "candidate.add"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        context.profile(self.language)
        normalized = context.normalize(self.language, self.word)
        if not normalized:
            raise MutationRejectedError("normalized word must not be empty")
        if context.candidate_exists(self.language, normalized):
            raise DuplicateCandidateError(
                f"normalized candidate already exists in {self.language}: {normalized!r}"
            )
        if self.category not in context.categories():
            raise MutationRejectedError(f"unknown category: {self.category}")
        created_at = _aware(self.created_at, "created_at")
        candidate_id = _candidate_id(self.language, normalized)
        provenance_id = _provenance_id(candidate_id, self.source_reference, created_at)
        candidate = WordCandidate(
            id=candidate_id,
            language=self.language,
            word=self.word,
            status=CandidateStatus.SUBMITTED,
            category=self.category,
            source_type=self.source_type,
            submitted_at=self.created_at,
            submitted_by=self.submitter_id,
            license_eligible=self.license_eligible,
            provenance_id=provenance_id,
            notes=self.comment,
        )
        provenance = ProvenanceRecord(
            id=provenance_id,
            candidate_id=candidate_id,
            source_kind=self.source_kind,
            source_reference=self.source_reference,
            contributor_assertion=f"Explicit contribution by {self.submitter_id}",
            license_basis=self.license_basis,
            independently_contributed=self.independently_contributed,
            bulk_source=self.bulk_source,
            created_at=self.created_at,
            notes=self.comment,
        )
        candidate_path = _candidate_path(self.language)
        candidate_fields, candidate_rows = _read_csv(context.read_bytes(candidate_path))
        candidate_rows.append(_candidate_row(candidate, candidate_fields))
        candidate_rows.sort(key=lambda row: row["id"])
        provenance_path = _provenance_path(self.language)
        provenance_fields, provenance_rows = _read_csv(context.read_bytes(provenance_path))
        provenance_values = provenance.model_dump(mode="json")
        provenance_rows.append(
            {
                field: (
                    ""
                    if provenance_values[field] is None
                    else str(provenance_values[field]).lower()
                    if isinstance(provenance_values[field], bool)
                    else str(provenance_values[field])
                )
                for field in provenance_fields
            }
        )
        provenance_rows.sort(key=lambda row: row["id"])
        warnings = context.similarity_warnings(self.language, self.word)
        return OperationPlan(
            files=(
                ProposedFile(candidate_path, _render_csv(candidate_fields, candidate_rows)),
                ProposedFile(provenance_path, _render_csv(provenance_fields, provenance_rows)),
            ),
            records_added=(candidate_id, provenance_id),
            warnings=warnings,
            status_transitions=(
                StatusTransition(candidate_id, "absent", CandidateStatus.SUBMITTED.value),
            ),
            details=(
                ("candidate_id", candidate_id),
                ("language", self.language),
                ("normalized_word", normalized),
                ("provenance_id", provenance_id),
                ("release_eligible", "false"),
                ("release_ineligibility_reason", "approval review missing"),
                ("word", self.word),
            ),
        )


@dataclass(frozen=True, slots=True)
class BatchImportOperation:
    """Compatibility operation for the existing local batch-import command."""

    language: str
    words: tuple[str, ...]
    source_type: SourceType
    submitted_by: str
    license_eligible: bool

    @property
    def name(self) -> str:
        return "candidate.import"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        context.profile(self.language)
        normalized_words = [(word, context.normalize(self.language, word)) for word in self.words]
        if len({normalized for _, normalized in normalized_words}) != len(normalized_words):
            raise DuplicateCandidateError("candidate batch contains normalized duplicates")
        for word, normalized in normalized_words:
            if context.candidate_exists(self.language, normalized):
                raise DuplicateCandidateError(
                    f"normalized candidate already exists in {self.language}: {word!r}"
                )
        if self.source_type == SourceType.IMPORT and self.license_eligible:
            raise MutationRejectedError(
                "bulk import cannot be marked license eligible without later review"
            )
        candidate_path = _candidate_path(self.language)
        candidate_fields, candidate_rows = _read_csv(context.read_bytes(candidate_path))
        provenance_path = _provenance_path(self.language)
        provenance_fields, provenance_rows = _read_csv(context.read_bytes(provenance_path))
        added: list[str] = []
        for word, normalized in sorted(normalized_words, key=lambda item: item[1]):
            candidate_id = _candidate_id(self.language, normalized)
            provenance_id = str(uuid5(NAMESPACE_URL, f"lexiforge:batch-provenance:{candidate_id}"))
            candidate = WordCandidate(
                id=candidate_id,
                language=self.language,
                word=word,
                status=CandidateStatus.SUBMITTED,
                source_type=self.source_type,
                submitted_by=self.submitted_by,
                license_eligible=self.license_eligible,
                provenance_id=provenance_id,
                notes="local batch import",
            )
            provenance = ProvenanceRecord(
                id=provenance_id,
                candidate_id=candidate_id,
                source_kind=SourceKind.MANUAL,
                contributor_assertion=f"Explicit batch contribution by {self.submitted_by}",
                license_basis="Contributor assertion; pending review",
                independently_contributed=self.source_type != SourceType.IMPORT,
                bulk_source=self.source_type == SourceType.IMPORT,
                notes="local batch import",
            )
            candidate_rows.append(_candidate_row(candidate, candidate_fields))
            values = provenance.model_dump(mode="json")
            provenance_rows.append(
                {
                    field: ""
                    if values[field] is None
                    else str(values[field]).lower()
                    if isinstance(values[field], bool)
                    else str(values[field])
                    for field in provenance_fields
                }
            )
            added.extend((candidate_id, provenance_id))
        candidate_rows.sort(key=lambda row: row["id"])
        provenance_rows.sort(key=lambda row: row["id"])
        return OperationPlan(
            files=(
                ProposedFile(candidate_path, _render_csv(candidate_fields, candidate_rows)),
                ProposedFile(provenance_path, _render_csv(provenance_fields, provenance_rows)),
            ),
            records_added=tuple(added),
            details=(
                ("candidate_count", str(len(normalized_words))),
                ("language", self.language),
            ),
        )


@dataclass(frozen=True, slots=True)
class EditCandidateOperation:
    candidate_id: str
    word: str | None = None
    category: str | None = None
    notes: str | None = None

    @property
    def name(self) -> str:
        return "candidate.edit"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        candidate = context.candidate(self.candidate_id)
        if self.category is not None and self.category not in context.categories():
            raise MutationRejectedError(f"unknown category: {self.category}")
        new_word = self.word if self.word is not None else candidate.word
        if new_word != candidate.word:
            if candidate.status == CandidateStatus.APPROVED:
                raise MutationRejectedError(
                    "schema 1 has no approved-to-review transition; withdraw or "
                    "supersede before changing word"
                )
            normalized = context.normalize(candidate.language, new_word)
            if context.candidate_exists(candidate.language, normalized):
                raise DuplicateCandidateError(
                    f"normalized candidate already exists in {candidate.language}: {normalized!r}"
                )
        new_category = self.category if self.category is not None else candidate.category
        new_notes = self.notes if self.notes is not None else candidate.notes
        if candidate.status == CandidateStatus.APPROVED and new_category != candidate.category:
            raise MutationRejectedError(
                "schema 1 has no approved-to-review transition; withdraw or supersede before "
                "changing category"
            )
        changes = tuple(
            FieldChange(field, before, after)
            for field, before, after in (
                ("word", candidate.word, new_word),
                ("category", candidate.category, new_category),
                ("notes", candidate.notes, new_notes),
            )
            if before != after
        )
        if not changes:
            return OperationPlan(
                files=(),
                details=(("candidate_id", self.candidate_id), ("result", "no_change")),
            )
        path = _candidate_path(candidate.language)
        fieldnames, rows = _read_csv(context.read_bytes(path))
        for row in rows:
            if row["id"] == self.candidate_id:
                row["word"] = new_word
                row["category"] = new_category or ""
                row["notes"] = new_notes
        warnings = context.similarity_warnings(
            candidate.language, new_word, exclude_candidate_id=self.candidate_id
        )
        return OperationPlan(
            files=(ProposedFile(path, _render_csv(fieldnames, rows)),),
            records_modified=(self.candidate_id,),
            warnings=warnings,
            field_changes=changes,
            details=(
                ("candidate_id", self.candidate_id),
                ("language", candidate.language),
                ("normalized_word", context.normalize(candidate.language, new_word)),
            ),
        )


@dataclass(frozen=True, slots=True)
class AddProvenanceOperation:
    candidate_id: str
    source_kind: SourceKind
    source_reference: str | None
    contributor_id: str
    license_basis: str
    license_eligible: bool
    recorded_at: datetime
    comment: str = ""
    independently_contributed: bool = True
    bulk_source: bool = False

    @property
    def name(self) -> str:
        return "provenance.add"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        candidate = context.candidate(self.candidate_id)
        recorded_at = _aware(self.recorded_at, "recorded_at")
        existing = context.provenance(self.candidate_id)
        if any(
            item.source_kind == self.source_kind
            and item.source_reference == self.source_reference
            and item.license_basis == self.license_basis
            for item in existing
        ):
            raise MutationRejectedError("duplicate provenance assertion for candidate")
        provenance_id = _provenance_id(self.candidate_id, self.source_reference, recorded_at)
        provenance = ProvenanceRecord(
            id=provenance_id,
            candidate_id=self.candidate_id,
            source_kind=self.source_kind,
            source_reference=self.source_reference,
            contributor_assertion=f"Explicit assertion by {self.contributor_id}",
            license_basis=self.license_basis,
            independently_contributed=self.independently_contributed,
            bulk_source=self.bulk_source,
            created_at=self.recorded_at,
            notes=self.comment,
        )
        provenance_path = _provenance_path(candidate.language)
        fields, rows = _read_csv(context.read_bytes(provenance_path))
        values = provenance.model_dump(mode="json")
        rows.append(
            {
                field: (
                    ""
                    if values[field] is None
                    else str(values[field]).lower()
                    if isinstance(values[field], bool)
                    else str(values[field])
                )
                for field in fields
            }
        )
        rows.sort(key=lambda row: row["id"])
        candidate_path = _candidate_path(candidate.language)
        candidate_fields, candidate_rows = _read_csv(context.read_bytes(candidate_path))
        for row in candidate_rows:
            if row["id"] == self.candidate_id:
                row["license_eligible"] = str(self.license_eligible).lower()
        return OperationPlan(
            files=(
                ProposedFile(candidate_path, _render_csv(candidate_fields, candidate_rows)),
                ProposedFile(provenance_path, _render_csv(fields, rows)),
            ),
            records_added=(provenance_id,),
            records_modified=(self.candidate_id,),
            field_changes=(
                FieldChange(
                    "license_eligible",
                    str(candidate.is_license_eligible).lower(),
                    str(self.license_eligible).lower(),
                ),
            ),
            details=(
                ("candidate_id", self.candidate_id),
                ("provenance_id", provenance_id),
            ),
        )


@dataclass(frozen=True, slots=True)
class SupersedeProvenanceOperation:
    provenance_id: str
    actor_id: str
    timestamp: datetime
    reason: str

    @property
    def name(self) -> str:
        return "provenance.supersede"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        raise MutationRejectedError(
            "dataset schema 1 cannot represent provenance supersession without rewriting history"
        )


@dataclass(frozen=True, slots=True)
class RecordReviewOperation:
    candidate_id: str
    decision: ReviewDecision
    reviewer_id: str
    reviewed_at: datetime
    criteria: ReviewCriteria
    comment: str = ""
    reason: str | None = None
    flags: tuple[str, ...] = ()
    replacement_id: str | None = None

    @property
    def name(self) -> str:
        return f"review.{self.decision.value}"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        candidate = context.candidate(self.candidate_id)
        reviewed_at = _aware(self.reviewed_at, "reviewed_at")
        new_status = {
            ReviewDecision.APPROVE: CandidateStatus.APPROVED,
            ReviewDecision.REJECT: CandidateStatus.REJECTED,
            ReviewDecision.NEEDS_REVIEW: CandidateStatus.NEEDS_REVIEW,
            ReviewDecision.SUPERSEDE: CandidateStatus.SUPERSEDED,
            ReviewDecision.WITHDRAW: CandidateStatus.WITHDRAWN,
        }[self.decision]
        try:
            validate_transition(candidate.status, new_status)
        except Exception as error:
            raise MutationRejectedError(str(error)) from error
        if self.decision == ReviewDecision.APPROVE:
            unresolved = [
                name
                for name in context.required_criteria()
                if self.criteria.model_dump(mode="json")[name] != CriterionValue.YES.value
            ]
            if unresolved:
                raise MutationRejectedError(
                    "approval requires criteria: " + ", ".join(sorted(unresolved))
                )
            if not context.provenance(self.candidate_id):
                raise MutationRejectedError("approval requires provenance")
            if not candidate.is_license_eligible:
                raise MutationRejectedError("approval requires explicit license eligibility")
            if self.flags:
                raise MutationRejectedError("approval cannot contain unresolved flags")
            if context.error_blocklisted(candidate.language, candidate.word):
                raise MutationRejectedError("approval blocked by error-severity blocklist")
        if self.decision in {ReviewDecision.REJECT, ReviewDecision.WITHDRAW} and not self.reason:
            raise MutationRejectedError(f"{self.decision.value} requires a reason")
        replacement = None
        if self.decision == ReviewDecision.SUPERSEDE:
            if not self.replacement_id:
                raise MutationRejectedError("supersession requires replacement candidate")
            if self.replacement_id == self.candidate_id:
                raise MutationRejectedError("candidate cannot supersede itself")
            replacement = context.candidate(self.replacement_id)
            if replacement.language != candidate.language:
                raise MutationRejectedError("replacement candidate must use the same language")
            marker = f"replacement_id={self.candidate_id}"
            if any(marker in review.comment for review in context.reviews(self.replacement_id)):
                raise MutationRejectedError("circular candidate supersession")
        comment_parts = []
        if self.replacement_id:
            comment_parts.append(f"replacement_id={self.replacement_id}")
        if self.reason:
            comment_parts.append(f"reason={self.reason}")
        if self.comment:
            comment_parts.append(self.comment)
        audit_comment = "; ".join(comment_parts)
        review = ReviewRecord(
            id=_review_id(self.candidate_id, self.decision, self.reviewer_id, reviewed_at),
            candidate_id=self.candidate_id,
            reviewer_id=self.reviewer_id,
            decision=self.decision,
            reviewed_at=self.reviewed_at,
            criteria=self.criteria,
            flags=list(self.flags),
            comment=audit_comment,
            previous_status=candidate.status,
            new_status=new_status,
        )
        review_path = _reviews_path(candidate.language)
        fields, rows = _read_csv(context.read_bytes(review_path))
        rows.append(
            {
                "id": review.id,
                "candidate_id": review.candidate_id,
                "reviewer_id": review.reviewer_id,
                "decision": review.decision.value,
                "reviewed_at": reviewed_at,
                "criteria": _criteria_text(review.criteria),
                "flags": json.dumps(review.flags, ensure_ascii=False),
                "comment": review.comment,
                "previous_status": review.previous_status.value,
                "new_status": review.new_status.value,
            }
        )
        rows.sort(key=lambda row: (row["reviewed_at"], row["id"]))
        candidate_path = _candidate_path(candidate.language)
        candidate_fields, candidate_rows = _read_csv(context.read_bytes(candidate_path))
        for row in candidate_rows:
            if row["id"] == self.candidate_id:
                row["status"] = new_status.value
                row["reviewed_at"] = reviewed_at
        warnings = context.similarity_warnings(
            candidate.language, candidate.word, exclude_candidate_id=self.candidate_id
        )
        details = [
            ("candidate_id", self.candidate_id),
            (
                "blocklist_error",
                str(context.error_blocklisted(candidate.language, candidate.word)).lower(),
            ),
            ("criteria", _criteria_text(self.criteria)),
            ("current_status", candidate.status.value),
            ("flags", json.dumps(sorted(self.flags), ensure_ascii=False)),
            ("language", candidate.language),
            ("proposed_status", new_status.value),
            ("provenance_count", str(len(context.provenance(self.candidate_id)))),
            ("reviewer_id", self.reviewer_id),
            ("reviewed_at", reviewed_at),
            ("word", candidate.word),
        ]
        if audit_comment:
            details.append(("comment", audit_comment))
        if replacement:
            details.append(("replacement_id", replacement.id))
        return OperationPlan(
            files=(
                ProposedFile(candidate_path, _render_csv(candidate_fields, candidate_rows)),
                ProposedFile(review_path, _render_csv(fields, rows)),
            ),
            records_added=(review.id,),
            records_modified=(self.candidate_id,),
            records_superseded=(self.candidate_id,)
            if self.decision == ReviewDecision.SUPERSEDE
            else (),
            warnings=warnings,
            status_transitions=(
                StatusTransition(self.candidate_id, candidate.status.value, new_status.value),
            ),
            details=tuple(details),
        )


@dataclass(frozen=True, slots=True)
class WithdrawCandidateOperation:
    candidate_id: str
    actor_id: str
    timestamp: datetime
    reason: str
    comment: str = ""

    @property
    def name(self) -> str:
        return "candidate.withdraw"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        return RecordReviewOperation(
            candidate_id=self.candidate_id,
            decision=ReviewDecision.WITHDRAW,
            reviewer_id=self.actor_id,
            reviewed_at=self.timestamp,
            criteria=unknown_criteria(),
            reason=self.reason,
            comment=self.comment,
        ).plan(context)


@dataclass(frozen=True, slots=True)
class SupersedeCandidateOperation:
    candidate_id: str
    replacement_id: str
    actor_id: str
    timestamp: datetime
    reason: str
    comment: str = ""

    @property
    def name(self) -> str:
        return "candidate.supersede"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        return RecordReviewOperation(
            candidate_id=self.candidate_id,
            decision=ReviewDecision.SUPERSEDE,
            reviewer_id=self.actor_id,
            reviewed_at=self.timestamp,
            criteria=unknown_criteria(),
            reason=self.reason,
            comment=self.comment,
            replacement_id=self.replacement_id,
        ).plan(context)


def unknown_criteria() -> ReviewCriteria:
    return ReviewCriteria.model_validate(
        {name: CriterionValue.UNKNOWN for name in ReviewCriteria.model_fields}
    )
