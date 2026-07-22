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
    code: LanguageCode
    name: str = Field(min_length=1)
    locale: str = Field(min_length=2)
    normalization: NormalizationForm = "NFC"
    word_length: WordLength
    allowed_pattern: str
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
    reviewed_at: datetime | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    license_eligible: bool = False
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


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


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
