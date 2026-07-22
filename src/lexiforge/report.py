import json
from typing import Any


def render_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_analysis_human(report: dict[str, Any]) -> str:
    lines = [
        f"Language: {report['language']}",
        f"Total records: {report['total_records']}",
        f"Unique normalized words: {report['unique_normalized_words']}",
        f"Word length: {report['minimum_word_length']}–{report['maximum_word_length']} "
        f"(average {report['average_word_length']})",
        f"Duplicate candidates: {report['duplicate_candidates']}",
        f"Validation: {report['validation_error_count']} error(s), "
        f"{report['validation_warning_count']} warning(s)",
        "Statuses: "
        + ", ".join(f"{key}={value}" for key, value in report["records_by_status"].items()),
        "Categories: "
        + ", ".join(f"{key}={value}" for key, value in report["records_by_category"].items()),
    ]
    return "\n".join(lines) + "\n"


def render_analysis_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# LexiForge analysis: {report['language']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total records | {report['total_records']} |",
        f"| Unique normalized words | {report['unique_normalized_words']} |",
        f"| Minimum word length | {report['minimum_word_length']} |",
        f"| Maximum word length | {report['maximum_word_length']} |",
        f"| Average word length | {report['average_word_length']} |",
        f"| Words with non-ASCII letters | {report['words_with_non_ascii_letters']} |",
        f"| Duplicate candidates | {report['duplicate_candidates']} |",
        f"| Validation errors | {report['validation_error_count']} |",
        f"| Validation warnings | {report['validation_warning_count']} |",
        "",
    ]
    return "\n".join(lines)
