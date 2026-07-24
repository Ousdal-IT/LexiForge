from pathlib import Path

PROJECT_NAME = "LexiForge"
WORDLIST_VERSION = "0.0.0-dev"
DATA_LICENSE = "CC0-1.0"
MANIFEST_SCHEMA_VERSION = 1
PACKAGE_ROOT = Path(__file__).resolve().parent
_DATA_LOCATIONS = (PACKAGE_ROOT.parent / "data", PACKAGE_ROOT.parents[1] / "data")
DEFAULT_DATA_ROOT = next(
    (location for location in _DATA_LOCATIONS if location.is_dir()),
    _DATA_LOCATIONS[0],
)
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
