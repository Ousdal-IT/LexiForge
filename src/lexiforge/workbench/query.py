"""Backend-independent, bounded read models for editorial workbenches."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ..index import RepositoryIndex, RepositoryIndexError
from ..index.storage import index_path
from ..models import (
    CandidateRecord,
    ProvenanceRecord,
    ReviewRecord,
    SimilarityFinding,
    WordCandidate,
)
from ..profiles import load_profiles
from ..repository import DatasetRepository
from ..similarity import find_similar_words
from .model import CandidateFilter, CandidateView, RepositorySnapshot
from .tools import RepositoryStatistics, repository_statistics

CandidateSort = Literal["word", "language", "category", "status", "eligible"]
MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    candidate: WordCandidate
    normalized_word: str
    release_eligible: bool
    eligibility_reasons: tuple[str, ...]
    blocklist_match: bool
    review_state: str
    reviewer: str | None


@dataclass(frozen=True, slots=True)
class CandidateQuery:
    filters: CandidateFilter = CandidateFilter()
    sort: CandidateSort = "word"
    reverse: bool = False
    offset: int = 0
    limit: int = 50

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("candidate query offset must be non-negative")
        if not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError(f"candidate query limit must be between 1 and {MAX_PAGE_SIZE}")


@dataclass(frozen=True, slots=True)
class CandidatePage:
    items: tuple[CandidateSummary, ...]
    total_count: int
    offset: int
    limit: int

    @property
    def has_previous(self) -> bool:
        return self.offset > 0

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.items) < self.total_count

    @property
    def page_number(self) -> int:
        return self.offset // self.limit + 1

    @property
    def page_count(self) -> int:
        return max(1, (self.total_count + self.limit - 1) // self.limit)


@dataclass(frozen=True, slots=True)
class WorkbenchBackendStatus:
    kind: Literal["indexed", "canonical"]
    label: str
    index_state: str
    reason: str | None = None


class WorkbenchRepositoryView(Protocol):
    """Small read contract shared by Textual and future presentation layers."""

    @property
    def status(self) -> WorkbenchBackendStatus: ...

    @property
    def languages(self) -> tuple[str, ...]: ...

    @property
    def categories(self) -> tuple[str, ...]: ...

    def list_candidates(self, query: CandidateQuery) -> CandidatePage: ...

    def get_candidate(self, candidate_id: str) -> CandidateView | None: ...

    def get_provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]: ...

    def get_reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]: ...

    def get_dashboard_statistics(self) -> RepositoryStatistics: ...

    def find_duplicates(
        self, language: str, normalized_word: str
    ) -> tuple[CandidateSummary, ...]: ...

    def find_similarity_candidates(
        self, candidate_id: str, limit: int = 100
    ) -> tuple[SimilarityFinding, ...]: ...

    def close(self) -> None: ...


def _summary(item: CandidateView) -> CandidateSummary:
    return CandidateSummary(
        candidate=item.candidate,
        normalized_word=item.normalized_word,
        release_eligible=item.release_eligible,
        eligibility_reasons=item.eligibility_reasons,
        blocklist_match=item.blocklist_match,
        review_state=item.review_state,
        reviewer=item.reviewer,
    )


def _sort_key(item: CandidateSummary, field: CandidateSort) -> tuple[object, ...]:
    candidate = item.candidate
    return {
        "word": (item.normalized_word, candidate.id),
        "language": (candidate.language, item.normalized_word, candidate.id),
        "category": (candidate.category or "", item.normalized_word, candidate.id),
        "status": (candidate.status.value, item.normalized_word, candidate.id),
        "eligible": (item.release_eligible, item.normalized_word, candidate.id),
    }[field]


class CanonicalWorkbenchView:
    """Complete immutable snapshot used only when no valid index is available."""

    def __init__(
        self,
        repository: DatasetRepository,
        *,
        index_state: str = "unavailable",
        reason: str | None = None,
    ):
        self.repository = repository
        self.snapshot = RepositorySnapshot.load(repository)
        self._status = WorkbenchBackendStatus(
            "canonical", "Canonical fallback", index_state, reason
        )

    @property
    def status(self) -> WorkbenchBackendStatus:
        return self._status

    @property
    def languages(self) -> tuple[str, ...]:
        return self.snapshot.languages

    @property
    def categories(self) -> tuple[str, ...]:
        return self.snapshot.categories

    def list_candidates(self, query: CandidateQuery) -> CandidatePage:
        items = [_summary(item) for item in self.snapshot.filtered(query.filters)]
        items.sort(key=lambda item: _sort_key(item, query.sort), reverse=query.reverse)
        selected = items[query.offset : query.offset + query.limit]
        return CandidatePage(tuple(selected), len(items), query.offset, query.limit)

    def get_candidate(self, candidate_id: str) -> CandidateView | None:
        return self.snapshot.candidate(candidate_id)

    def get_provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]:
        item = self.snapshot.candidate(candidate_id)
        return item.provenance if item else ()

    def get_reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]:
        item = self.snapshot.candidate(candidate_id)
        return item.reviews if item else ()

    def get_dashboard_statistics(self) -> RepositoryStatistics:
        return repository_statistics(self.snapshot)

    def find_duplicates(self, language: str, normalized_word: str) -> tuple[CandidateSummary, ...]:
        return tuple(
            _summary(item)
            for item in self.snapshot.candidates
            if item.candidate.language == language and item.normalized_word == normalized_word
        )

    def find_similarity_candidates(
        self, candidate_id: str, limit: int = 100
    ) -> tuple[SimilarityFinding, ...]:
        selected = self.snapshot.candidate(candidate_id)
        if selected is None:
            return ()
        prefix = selected.normalized_word[:2]
        candidates = [
            item
            for item in self.snapshot.candidates
            if item.candidate.language == selected.candidate.language
            and item.candidate.id != candidate_id
            and item.normalized_word.startswith(prefix)
        ][:limit]
        return _similarity_findings(self.repository, selected, candidates)

    def close(self) -> None:
        return


class IndexedWorkbenchView:
    """Bounded workbench reads over one already verified repository index."""

    def __init__(self, repository: DatasetRepository, index: RepositoryIndex):
        self.repository = repository
        self.index = index
        self._languages = tuple(sorted(load_profiles(repository.root)))
        self._categories = index.list_categories()
        self._status = WorkbenchBackendStatus("indexed", "Indexed", "valid")

    @property
    def status(self) -> WorkbenchBackendStatus:
        return self._status

    @property
    def languages(self) -> tuple[str, ...]:
        return self._languages

    @property
    def categories(self) -> tuple[str, ...]:
        return self._categories

    def list_candidates(self, query: CandidateQuery) -> CandidatePage:
        filters = query.filters
        page = self.index.search_candidates(
            filters.search,
            language=filters.language,
            category=filters.category,
            status=filters.status,
            release_eligible=filters.release_eligible,
            review_state=filters.review_state,
            contributor=filters.contributor,
            reviewer=filters.reviewer,
            source_type=filters.source_type,
            license_eligible=filters.license_eligible,
            created_after=filters.created_after,
            created_before=filters.created_before,
            modified_after=filters.modified_after,
            modified_before=filters.modified_before,
            similarity_warning=filters.similarity_warning,
            blocklist_state=filters.blocklist_state,
            include_normalized_search=True,
            sort_field=query.sort,
            reverse=query.reverse,
            offset=query.offset,
            limit=query.limit,
        )
        return CandidatePage(
            tuple(
                CandidateSummary(
                    candidate=item.candidate,
                    normalized_word=item.normalized_word,
                    release_eligible=item.release_eligible,
                    eligibility_reasons=item.eligibility_reasons,
                    blocklist_match=item.blocklist_match,
                    review_state=item.review_state,
                    reviewer=item.reviewer,
                )
                for item in page.items
            ),
            page.total,
            page.offset,
            page.limit,
        )

    def get_candidate(self, candidate_id: str) -> CandidateView | None:
        item = self.index.get_candidate(candidate_id)
        if item is None:
            return None
        return CandidateView(
            candidate=item.candidate,
            normalized_word=item.normalized_word,
            release_eligible=item.release_eligible,
            eligibility_reasons=item.eligibility_reasons,
            provenance=self.get_provenance(candidate_id),
            reviews=self.get_reviews(candidate_id),
            blocklist_match=item.blocklist_match,
        )

    def get_provenance(self, candidate_id: str) -> tuple[ProvenanceRecord, ...]:
        return self.index.get_provenance(candidate_id)

    def get_reviews(self, candidate_id: str) -> tuple[ReviewRecord, ...]:
        return self.index.get_reviews(candidate_id)

    def get_dashboard_statistics(self) -> RepositoryStatistics:
        return RepositoryStatistics(**self.index.get_dashboard_statistics())

    def find_duplicates(self, language: str, normalized_word: str) -> tuple[CandidateSummary, ...]:
        return tuple(
            CandidateSummary(
                candidate=item.candidate,
                normalized_word=item.normalized_word,
                release_eligible=item.release_eligible,
                eligibility_reasons=item.eligibility_reasons,
                blocklist_match=item.blocklist_match,
                review_state=item.review_state,
                reviewer=item.reviewer,
            )
            for item in self.index.find_by_normalized_word(language, normalized_word)
        )

    def find_similarity_candidates(
        self, candidate_id: str, limit: int = 100
    ) -> tuple[SimilarityFinding, ...]:
        selected = self.get_candidate(candidate_id)
        if selected is None:
            return ()
        candidates = [
            self.get_candidate(item.candidate.id)
            for item in self.index.find_similarity_candidates(candidate_id, limit)
        ]
        return _similarity_findings(
            self.repository,
            selected,
            [item for item in candidates if item is not None],
        )

    def close(self) -> None:
        self.index.close()


def _similarity_findings(
    repository: DatasetRepository,
    selected: CandidateView,
    candidates: list[CandidateView],
) -> tuple[SimilarityFinding, ...]:
    records = [CandidateRecord(candidate=item.candidate) for item in [selected, *candidates]]
    profile = load_profiles(repository.root)[selected.candidate.language]
    findings = find_similar_words(records, profile)
    word = selected.normalized_word
    return tuple(item for item in findings if item.word_a == word or item.word_b == word)


def open_workbench_view(
    repository: DatasetRepository,
    index_root: Path | None = None,
    *,
    cross_thread: bool = False,
) -> WorkbenchRepositoryView:
    """Select a verified index, otherwise materialize the canonical fallback."""
    path = index_path(repository.root, index_root)
    try:
        index = RepositoryIndex.open(repository, path, cross_thread=cross_thread)
    except RepositoryIndexError as error:
        status = RepositoryIndex.status(repository, path)
        return CanonicalWorkbenchView(
            repository,
            index_state=status.state,
            reason=str(error),
        )
    assert index is not None
    return IndexedWorkbenchView(repository, index)


__all__ = [
    "CandidatePage",
    "CandidateQuery",
    "CandidateSort",
    "CandidateSummary",
    "CanonicalWorkbenchView",
    "IndexedWorkbenchView",
    "MAX_PAGE_SIZE",
    "WorkbenchBackendStatus",
    "WorkbenchRepositoryView",
    "open_workbench_view",
]
