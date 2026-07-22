# Blocklists

Each language can declare multiple blocklists in `blocklists/metadata.yaml`. Metadata identifies the stable ID, file, language, type, severity, description, license, and version. Supported types include reserved, offensive, proper-name, brand, sensitive, ambiguous, technical, and custom; severities are error, warning, and review.

Entries are UTF-8, normalized, one per line, and may contain comments or blanks. Duplicates and missing metadata fail loading. Error matches affect release eligibility; other severities remain review signals. M1 production directories contain no harmful demonstration entries.
