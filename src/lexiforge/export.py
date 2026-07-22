import csv
import io
import json
import unicodedata
from pathlib import Path

from .errors import ExportError
from .models import CandidateRecord, CandidateStatus, LanguageProfile
from .normalize import normalize_word


def approved_words(records: list[CandidateRecord], profile: LanguageProfile) -> list[str]:
    return sorted(
        normalize_word(record.candidate.word, profile)
        for record in records
        if record.candidate.status == CandidateStatus.APPROVED
    )


def export_bytes(words: list[str], profile: LanguageProfile, output_format: str) -> bytes:
    words = sorted(unicodedata.normalize(profile.normalization, word) for word in words)
    if output_format == "txt":
        text = "".join(f"{word}\n" for word in words)
    elif output_format == "json":
        text = (
            json.dumps(
                {"language": profile.code, "normalization": profile.normalization, "words": words},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    elif output_format == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["language", "word"])
        for word in words:
            writer.writerow([profile.code, word])
        text = buffer.getvalue()
    else:
        raise ExportError(f"unsupported export format: {output_format}")
    return text.encode("utf-8")


def export_wordlist(
    records: list[CandidateRecord], profile: LanguageProfile, output_format: str, output: Path
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(export_bytes(approved_words(records, profile), profile, output_format))
    return output
