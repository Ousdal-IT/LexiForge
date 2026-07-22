from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from .analyse import analyse_candidates
from .constants import DEFAULT_DATA_ROOT
from .errors import ConfigurationError, LexiForgeError, ValidationFailure
from .export import approved_words, export_wordlist
from .io import load_blocklists, load_language_candidates
from .manifest import create_manifest, verify_manifest, write_manifest
from .models import CandidateRecord, LanguageProfile, ValidationResult
from .profiles import load_categories, load_policy, load_profiles
from .report import render_analysis_human, render_analysis_markdown, render_json
from .validate import validate_candidates

app = typer.Typer(
    help="Build, validate, analyse, and publish multilingual wordlists.", no_args_is_help=True
)


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
        profile, records, result = _load_and_validate(code)
        reports.append(analyse_candidates(records, profile, result))
    if output_format == ReportFormat.JSON:
        typer.echo(render_json(reports if all_languages else reports[0]), nl=False)
    else:
        renderer = (
            render_analysis_markdown
            if output_format == ReportFormat.MARKDOWN
            else render_analysis_human
        )
        typer.echo("\n".join(renderer(report).rstrip() for report in reports))


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
    export_wordlist(records, profile, output_format.value, output)
    typer.echo(f"wrote {len(approved_words(records, profile))} words to {output}")


@app.command()
def build(
    language: Annotated[str, typer.Option("--language", "-l")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Validate, export all formats, write a manifest, and verify hashes."""
    _selected(language, False)
    _ensure_safe_output(output_dir, force)
    profile, records, result = _load_and_validate(language)
    if not result.valid:
        raise ValidationFailure(f"{language} has {result.error_count} validation error(s)")
    ineligible = [
        record.candidate.id
        for record in records
        if record.candidate.status.value == "approved" and not record.candidate.license_eligible
    ]
    if ineligible:
        raise ValidationFailure(
            "cannot claim CC0: approved records are not marked license eligible: "
            + ", ".join(ineligible)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for output_format in ExportFormat:
        path = output_dir / f"lexiforge-{language}-dev.{output_format.value}"
        files.append(export_wordlist(records, profile, output_format.value, path))
    words = approved_words(records, profile)
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
