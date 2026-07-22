from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from .constants import DEFAULT_DATA_ROOT
from .curation import build_curation_report, load_curation_data
from .dataset import (
    balanced_selection,
    compare_languages,
    dataset_statistics,
    optimisation_report,
    release_plan,
)
from .errors import ConfigurationError, LexiForgeError, ValidationFailure
from .export import approved_words, export_wordlist
from .io import load_blocklists, load_language_candidates
from .manifest import create_manifest, verify_manifest, write_manifest
from .models import CandidateRecord, LanguageProfile, ValidationResult
from .normalize import normalize_word
from .profiles import load_categories, load_policy, load_profiles
from .report import render_analysis_human, render_analysis_markdown, render_json
from .validate import validate_candidates

app = typer.Typer(
    help="Build, validate, analyse, and publish multilingual wordlists.", no_args_is_help=True
)
curate_app = typer.Typer(help="Generate deterministic human-curation reports.")
candidates_app = typer.Typer(help="Inspect and validate local candidate records.")
review_app = typer.Typer(help="Record explicit local moderation decisions.")
release_app = typer.Typer(help="Plan deterministic dataset releases.")
report_app = typer.Typer(help="Generate static public dataset reports.")
app.add_typer(curate_app, name="curate")
app.add_typer(candidates_app, name="candidates")
app.add_typer(review_app, name="review")
app.add_typer(release_app, name="release")
app.add_typer(report_app, name="report")


class ReportFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"
    MARKDOWN = "markdown"


class ExportFormat(StrEnum):
    TXT = "txt"
    JSON = "json"
    CSV = "csv"


def _selected(language: str | None, all_languages: bool) -> list[str]:
    profiles = load_profiles()
    if all_languages:
        return sorted(profiles)
    if language is None:
        raise typer.BadParameter("provide --language or --all")
    if language not in profiles:
        raise typer.BadParameter(f"unknown language: {language}")
    return [language]


def _load_and_validate(
    language: str,
) -> tuple[LanguageProfile, list[CandidateRecord], ValidationResult]:
    load_policy()
    profiles = load_profiles()
    profile = profiles[language]
    records = load_language_candidates(language)
    categories = {category.id for category in load_categories().categories}
    blocklist = load_blocklists(DEFAULT_DATA_ROOT / "languages" / language / "blocklists")
    result = validate_candidates(records, profile, categories, blocklist)
    return profile, records, result


@app.command("languages")
def languages_command() -> None:
    """List configured language profiles."""
    load_policy()
    load_categories()
    for code, profile in sorted(load_profiles().items()):
        typer.echo(f"{code}\t{profile.name}\t{profile.locale}\tvalid")


@app.command()
def validate(
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    all_languages: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    """Validate candidate data structurally."""
    errors = 0
    for code in _selected(language, all_languages):
        _, _, result = _load_and_validate(code)
        for diagnostic in result.diagnostics:
            typer.echo(
                f"{diagnostic.severity}: {diagnostic.file}:{diagnostic.row}: "
                f"{diagnostic.rule_id}: {diagnostic.message}"
            )
        typer.echo(f"{code}: {result.error_count} error(s), {result.warning_count} warning(s)")
        errors += result.error_count
    if errors:
        raise typer.Exit(1)


@app.command()
def analyse(
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    all_languages: Annotated[bool, typer.Option("--all")] = False,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Report deterministic structural statistics."""
    reports = []
    for code in _selected(language, all_languages):
        _load_and_validate(code)
        reports.append(dataset_statistics(code))
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(reports if all_languages else reports[0]), nl=False)
    else:
        renderer = (
            render_analysis_markdown
            if output_format == ReportFormat.MARKDOWN
            else render_analysis_human
        )
        typer.echo("\n".join(renderer(report).rstrip() for report in reports))


@app.command("optimise")
def optimise_command(
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    all_languages: Annotated[bool, typer.Option("--all")] = False,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Suggest deterministic dataset improvements without modifying data."""
    reports = [optimisation_report(code) for code in _selected(language, all_languages)]
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(reports if all_languages else reports[0]), nl=False)
        return
    for report in reports:
        typer.echo(f"Language: {report['language']}")
        for suggestion in report["suggestions"]:
            typer.echo(f"- {suggestion['rule_id']}: {suggestion['message']}")
        if not report["suggestions"]:
            typer.echo("- No structural optimisation suggestions.")


@app.command("compare")
def compare_command(
    left: str,
    right: str,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Compare two language datasets structurally, without translation."""
    _selected(left, False)
    _selected(right, False)
    comparison = compare_languages(left, right)
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(comparison), nl=False)
        return
    typer.echo(f"Structural comparison: {left} / {right}")
    for language in (left, right):
        item = comparison["comparison"][language]
        typer.echo(
            f"{language}: {item['candidate_count']} candidates, "
            f"{item['approved_count']} approved, "
            f"provenance {item['provenance_complete']}/{item['candidate_count']}"
        )


@release_app.command("plan")
def release_plan_command(
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    all_languages: Annotated[bool, typer.Option("--all")] = False,
    target_size: Annotated[int | None, typer.Option("--size")] = None,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Plan release gaps without inventing candidate words."""
    if language is None and not all_languages:
        all_languages = True
    plans = [release_plan(code, target_size) for code in _selected(language, all_languages)]
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(plans if all_languages else plans[0]), nl=False)
        return
    for plan in plans:
        typer.echo(f"Language: {plan['language']}")
        typer.echo(f"Eligible candidates: {plan['eligible_count']}")
        typer.echo(f"Missing for {plan['target_size']} release: {plan['missing_count']}")
        typer.echo("Approximate category needs:")
        for category, count in plan["category_needs"].items():
            typer.echo(f"- {category}: {count}")


@report_app.command("publish")
def report_publish_command(
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")] = Path("build/site"),
) -> None:
    """Generate a deterministic static directory suitable for GitHub Pages."""
    from .publication import publish_reports

    files = publish_reports(output_dir)
    typer.echo(f"published {len(files)} static report files to {output_dir}")


@report_app.command("generate")
def report_generate_command(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_format: Annotated[str, typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Generate one deterministic Markdown, JSON, or static HTML dataset report."""
    from .dataset import dataset_statistics
    from .publication import render_dataset_html, render_dataset_markdown

    _selected(language, False)
    statistics = dataset_statistics(language)
    plan = release_plan(language)
    if output_format == "markdown":
        content = render_dataset_markdown(statistics, plan)
    elif output_format == "json":
        content = render_json({"statistics": statistics, "release_plan": plan})
    elif output_format == "html":
        content = render_dataset_html(statistics, plan)
    else:
        raise typer.BadParameter("report format must be markdown, json, or html")
    if output is None:
        typer.echo(content, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")


@app.command("similarity")
def similarity_command(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Find deterministic, advisory similar-word pairs."""
    from .similarity import find_similar_words

    _selected(language, False)
    profile, records, _ = _load_and_validate(language)
    findings = [item.model_dump(mode="json") for item in find_similar_words(records, profile)]
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(findings), nl=False)
        return
    if not findings:
        typer.echo(f"{language}: no similarity findings")
        return
    for item in findings:
        typer.echo(
            f"{item['language']}: {item['word_a']} / {item['word_b']} "
            f"[{item['rule_id']}, distance={item['distance']}]"
        )


@app.command("score")
def score_command(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
) -> None:
    """Show explainable advisory candidate scores without changing status."""
    report = build_curation_report(language)
    scores = report["scores"]
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(scores), nl=False)
    else:
        for candidate_id, result in scores.items():
            signal_ids = ", ".join(signal["id"] for signal in result["signals"])
            typer.echo(f"{candidate_id}: {result['total']} ({signal_ids})")


@curate_app.command("report")
def curate_report_command(
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    all_languages: Annotated[bool, typer.Option("--all")] = False,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.HUMAN,
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
) -> None:
    """Generate concise deterministic curation reports."""
    reports = [build_curation_report(code) for code in _selected(language, all_languages)]
    for report in reports:
        if output_format == ReportFormat.JSON:
            content = render_json(report)
            suffix = "json"
        elif output_format == ReportFormat.MARKDOWN:
            content = (
                f"# LexiForge curation report: {report['language']}\n\n"
                f"- Candidates: {report['candidate_count']}\n"
                f"- Release eligible: {report['release_eligible_count']}\n"
                f"- Similarity findings: {len(report['similarity_findings'])}\n"
                f"- Requiring review: {len(report['candidates_requiring_review'])}\n"
            )
            suffix = "md"
        else:
            content = (
                f"{report['language']}: {report['candidate_count']} candidates; "
                f"{report['release_eligible_count']} release eligible; "
                f"{len(report['candidates_requiring_review'])} require review\n"
            )
            suffix = "txt"
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"curation-{report['language']}.{suffix}").write_text(
                content, encoding="utf-8"
            )
        else:
            typer.echo(content, nl=False)


@candidates_app.command("list")
def candidates_list(language: Annotated[str, typer.Option("--language", "-l")]) -> None:
    """List candidates in stable ID order."""
    _, records, _, _ = load_curation_data(language)
    for record in sorted(records, key=lambda item: item.candidate.id):
        item = record.candidate
        typer.echo(f"{item.id}\t{item.word}\t{item.status.value}")


@candidates_app.command("show")
def candidates_show(candidate_id: str) -> None:
    """Show one candidate and its curation records as JSON."""
    for code in sorted(load_profiles()):
        _, records, provenance, reviews = load_curation_data(code)
        for record in records:
            if record.candidate.id == candidate_id:
                payload = {
                    "candidate": record.candidate.model_dump(mode="json"),
                    "provenance": [
                        item.model_dump(mode="json")
                        for item in provenance
                        if item.candidate_id == candidate_id
                    ],
                    "reviews": [
                        item.model_dump(mode="json")
                        for item in reviews
                        if item.candidate_id == candidate_id
                    ],
                }
                typer.echo(render_json(payload), nl=False)
                return
    raise ValidationFailure(f"candidate not found: {candidate_id}")


@candidates_app.command("validate")
def candidates_validate(language: Annotated[str, typer.Option("--language", "-l")]) -> None:
    """Validate candidate and linked curation data."""
    from .moderation import validate_review_history
    from .provenance import validate_provenance_links

    _, records, provenance, reviews = load_curation_data(language)
    statuses = {item.candidate.id: item.candidate.status for item in records}
    errors = validate_provenance_links(provenance, set(statuses)) + validate_review_history(
        reviews, statuses
    )
    if errors:
        for error in errors:
            typer.echo(f"error: {error}")
        raise typer.Exit(1)
    typer.echo(f"{language}: candidate, provenance, and review links valid")


@candidates_app.command("import")
def candidates_import(
    path: Path,
    language: Annotated[str, typer.Option("--language", "-l")],
    source_type: Annotated[str, typer.Option("--source-type")],
    submitted_by: Annotated[str, typer.Option("--submitted-by")],
    license_eligibility: Annotated[str, typer.Option("--license-eligibility")],
    apply: Annotated[bool, typer.Option("--apply")] = False,
) -> None:
    """Import a local TXT/JSON/CSV batch; dry-run unless --apply is given."""
    from .batch import import_candidate_batch
    from .models import SourceType

    if license_eligibility not in {"eligible", "ineligible"}:
        raise typer.BadParameter("license eligibility must be eligible or ineligible")
    try:
        parsed_source = SourceType(source_type)
    except ValueError:
        raise typer.BadParameter(f"unknown source type: {source_type}") from None
    result = import_candidate_batch(
        path,
        language,
        parsed_source,
        submitted_by,
        license_eligibility == "eligible",
        apply=apply,
    )
    typer.echo(render_json(result), nl=False)


def _review_command(
    candidate_id: str,
    decision: str,
    reviewer: str,
    criteria_file: Path | None,
    comment: str,
    apply: bool,
    reviewed_at: str | None,
) -> None:
    from .models import ReviewDecision
    from .review_workflow import load_criteria, moderate_candidate

    result = moderate_candidate(
        candidate_id,
        ReviewDecision(decision),
        reviewer,
        load_criteria(criteria_file),
        comment,
        apply=apply,
        reviewed_at=reviewed_at,
    )
    typer.echo(render_json(result), nl=False)


@review_app.command("approve")
def review_approve(
    candidate_id: str,
    reviewer: Annotated[str, typer.Option("--reviewer")],
    criteria_file: Annotated[Path, typer.Option("--criteria-file")],
    comment: Annotated[str, typer.Option("--comment")] = "",
    apply: Annotated[bool, typer.Option("--apply")] = False,
    reviewed_at: Annotated[str | None, typer.Option("--reviewed-at")] = None,
) -> None:
    """Approve a needs-review candidate; dry-run by default."""
    _review_command(candidate_id, "approve", reviewer, criteria_file, comment, apply, reviewed_at)


@review_app.command("reject")
def review_reject(
    candidate_id: str,
    reviewer: Annotated[str, typer.Option("--reviewer")],
    comment: Annotated[str, typer.Option("--comment")] = "",
    apply: Annotated[bool, typer.Option("--apply")] = False,
    reviewed_at: Annotated[str | None, typer.Option("--reviewed-at")] = None,
) -> None:
    """Reject a submitted or needs-review candidate; dry-run by default."""
    _review_command(candidate_id, "reject", reviewer, None, comment, apply, reviewed_at)


@review_app.command("needs-review")
def review_needs_review(
    candidate_id: str,
    reviewer: Annotated[str, typer.Option("--reviewer")],
    comment: Annotated[str, typer.Option("--comment")] = "",
    apply: Annotated[bool, typer.Option("--apply")] = False,
    reviewed_at: Annotated[str | None, typer.Option("--reviewed-at")] = None,
) -> None:
    """Return a submitted or rejected candidate to human review."""
    _review_command(candidate_id, "needs_review", reviewer, None, comment, apply, reviewed_at)


def _ensure_safe_output(output: Path, force: bool) -> None:
    try:
        output.resolve().relative_to(DEFAULT_DATA_ROOT.resolve())
    except ValueError:
        pass
    else:
        if not force:
            raise ValidationFailure("refusing to overwrite a path inside source data; use --force")
    if output.exists() and not force:
        raise ValidationFailure(f"output already exists: {output}; use --force")


@app.command()
def export(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_format: Annotated[ExportFormat, typer.Option("--format")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Export approved words in one deterministic format."""
    _selected(language, False)
    _ensure_safe_output(output, force)
    profile, records, result = _load_and_validate(language)
    if not result.valid:
        raise ValidationFailure(f"{language} has {result.error_count} validation error(s)")
    eligible_ids = set(build_curation_report(language)["release_eligible_ids"])
    eligible_records = [record for record in records if record.candidate.id in eligible_ids]
    export_wordlist(eligible_records, profile, output_format.value, output)
    typer.echo(f"wrote {len(approved_words(eligible_records, profile))} words to {output}")


@app.command()
def build(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")],
    force: Annotated[bool, typer.Option("--force")] = False,
    size: Annotated[int | None, typer.Option("--size")] = None,
    allow_development_size: Annotated[bool, typer.Option("--allow-development-size")] = False,
    balanced: Annotated[bool, typer.Option("--balanced")] = False,
) -> None:
    """Validate, export all formats, write a manifest, and verify hashes."""
    _selected(language, False)
    _ensure_safe_output(output_dir, force)
    profile, records, result = _load_and_validate(language)
    if not result.valid:
        raise ValidationFailure(f"{language} has {result.error_count} validation error(s)")
    report = build_curation_report(language)
    eligible_ids = set(report["release_eligible_ids"])
    eligible_records = [record for record in records if record.candidate.id in eligible_ids]
    eligible_records.sort(key=lambda item: normalize_word(item.candidate.word, profile))
    policy = load_policy()
    if (
        size is not None
        and size not in profile.target_sizes
        and (not allow_development_size or size not in policy.development_sizes)
    ):
        raise ValidationFailure(
            f"size {size} is not a production target; use an allowed development size "
            "with --allow-development-size"
        )
    if size is not None:
        if len(eligible_records) < size:
            raise ValidationFailure(
                f"requested {size} words but only {len(eligible_records)} are release eligible"
            )
        eligible_records = (
            balanced_selection(eligible_records, language, size)
            if balanced
            else eligible_records[:size]
        )
    elif balanced:
        eligible_records = balanced_selection(eligible_records, language, len(eligible_records))
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for output_format in ExportFormat:
        path = output_dir / f"lexiforge-{language}-dev.{output_format.value}"
        files.append(export_wordlist(eligible_records, profile, output_format.value, path))
    words = approved_words(eligible_records, profile)
    manifest = create_manifest(profile, len(words), files)
    write_manifest(manifest, output_dir / "manifest.json")
    verify_manifest(manifest, output_dir, len(words))
    typer.echo(
        f"built {language}: {len(words)} approved words, {len(files)} exports; hashes verified"
    )


def main() -> None:
    try:
        app()
    except ConfigurationError as error:
        typer.echo(f"error: {error}", err=True)
        raise SystemExit(2) from None
    except LexiForgeError as error:
        typer.echo(f"error: {error}", err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
