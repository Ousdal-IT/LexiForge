"""Deterministic, UI-independent power tools for the editorial workbench."""

import csv
import io
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..models import CandidateRecord, CandidateStatus, SimilarityFinding
from ..profiles import load_profiles
from ..similarity import find_similar_words
from .model import CandidateFilter, CandidateView, RepositorySnapshot


@dataclass(frozen=True, slots=True)
class RepositoryStatistics:
    total_candidates: int
    languages: dict[str, int]
    categories: dict[str, int]
    statuses: dict[str, int]
    approved: int
    pending_reviews: int
    flagged: int
    release_eligible: int
    release_blocked: int
    provenance_missing: int
    duplicate_warnings: int
    blocklist_matches: int
    license_distribution: dict[str, int]
    contributors: dict[str, int]
    reviewers: dict[str, int]
    average_review_time_seconds: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_csv(self) -> str:
        rows = [
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
            for key, value in self.as_dict().items()
        ]
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("metric", "value"))
        writer.writerows(rows)
        return output.getvalue()


def repository_statistics(snapshot: RepositorySnapshot) -> RepositoryStatistics:
    candidates = snapshot.candidates
    statuses = Counter(item.candidate.status.value for item in candidates)
    languages = Counter(item.candidate.language for item in candidates)
    categories = Counter(item.candidate.category or "uncategorized" for item in candidates)
    contributors = Counter(item.candidate.submitted_by or "unknown" for item in candidates)
    reviewers = Counter(review.reviewer_id for item in candidates for review in item.reviews)
    review_times: list[float] = []
    for item in candidates:
        submitted = item.candidate.submitted_at
        if submitted is None:
            continue
        for review in item.reviews:
            review_times.append((review.reviewed_at - submitted).total_seconds())
    return RepositoryStatistics(
        total_candidates=len(candidates),
        languages=dict(sorted(languages.items())),
        categories=dict(sorted(categories.items())),
        statuses=dict(sorted(statuses.items())),
        approved=statuses[CandidateStatus.APPROVED.value],
        pending_reviews=sum(
            item.candidate.status in {CandidateStatus.SUBMITTED, CandidateStatus.NEEDS_REVIEW}
            for item in candidates
        ),
        flagged=sum(item.review_state == "flagged" for item in candidates),
        release_eligible=sum(item.release_eligible for item in candidates),
        release_blocked=sum(not item.release_eligible for item in candidates),
        provenance_missing=sum(not item.provenance for item in candidates),
        duplicate_warnings=sum(
            "duplicate" in reason for item in candidates for reason in item.eligibility_reasons
        ),
        blocklist_matches=sum(item.blocklist_match for item in candidates),
        license_distribution=dict(
            sorted(
                Counter(
                    "eligible" if item.candidate.is_license_eligible else "ineligible"
                    for item in candidates
                ).items()
            )
        ),
        contributors=dict(sorted(contributors.items())),
        reviewers=dict(sorted(reviewers.items())),
        average_review_time_seconds=(
            sum(review_times) / len(review_times) if review_times else None
        ),
    )


def similarity_browser(
    snapshot: RepositorySnapshot, language: str | None = None
) -> tuple[SimilarityFinding, ...]:
    profiles = load_profiles(snapshot.root)
    findings: list[SimilarityFinding] = []
    for code in sorted(profiles):
        if language and code != language:
            continue
        records = [item for item in snapshot.candidates if item.candidate.language == code]
        findings.extend(find_similar_words([_record(item) for item in records], profiles[code]))
    return tuple(
        sorted(findings, key=lambda item: (item.language, item.word_a, item.word_b, item.rule_id))
    )


def _record(item: CandidateView) -> CandidateRecord:
    return CandidateRecord(candidate=item.candidate)


@dataclass(frozen=True, slots=True)
class SavedSearch:
    name: str
    filters: CandidateFilter


class SavedSearchStore:
    """Stores editor-only searches outside the dataset repository."""

    def __init__(self, path: Path | None = None):
        configured = os.environ.get("LEXIFORGE_EDITOR_STATE")
        self.path = path or Path(configured or (Path.home() / ".config/lexiforge/workbench.json"))

    def load(self) -> dict[str, SavedSearch]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
            return {}
        result: dict[str, SavedSearch] = {}
        for name, values in payload.get("saved_searches", {}).items():
            result[name] = SavedSearch(
                name=name,
                filters=CandidateFilter(
                    search=str(values.get("search", "")),
                    language=values.get("language"),
                    category=values.get("category"),
                    status=CandidateStatus(values["status"]) if values.get("status") else None,
                    release_eligible=values.get("release_eligible"),
                    review_state=values.get("review_state"),
                    contributor=values.get("contributor"),
                    reviewer=values.get("reviewer"),
                    source_type=values.get("source_type"),
                    license_eligible=values.get("license_eligible"),
                    blocklist_state=values.get("blocklist_state"),
                ),
            )
        return result

    def save(self, searches: dict[str, SavedSearch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_searches": {
                name: {
                    "search": item.filters.search,
                    "language": item.filters.language,
                    "category": item.filters.category,
                    "status": item.filters.status.value if item.filters.status else None,
                    "release_eligible": item.filters.release_eligible,
                    "review_state": item.filters.review_state,
                    "contributor": item.filters.contributor,
                    "reviewer": item.filters.reviewer,
                    "source_type": item.filters.source_type,
                    "license_eligible": item.filters.license_eligible,
                    "blocklist_state": item.filters.blocklist_state,
                }
                for name, item in sorted(searches.items())
            }
        }
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


@dataclass(frozen=True, slots=True)
class SessionState:
    repository: str | None = None
    language: str | None = None
    search: str = ""
    category: str | None = None
    status: str | None = None
    release_eligible: bool | None = None
    sort_field: str = "word"
    sort_reverse: bool = False
    selected_candidate: str | None = None


class SessionStore:
    def __init__(self, path: Path | None = None):
        configured = os.environ.get("LEXIFORGE_EDITOR_STATE")
        self.path = path or Path(
            configured or (Path.home() / ".config/lexiforge/workbench-session.json")
        )

    def load(self) -> SessionState:
        try:
            return SessionState(**json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, OSError, UnicodeError, TypeError, ValueError):
            return SessionState()

    def save(self, state: SessionState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(asdict(state), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
