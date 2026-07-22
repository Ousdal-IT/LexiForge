from collections import Counter
from pathlib import Path
from typing import Any

from .analyse import analyse_candidates
from .constants import DEFAULT_DATA_ROOT
from .curation import build_curation_report, load_curation_data
from .models import CandidateRecord, CandidateStatus, ValidationResult
from .normalize import normalize_word
from .profiles import load_categories


def dataset_statistics(language: str, data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    profile, candidates, _, _ = load_curation_data(language, data_root)
    statistics = analyse_candidates(candidates, profile, ValidationResult())
    curation = build_curation_report(language, data_root)
    statistics.update(
        {
            "review_completion": {
                "rate": curation["review_completeness_rate"],
                "reviewed": round(curation["review_completeness_rate"] * len(candidates)),
                "total": len(candidates),
            },
            "provenance_summary": curation["provenance_source_breakdown"],
            "provenance_complete": curation["provenance_complete"],
            "score_distribution": curation["score_histogram"],
            "release_eligibility": {
                "eligible": curation["release_eligible_count"],
                "ineligible": len(candidates) - curation["release_eligible_count"],
                "exclusion_reasons": curation["exclusion_reasons"],
            },
            "similarity_finding_count": len(curation["similarity_findings"]),
        }
    )
    return statistics


def optimisation_report(language: str, data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    statistics = dataset_statistics(language, data_root)
    profile, candidates, _, _ = load_curation_data(language, data_root)
    words = sorted(normalize_word(item.candidate.word, profile) for item in candidates)
    suggestions: list[dict[str, Any]] = []

    def add(rule_id: str, message: str, evidence: dict[str, Any]) -> None:
        suggestions.append({"rule_id": rule_id, "message": message, "evidence": evidence})

    categories = statistics["records_by_category"]
    if categories and max(categories.values()) - min(categories.values()) > 1:
        add(
            "optimise.category_imbalance",
            "Consider reviewing underrepresented categories.",
            categories,
        )
    lengths = statistics["word_length_histogram"]
    if lengths and max(lengths.values()) > max(2, len(words) // 3):
        add(
            "optimise.word_length_imbalance",
            "One word length accounts for a large share of candidates.",
            lengths,
        )
    for label, counter in (
        ("prefix", Counter(word[:2] for word in words if len(word) >= 2)),
        ("suffix", Counter(word[-2:] for word in words if len(word) >= 2)),
    ):
        repeated = {key: value for key, value in sorted(counter.items()) if value >= 3}
        if repeated:
            add(
                f"optimise.repeated_{label}",
                f"Review heavily repeated two-letter {label}es.",
                repeated,
            )
    doubled = sorted(
        word for word in words if any(a == b for a, b in zip(word, word[1:], strict=False))
    )
    if doubled:
        add(
            "optimise.repeated_letter_pattern",
            "Review concentration of double-letter spellings.",
            {"words": doubled},
        )
    characters = statistics["character_frequency"]
    if characters:
        average = sum(characters.values()) / len(characters)
        skewed = {key: value for key, value in sorted(characters.items()) if value > average * 1.8}
        if skewed:
            add(
                "optimise.character_distribution",
                "Some characters occur substantially more often than average.",
                skewed,
            )
    rare_bigrams = sorted(
        key for key, value in statistics["bigram_frequency"].items() if value == 1
    )
    if rare_bigrams:
        add(
            "optimise.uncommon_letter_combinations",
            "Review single-occurrence bigrams for readability; rarity is not an error.",
            {"bigrams": rare_bigrams},
        )
    if statistics["similarity_finding_count"]:
        add(
            "optimise.excessive_similarity",
            "Review advisory similar-word pairs before release.",
            {"finding_count": statistics["similarity_finding_count"]},
        )
    return {
        "schema_version": 1,
        "language": language,
        "candidate_count": len(candidates),
        "suggestions": sorted(suggestions, key=lambda item: item["rule_id"]),
    }


def release_plan(
    language: str, target_size: int | None = None, data_root: Path = DEFAULT_DATA_ROOT
) -> dict[str, Any]:
    profile, candidates, _, _ = load_curation_data(language, data_root)
    target = target_size or min(profile.target_sizes)
    curation = build_curation_report(language, data_root)
    eligible_ids = set(curation["release_eligible_ids"])
    eligible = [item for item in candidates if item.candidate.id in eligible_ids]
    categories = [item.id for item in load_categories(data_root).categories]
    category_counts = Counter(item.candidate.category or "uncategorized" for item in eligible)
    desired_base, remainder = divmod(target, len(categories))
    needs = {}
    for index, category in enumerate(categories):
        desired = desired_base + int(index < remainder)
        needs[category] = max(0, desired - category_counts.get(category, 0))
    approved = sum(item.candidate.status == CandidateStatus.APPROVED for item in candidates)
    return {
        "schema_version": 1,
        "language": language,
        "target_size": target,
        "candidate_count": len(candidates),
        "approved_count": approved,
        "eligible_count": len(eligible),
        "missing_count": max(0, target - len(eligible)),
        "category_needs": dict(sorted(needs.items())),
        "ready": len(eligible) >= target,
    }


def compare_languages(left: str, right: str, data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    left_stats = dataset_statistics(left, data_root)
    right_stats = dataset_statistics(right, data_root)

    def summary(statistics: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_count": statistics["total_records"],
            "approved_count": statistics["records_by_status"].get("approved", 0),
            "category_distribution": statistics["records_by_category"],
            "word_length_histogram": statistics["word_length_histogram"],
            "character_frequency": statistics["character_frequency"],
            "review_completion": statistics["review_completion"],
            "provenance_complete": statistics["provenance_complete"],
        }

    return {
        "schema_version": 1,
        "languages": [left, right],
        "comparison": {left: summary(left_stats), right: summary(right_stats)},
        "scope": "structural_only_no_semantic_or_translation_comparison",
    }


def balanced_selection(
    records: list[CandidateRecord], language: str, size: int, data_root: Path = DEFAULT_DATA_ROOT
) -> list[CandidateRecord]:
    profile = load_curation_data(language, data_root)[0]
    curation = build_curation_report(language, data_root)
    scores = curation["scores"]
    remaining = sorted(records, key=lambda item: normalize_word(item.candidate.word, profile))
    selected: list[CandidateRecord] = []
    categories: Counter[str] = Counter()
    lengths: Counter[int] = Counter()
    initials: Counter[str] = Counter()
    while remaining and len(selected) < size:
        chosen = min(
            remaining,
            key=lambda item: (
                categories[item.candidate.category or "uncategorized"],
                lengths[len(normalize_word(item.candidate.word, profile))],
                initials[normalize_word(item.candidate.word, profile)[0]],
                -scores[item.candidate.id]["total"],
                normalize_word(item.candidate.word, profile),
            ),
        )
        remaining.remove(chosen)
        selected.append(chosen)
        word = normalize_word(chosen.candidate.word, profile)
        categories[chosen.candidate.category or "uncategorized"] += 1
        lengths[len(word)] += 1
        initials[word[0]] += 1
    return selected
