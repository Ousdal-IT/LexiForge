from html import escape
from pathlib import Path
from typing import Any

from .constants import DEFAULT_DATA_ROOT
from .dataset import dataset_statistics, release_plan
from .profiles import load_profiles
from .report import render_json
from .visualise import bar_chart_svg


def _table(title: str, values: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in sorted(values.items())
    )
    return f"<h2>{escape(title)}</h2><table>{rows}</table>"


def render_dataset_html(statistics: dict[str, Any], plan: dict[str, Any]) -> str:
    language = statistics["language"]
    body = [
        f"<h1>LexiForge dataset report: {escape(language)}</h1>",
        '<p class="notice">Development data only; not a production passphrase wordlist.</p>',
        _table(
            "Summary",
            {
                "Candidates": statistics["total_records"],
                "Approved": statistics["records_by_status"].get("approved", 0),
                "Release eligible": plan["eligible_count"],
                "Target": plan["target_size"],
                "Missing": plan["missing_count"],
                "Review completion": statistics["review_completion"]["rate"],
            },
        ),
        _table("Categories", statistics["records_by_category"]),
        _table("Word lengths", statistics["word_length_histogram"]),
        "<h2>Charts</h2><ul>",
        '<li><a href="word-length.svg">Word length</a></li>',
        '<li><a href="categories.svg">Category distribution</a></li>',
        '<li><a href="characters.svg">Character frequency</a></li>',
        '<li><a href="review-status.svg">Review status</a></li>',
        '<li><a href="release-readiness.svg">Release readiness</a></li>',
        "</ul>",
    ]
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>LexiForge {escape(language)} dataset report</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:64rem;"
        "margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse}th,td{border:1px solid #bbb;"
        "padding:.35rem .6rem;text-align:left}"
        ".notice{background:#fff4ce;padding:.75rem}</style></head><body>"
        + "".join(body)
        + "</body></html>\n"
    )


def render_dataset_markdown(statistics: dict[str, Any], plan: dict[str, Any]) -> str:
    lines = [
        f"# LexiForge dataset report: {statistics['language']}",
        "",
        "> Development data only; not a production passphrase wordlist.",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Candidates | {statistics['total_records']} |",
        f"| Approved | {statistics['records_by_status'].get('approved', 0)} |",
        f"| Release eligible | {plan['eligible_count']} |",
        f"| Target | {plan['target_size']} |",
        f"| Missing | {plan['missing_count']} |",
        f"| Review completion | {statistics['review_completion']['rate']} |",
        "",
        "## Word-length histogram",
        "",
    ]
    lines.extend(
        f"- `{length}`: {count}" for length, count in statistics["word_length_histogram"].items()
    )
    lines.extend(["", "## Category distribution", ""])
    lines.extend(
        f"- `{category}`: {count}" for category, count in statistics["records_by_category"].items()
    )
    return "\n".join(lines) + "\n"


def publish_reports(output_dir: Path, data_root: Path = DEFAULT_DATA_ROOT) -> list[Path]:
    profiles = load_profiles(data_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    links = []
    for language in sorted(profiles):
        directory = output_dir / language
        directory.mkdir(parents=True, exist_ok=True)
        statistics = dataset_statistics(language, data_root)
        plan = release_plan(language, data_root=data_root)
        assets = {
            "word-length.svg": bar_chart_svg(
                "Word length",
                {key: int(value) for key, value in statistics["word_length_histogram"].items()},
            ),
            "categories.svg": bar_chart_svg("Categories", statistics["records_by_category"]),
            "characters.svg": bar_chart_svg("Characters", statistics["character_frequency"]),
            "review-status.svg": bar_chart_svg("Review status", statistics["records_by_status"]),
            "release-readiness.svg": bar_chart_svg(
                "Release readiness",
                {"eligible": plan["eligible_count"], "missing": plan["missing_count"]},
            ),
        }
        files = {
            "index.html": render_dataset_html(statistics, plan),
            "report.json": render_json({"statistics": statistics, "release_plan": plan}),
            **assets,
        }
        for name, content in sorted(files.items()):
            path = directory / name
            path.write_text(content, encoding="utf-8")
            generated.append(path)
        links.append(
            f'<li><a href="{language}/index.html">{escape(profiles[language].name)}</a></li>'
        )
    index = output_dir / "index.html"
    index.write_text(
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>LexiForge dataset reports</title></head><body>"
        "<h1>LexiForge dataset reports</h1>"
        "<p>Development datasets only; not production passphrase wordlists.</p><ul>"
        + "".join(links)
        + "</ul></body></html>\n",
        encoding="utf-8",
    )
    generated.append(index)
    return sorted(generated)
