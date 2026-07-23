from dataclasses import dataclass
from pathlib import Path

from ..blocklists import load_blocklists_with_metadata
from ..curation import evaluate_release_eligibility, load_curation_data
from ..models import CandidateStatus, ProvenanceRecord, ReviewRecord, WordCandidate
from ..moderation import latest_reviews
from ..normalize import normalize_word
from ..profiles import load_policy, load_profiles
from ..repository import DatasetRepository


@dataclass(frozen=True, slots=True)
class CandidateView:
    candidate: WordCandidate
    normalized_word: str
    release_eligible: bool
    eligibility_reasons: tuple[str, ...]
    provenance: tuple[ProvenanceRecord, ...]
    reviews: tuple[ReviewRecord, ...]

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

    def matches(self, item: CandidateView) -> bool:
        candidate = item.candidate
        return (
            (not self.search or self.search.casefold() in item.search_text)
            and (self.language is None or candidate.language == self.language)
            and (self.category is None or candidate.category == self.category)
            and (self.status is None or candidate.status == self.status)
            and (self.release_eligible is None or item.release_eligible == self.release_eligible)
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
