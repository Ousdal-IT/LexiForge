from collections import Counter
from pathlib import Path
from typing import Any

from .blocklists import load_blocklists_with_metadata
from .constants import DEFAULT_DATA_ROOT
from .io import load_language_candidates
from .models import (
    CandidateRecord,
    CandidateStatus,
    LanguageProfile,
    ProvenanceRecord,
    ReviewRecord,
    ScoreResult,
)
from .moderation import latest_reviews, required_criteria_resolved
from .profiles import load_language_profile, load_policy
from .provenance import load_provenance
from .scoring import score_candidate
from .similarity import find_similar_words


def load_curation_data(
    language: str, data_root: Path = DEFAULT_DATA_ROOT
) -> tuple[LanguageProfile, list[CandidateRecord], list[ProvenanceRecord], list[ReviewRecord]]:
    from .moderation import load_reviews

    profile = load_language_profile(language, data_root)
    base = data_root / "languages" / language
    return (
        profile,
        load_language_candidates(language, data_root),
        load_provenance(base / "provenance.csv"),
        load_reviews(base / "reviews.csv"),
    )


def evaluate_release_eligibility(
    candidate: CandidateRecord,
    provenance: ProvenanceRecord | None,
    review: ReviewRecord | None,
    required_criteria: list[str],
    error_blocklist_words: set[str],
) -> list[str]:
    reasons = []
    item = candidate.candidate
    if item.status != CandidateStatus.APPROVED:
        reasons.append("status_not_approved")
    if provenance is None:
        reasons.append("missing_provenance")
    if not item.is_license_eligible:
        reasons.append("license_ineligible")
    if not required_criteria_resolved(review, required_criteria):
        reasons.append("unresolved_required_criteria")
    if item.word in error_blocklist_words:
        reasons.append("error_blocklist_match")
    if review and review.flags:
        reasons.append("unresolved_mandatory_flags")
    return reasons


def build_curation_report(language: str, data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    profile, candidates, provenance, reviews = load_curation_data(language, data_root)
    policy = load_policy(data_root)
    provenance_by_candidate = {item.candidate_id: item for item in provenance}
    reviews_by_candidate = latest_reviews(reviews)
    _, blocklist_entries, _ = load_blocklists_with_metadata(
        data_root / "languages" / language / "blocklists", profile
    )
    error_words = {item.word for item in blocklist_entries if item.severity == "error"}
    warning_words = {item.word for item in blocklist_entries if item.severity != "error"}
    similarity = find_similar_words(candidates, profile)
    similar_words = {item.word_a for item in similarity} | {item.word_b for item in similarity}
    exclusions: Counter[str] = Counter()
    scores: dict[str, ScoreResult] = {}
    eligible = []
    requiring_review = []
    for record in sorted(candidates, key=lambda item: item.candidate.id):
        candidate = record.candidate
        review = reviews_by_candidate.get(candidate.id)
        reasons = evaluate_release_eligibility(
            record,
            provenance_by_candidate.get(candidate.id),
            review,
            policy.required_review_criteria,
            error_words,
        )
        exclusions.update(reasons)
        if not reasons:
            eligible.append(candidate.id)
        if candidate.status in {CandidateStatus.SUBMITTED, CandidateStatus.NEEDS_REVIEW} or reasons:
            requiring_review.append(candidate.id)
        scores[candidate.id] = score_candidate(
            candidate,
            has_provenance=candidate.id in provenance_by_candidate,
            review_complete=required_criteria_resolved(review, policy.required_review_criteria),
            similarity_warning=candidate.word in similar_words,
            blocklist_warning=candidate.word in warning_words,
        )
    histogram = Counter(str((result.total // 10) * 10) for result in scores.values())
    return {
        "schema_version": 1,
        "language": language,
        "candidate_count": len(candidates),
        "status_breakdown": dict(
            sorted(Counter(item.candidate.status.value for item in candidates).items())
        ),
        "category_distribution": dict(
            sorted(
                Counter(item.candidate.category or "uncategorized" for item in candidates).items()
            )
        ),
        "provenance_source_breakdown": dict(
            sorted(Counter(item.source_kind.value for item in provenance).items())
        ),
        "provenance_complete": len(provenance_by_candidate),
        "license_eligible": sum(item.candidate.is_license_eligible for item in candidates),
        "review_completeness_rate": round(len(reviews_by_candidate) / len(candidates), 3)
        if candidates
        else 0.0,
        "approval_rate": round(
            sum(item.candidate.status == CandidateStatus.APPROVED for item in candidates)
            / len(candidates),
            3,
        )
        if candidates
        else 0.0,
        "blocklist_findings": len(
            [
                item
                for item in blocklist_entries
                if item.word in {record.candidate.word for record in candidates}
            ]
        ),
        "similarity_findings": [item.model_dump(mode="json") for item in similarity],
        "score_histogram": dict(sorted(histogram.items(), key=lambda item: int(item[0]))),
        "scores": {key: value.model_dump(mode="json") for key, value in sorted(scores.items())},
        "release_eligible_count": len(eligible),
        "release_eligible_ids": eligible,
        "exclusion_reasons": dict(sorted(exclusions.items())),
        "candidates_requiring_review": sorted(requiring_review),
    }
