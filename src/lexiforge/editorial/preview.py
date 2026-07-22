import json
from typing import Any

from .changeset import ChangeSet


def changeset_as_dict(changeset: ChangeSet) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": changeset.id,
        "repository_root": str(changeset.repository_root),
        "operation": changeset.operation,
        "affected_files": list(changeset.affected_files),
        "file_changes": [
            {
                "path": item.relative_path,
                "existed": item.existed,
                "before_sha256": item.before_sha256,
                "after_sha256": item.after_sha256,
            }
            for item in changeset.files
        ],
        "records_added": list(changeset.records_added),
        "records_modified": list(changeset.records_modified),
        "records_superseded": list(changeset.records_superseded),
        "warnings": list(changeset.warnings),
        "validation_status": changeset.validation_status,
        "release_eligibility_impact": [
            {
                "language": item.language,
                "before": item.before,
                "after": item.after,
                "delta": item.delta,
            }
            for item in changeset.release_eligibility_impact
        ],
    }


def render_json(changeset: ChangeSet) -> str:
    return (
        json.dumps(changeset_as_dict(changeset), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def render_text(changeset: ChangeSet) -> str:
    lines = [
        f"ChangeSet: {changeset.id}",
        f"Operation: {changeset.operation}",
        f"Validation: {changeset.validation_status}",
        "Affected files:",
    ]
    lines.extend(f"- {path}" for path in changeset.affected_files)
    lines.append("Release eligibility impact:")
    lines.extend(
        f"- {item.language}: {item.before} -> {item.after} ({item.delta:+d})"
        for item in changeset.release_eligibility_impact
    )
    if changeset.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in changeset.warnings)
    return "\n".join(lines) + "\n"
