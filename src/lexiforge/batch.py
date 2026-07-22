import csv
import io
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .atomic import atomic_write_text
from .constants import DEFAULT_DATA_ROOT
from .errors import DataFormatError, ValidationFailure
from .io import load_language_candidates
from .models import CandidateStatus, SourceType, WordCandidate
from .normalize import normalize_word
from .profiles import load_language_profile


def read_batch_words(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".txt":
            words = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        elif path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise DataFormatError("JSON candidate batch must be a list")
            words = [item if isinstance(item, str) else item["word"] for item in payload]
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                words = [row["word"] for row in csv.DictReader(handle)]
        else:
            raise DataFormatError("candidate import supports only .txt, .json, and .csv")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DataFormatError(f"cannot read candidate batch {path}: {error}") from error
    if len(words) != len(set(words)):
        raise ValidationFailure("candidate batch contains duplicate words")
    return words


def stable_candidate_id(language: str, normalized_word: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"lexiforge:candidate:{language}:{normalized_word}"))


def import_candidate_batch(
    path: Path,
    language: str,
    source_type: SourceType,
    submitted_by: str,
    license_eligible: bool,
    *,
    apply: bool = False,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> dict[str, object]:
    if source_type == SourceType.IMPORT and license_eligible:
        raise ValidationFailure(
            "bulk import cannot be marked license eligible without later review"
        )
    profile = load_language_profile(language, data_root)
    words = read_batch_words(path)
    existing = load_language_candidates(language, data_root)
    existing_words = {normalize_word(item.candidate.word, profile) for item in existing}
    additions = []
    for word in sorted(words):
        normalized = normalize_word(word, profile)
        if normalized in existing_words:
            raise ValidationFailure(f"candidate already exists for {language}: {word!r}")
        candidate_id = stable_candidate_id(language, normalized)
        additions.append(
            WordCandidate(
                id=candidate_id,
                language=language,
                word=word,
                status=CandidateStatus.SUBMITTED,
                source_type=source_type,
                submitted_by=submitted_by,
                license_eligible=license_eligible,
                notes="local batch import",
            )
        )
    report: dict[str, object] = {
        "schema_version": 1,
        "applied": apply,
        "language": language,
        "candidate_count": len(additions),
        "candidates": [
            {
                "id": item.id,
                "normalized_word": normalize_word(item.word, profile),
                "word": item.word,
            }
            for item in additions
        ],
    }
    if not apply:
        return report
    candidate_path = data_root / "languages" / language / "candidates.csv"
    provenance_path = data_root / "languages" / language / "provenance.csv"
    candidate_content = candidate_path.read_text(encoding="utf-8")
    provenance_content = provenance_path.read_text(encoding="utf-8")
    candidate_buffer = io.StringIO(newline="")
    candidate_buffer.write(candidate_content)
    candidate_writer = csv.writer(candidate_buffer, lineterminator="\n")
    provenance_buffer = io.StringIO(newline="")
    provenance_buffer.write(provenance_content)
    provenance_writer = csv.writer(provenance_buffer, lineterminator="\n")
    for item in additions:
        candidate_writer.writerow(
            [
                item.id,
                language,
                item.word,
                "submitted",
                "",
                source_type.value,
                "",
                "",
                "",
                str(license_eligible).lower(),
                "local batch import",
            ]
        )
        provenance_writer.writerow(
            [
                f"p-{item.id}",
                item.id,
                "manual" if source_type == SourceType.IMPORT else source_type.value,
                "",
                f"Local explicit batch contribution by {submitted_by}",
                "Contributor assertion; pending review",
                str(source_type != SourceType.IMPORT).lower(),
                str(source_type == SourceType.IMPORT).lower(),
                "",
                "local batch import",
            ]
        )
    atomic_write_text(candidate_path, candidate_buffer.getvalue())
    atomic_write_text(provenance_path, provenance_buffer.getvalue())
    return report
