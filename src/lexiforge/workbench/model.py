from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..blocklists import load_blocklists_with_metadata
from ..curation import evaluate_release_eligibility, load_curation_data
from ..models import CandidateStatus, ProvenanceRecord, ReviewRecord, WordCandidate
from ..moderation import latest_reviews
from ..normalize import normalize_word
from ..profiles import load_policy, load_profiles
from ..repository import DatasetRepository


def _within_dates(
    value: datetime | None,
    after: datetime | None,
    before: datetime | None,
) -> bool:
    if after is None and before is None:
        return True
    if value is None:
        return False
    return (after is None or value >= after) and (before is None or value <= before)


@dataclass(frozen=True, slots=True)
class CandidateView:
    candidate: WordCandidate
    normalized_word: str
    release_eligible: bool
    eligibility_reasons: tuple[str, ...]
    provenance: tuple[ProvenanceRecord, ...]
    reviews: tuple[ReviewRecord, ...]
    blocklist_match: bool = False
    similarity_warning: bool = False

    @property
    def contributor(self) -> str | None:
        return self.candidate.submitted_by

    @property
    def reviewer(self) -> str | None:
        return self.reviews[-1].reviewer_id if self.reviews else None

    @property
    def review_state(self) -> str:
        if not self.reviews:
            return "pending"
        if self.reviews[-1].flags:
            return "flagged"
        return "complete"

    @property
    def source_type(self) -> str:
        return self.candidate.source_type.value

    @property
    def search_text(self) -> str:
        return " ".join((self.candidate.word, self.normalized_word, self.candidate.id)).casefold()


@dataclass(frozen=True, slots=True)
class CandidateFilter:
    search: str = ""
    language: str | None = None
    category: str | None = None
    status: CandidateStatus | None = None
    release_eligible: bool | None = None
    review_state: str | None = None
    contributor: str | None = None
    reviewer: str | None = None
    source_type: str | None = None
    license_eligible: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    similarity_warning: bool | None = None
    blocklist_state: str | None = None

    def matches(self, item: CandidateView) -> bool:
        candidate = item.candidate
        return (
            (not self.search or self.search.casefold() in item.search_text)
            and (self.language is None or candidate.language == self.language)
            and (self.category is None or candidate.category == self.category)
            and (self.status is None or candidate.status == self.status)
            and (self.release_eligible is None or item.release_eligible == self.release_eligible)
            and (self.review_state is None or item.review_state == self.review_state)
            and (self.contributor is None or item.contributor == self.contributor)
            and (self.reviewer is None or item.reviewer == self.reviewer)
            and (self.source_type is None or item.source_type == self.source_type)
            and (
                self.license_eligible is None
                or candidate.is_license_eligible == self.license_eligible
            )
            and _within_dates(candidate.submitted_at, self.created_after, self.created_before)
            and _within_dates(candidate.reviewed_at, self.modified_after, self.modified_before)
            and (
                self.similarity_warning is None
                or item.similarity_warning == self.similarity_warning
            )
            and (
                self.blocklist_state is None
                or ("match" if item.blocklist_match else "clear") == self.blocklist_state
            )
        )


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    root: Path
    candidates: tuple[CandidateView, ...]
    languages: tuple[str, ...]
    categories: tuple[str, ...]

    @classmethod
    def load(cls, repository: DatasetRepository) -> "RepositorySnapshot":
        profiles = load_profiles(repository.root)
        policy = load_policy(repository.root)
        candidates: list[CandidateView] = []
        categories: set[str] = set()
        for language, profile in sorted(profiles.items()):
            _, records, provenance, reviews = load_curation_data(language, repository.root)
            provenance_by_candidate: dict[str, list[ProvenanceRecord]] = {}
            reviews_by_candidate: dict[str, list[ReviewRecord]] = {}
            for provenance_record in provenance:
                provenance_by_candidate.setdefault(provenance_record.candidate_id, []).append(
                    provenance_record
                )
            for review_record in reviews:
                reviews_by_candidate.setdefault(review_record.candidate_id, []).append(
                    review_record
                )
            effective_reviews = latest_reviews(reviews)
            _, blocklist_entries, _ = load_blocklists_with_metadata(
                repository.root / "languages" / language / "blocklists", profile
            )
            error_words = {item.word for item in blocklist_entries if item.severity == "error"}
            blocklist_words = {item.word for item in blocklist_entries}
            for candidate_record in records:
                candidate = candidate_record.candidate
                candidate_provenance = tuple(
                    sorted(provenance_by_candidate.get(candidate.id, ()), key=lambda item: item.id)
                )
                candidate_reviews = tuple(
                    sorted(
                        reviews_by_candidate.get(candidate.id, ()),
                        key=lambda item: (item.reviewed_at, item.id),
                    )
                )
                reasons = tuple(
                    evaluate_release_eligibility(
                        candidate_record,
                        candidate_provenance[-1] if candidate_provenance else None,
                        effective_reviews.get(candidate.id),
                        policy.required_review_criteria,
                        error_words,
                    )
                )
                if candidate.category:
                    categories.add(candidate.category)
                candidates.append(
                    CandidateView(
                        candidate=candidate,
                        normalized_word=normalize_word(candidate.word, profile),
                        release_eligible=not reasons,
                        eligibility_reasons=reasons,
                        provenance=candidate_provenance,
                        reviews=candidate_reviews,
                        blocklist_match=candidate.word in blocklist_words,
                    )
                )
        return cls(
            root=repository.root,
            candidates=tuple(
                sorted(
                    candidates,
                    key=lambda item: (
                        item.candidate.language,
                        item.normalized_word,
                        item.candidate.id,
                    ),
                )
            ),
            languages=tuple(sorted(profiles)),
            categories=tuple(sorted(categories)),
        )

    def filtered(self, filters: CandidateFilter) -> tuple[CandidateView, ...]:
        return tuple(item for item in self.candidates if filters.matches(item))

    def candidate(self, candidate_id: str) -> CandidateView | None:
        return next((item for item in self.candidates if item.candidate.id == candidate_id), None)
