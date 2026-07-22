import csv
from pathlib import Path

from pydantic import ValidationError

from .constants import CSV_COLUMNS, DEFAULT_DATA_ROOT
from .errors import DataFormatError
from .models import CandidateRecord, candidate_from_csv


def load_candidates(path: Path) -> list[CandidateRecord]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            legacy_columns = tuple(
                column
                for column in CSV_COLUMNS
                if column not in {"submitted_by", "reviewed_by", "provenance_id"}
            )
            if fieldnames not in {CSV_COLUMNS, legacy_columns}:
                raise DataFormatError(
                    f"{path}: CSV columns must be exactly: {', '.join(CSV_COLUMNS)}"
                )
            records = []
            for row_number, row in enumerate(reader, start=2):
                try:
                    row.setdefault("submitted_by", None)
                    row.setdefault("reviewed_by", None)
                    row.setdefault("provenance_id", None)
                    candidate = candidate_from_csv(row)
                except ValidationError as error:
                    raise DataFormatError(
                        f"{path}:{row_number}: malformed candidate: {error}"
                    ) from error
                records.append(CandidateRecord(candidate=candidate, file=str(path), row=row_number))
            return records
    except UnicodeDecodeError as error:
        raise DataFormatError(f"{path}: input is not valid UTF-8") from error
    except OSError as error:
        raise DataFormatError(f"cannot read {path}: {error}") from error


def load_language_candidates(
    language: str, data_root: Path = DEFAULT_DATA_ROOT
) -> list[CandidateRecord]:
    return load_candidates(data_root / "languages" / language / "candidates.csv")


def load_blocklists(directory: Path) -> set[str]:
    words: set[str] = set()
    for path in sorted(directory.glob("*.txt")):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise DataFormatError(f"cannot read blocklist {path}: {error}") from error
        if content and not content.endswith("\n"):
            raise DataFormatError(f"blocklist {path} must end with a newline")
        for line_number, line in enumerate(content.splitlines(), start=1):
            word = line.strip()
            if not word or word.startswith("#"):
                continue
            if word in words:
                raise DataFormatError(f"{path}:{line_number}: duplicate blocklist word {word!r}")
            words.add(word)
    return words
