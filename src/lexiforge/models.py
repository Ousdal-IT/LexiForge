import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
NormalizationForm = Literal["NFC", "NFD", "NFKC", "NFKD"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class WordLength(StrictModel):
    minimum: int = Field(ge=1)
    maximum: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> "WordLength":
        if self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class LanguageProfile(StrictModel):
    version: int = Field(ge=1)
    code: LanguageCode
    name: str = Field(min_length=1)
    locale: str = Field(min_length=2)
    normalization: NormalizationForm = "NFC"
    word_length: WordLength
    allowed_pattern: str
    vowels: str
    allow_diacritics: bool
    allow_apostrophes: bool = False
    allow_hyphens: bool = False
    allow_digits: bool = False
    allow_internal_whitespace: bool = False
    output_case: str = "lowercase"
    target_sizes: list[int] = Field(min_length=1)

    @field_validator("normalization")
    @classmethod
    def normalization_supported(cls, value: NormalizationForm) -> NormalizationForm:
        if value not in {"NFC", "NFD", "NFKC", "NFKD"}:
            raise ValueError("unsupported Unicode normalization")
        return value

    @field_validator("output_case")
    @classmethod
    def lowercase_only(cls, value: str) -> str:
        if value != "lowercase":
            raise ValueError("only lowercase output is supported in M0")
        return value

    @field_validator("allowed_pattern")
    @classmethod
    def valid_pattern(cls, value: str) -> str:
        try:
            compiled = re.compile(value)
        except re.error as error:
            raise ValueError(f"invalid regular expression: {error}") from error
        if not value.startswith("^") or not value.endswith("$"):
            raise ValueError("allowed_pattern must be anchored with ^ and $")
        if compiled.fullmatch(""):
            raise ValueError("allowed_pattern must not match the empty string")
        return value


class SharedPolicy(StrictModel):
    unicode_normalization: str = "NFC"
    require_lowercase: bool = True
    require_unique_words: bool = True
    require_final_newline: bool = True
    deterministic_sorting: bool = True
    required_review_criteria: list[str] = Field(
        default_factory=lambda: [
            "common",
            "easy_to_read",
            "easy_to_pronounce",
            "easy_to_spell",
            "neutral",
            "not_proper_name",
            "not_brand",
            "not_abbreviation",
            "suitable_for_passphrase",
        ]
    )
    development_sizes: list[int] = Field(default_factory=lambda: [16, 32, 64])


class Category(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
    labels: dict[LanguageCode, str]


class CategoryConfig(StrictModel):
    categories: list[Category]


class CandidateStatus(StrEnum):
    SUBMITTED = "submitted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTOMATIC_REJECT = "automatic_reject"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class SourceType(StrEnum):
    MANUAL = "manual"
    COMMUNITY = "community"
    IMPORT = "import"
    FIXTURE = "fixture"


class WordCandidate(StrictModel):
    id: str
    language: LanguageCode
    word: str
    status: CandidateStatus
    category: str | None = None
    source_type: SourceType
    submitted_at: datetime | None = None
    submitted_by: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    license_eligible: bool = False
    license_eligibility: Literal["eligible", "ineligible", "unknown"] | None = None
    provenance_id: str | None = None
    notes: str = ""

    @field_validator("id")
    @classmethod
    def globally_unique_id(cls, value: str) -> str:
        from uuid import UUID

        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("id must be a UUID") from error
        return value

    @field_validator("submitted_by", "reviewed_by")
    @classmethod
    def actor_identifier(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9_-]*(?::[A-Za-z0-9._-]+)?", value):
            raise ValueError("actor identifier must be a stable pseudonymous identifier")
        return value

    @property
    def is_license_eligible(self) -> bool:
        if self.license_eligibility is not None:
            return self.license_eligibility == "eligible"
        return self.license_eligible


class LicenseEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class SourceKind(StrEnum):
    MANUAL = "manual"
    COMMUNITY = "community"
    FIXTURE = "fixture"
    VERIFIED_SPELLING = "verified_spelling"
    THIRD_PARTY = "third_party"


class ProvenanceRecord(StrictModel):
    id: str
    candidate_id: str
    source_kind: SourceKind
    source_reference: str | None = None
    contributor_assertion: str
    license_basis: str
    independently_contributed: bool
    bulk_source: bool
    created_at: datetime | None = None
    notes: str = ""

    @model_validator(mode="after")
    def third_party_details(self) -> "ProvenanceRecord":
        if self.source_kind == SourceKind.THIRD_PARTY and (
            not self.source_reference or not self.license_basis
        ):
            raise ValueError("third-party provenance requires source reference and license basis")
        if self.bulk_source and self.independently_contributed:
            raise ValueError("bulk sources cannot be marked independently contributed")
        return self


class CriterionValue(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ReviewCriteria(StrictModel):
    common: CriterionValue
    easy_to_read: CriterionValue
    easy_to_pronounce: CriterionValue
    easy_to_spell: CriterionValue
    neutral: CriterionValue
    not_proper_name: CriterionValue
    not_brand: CriterionValue
    not_abbreviation: CriterionValue
    suitable_for_passphrase: CriterionValue


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"
    SUPERSEDE = "supersede"
    WITHDRAW = "withdraw"


class ReviewRecord(StrictModel):
    id: str
    candidate_id: str
    reviewer_id: str
    decision: ReviewDecision
    reviewed_at: datetime
    criteria: ReviewCriteria
    flags: list[str] = Field(default_factory=list)
    comment: str = ""
    previous_status: CandidateStatus
    new_status: CandidateStatus

    @field_validator("reviewer_id")
    @classmethod
    def reviewer_identifier(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*(?::[A-Za-z0-9._-]+)?", value):
            raise ValueError("reviewer identifier must be a stable pseudonymous identifier")
        return value


class ScoreSignal(StrictModel):
    id: str
    value: int
    message: str


class ScoreResult(StrictModel):
    total: int
    signals: list[ScoreSignal]


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SimilarityFinding(StrictModel):
    language: str
    word_a: str
    word_b: str
    rule_id: str
    distance: int
    severity: Severity = Severity.WARNING
    explanation: str


class Diagnostic(StrictModel):
    rule_id: str
    severity: Severity
    message: str
    language: str | None = None
    word: str | None = None
    file: str | None = None
    row: int | None = None


class ValidationResult(StrictModel):
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(item.severity == Severity.ERROR for item in self.diagnostics)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == Severity.WARNING for item in self.diagnostics)

    @property
    def valid(self) -> bool:
        return self.error_count == 0


class CandidateRecord(StrictModel):
    candidate: WordCandidate
    file: str | None = None
    row: int | None = None


def candidate_from_csv(row: dict[str, str]) -> WordCandidate:
    values: dict[str, Any] = dict(row)
    for key in ("category", "submitted_at", "reviewed_at", "score"):
        if values.get(key) == "":
            values[key] = None
    return WordCandidate.model_validate(values)
