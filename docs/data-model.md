# Candidate data model

CSV columns are exact and ordered; unknown columns are rejected.

| Field | Meaning |
| --- | --- |
| `id` | Stable UUID, unique across candidates |
| `language` | BCP 47-compatible profile code |
| `word` | Original submitted spelling |
| `status` | `submitted`, `needs_review`, `approved`, `rejected`, or `automatic_reject` |
| `category` | Optional stable shared category ID |
| `source_type` | `manual`, `community`, `import`, or `fixture` |
| `submitted_at` | Optional ISO 8601 timestamp |
| `reviewed_at` | Optional ISO 8601 timestamp |
| `score` | Optional integer from 0 through 100; no semantic scoring is implemented |
| `license_eligible` | Whether provenance permits inclusion under the LexiForge data license |
| `notes` | Optional plain-text context |

The same spelling may exist in different languages. Word uniqueness is scoped to language plus normalized spelling. CSV exports use fixed columns and quote fields as necessary; consumers opening metadata in spreadsheets should still treat leading formula characters as untrusted input.
