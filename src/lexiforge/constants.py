from pathlib import Path

PROJECT_NAME = "LexiForge"
WORDLIST_VERSION = "0.0.0-dev"
DATA_LICENSE = "CC0-1.0"
MANIFEST_SCHEMA_VERSION = 1
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PACKAGE_ROOT / "data"
CSV_COLUMNS = (
    "id",
    "language",
    "word",
    "status",
    "category",
    "source_type",
    "submitted_at",
    "submitted_by",
    "reviewed_at",
    "reviewed_by",
    "score",
    "license_eligible",
    "provenance_id",
    "notes",
)
