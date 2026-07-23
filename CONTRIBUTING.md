# Contributing

Install with `uv sync --frozen --all-extras --dev` and run every check listed in `AGENTS.md`. Behavioral changes need typed implementation, tests, and documentation.

For future word contributions, submit individually selected words rather than copied bulk lists. Declare provenance, identify the correct language variety, and declare any bulk or third-party source without concealment. Eligible contributions may become part of the published dataset under its stated terms only when legally eligible for CC0. Do not submit personal data, copyrighted dictionary definitions, scraped lists, or content whose rights are unclear. All input is untrusted and passes the same validation boundary.

# Editorial changes

Use the service-backed CLI described in `docs/editorial-cli.md` for routine candidate, provenance,
and review maintenance. Preview first, apply explicitly, then inspect the repository diff. Supply
explicit pseudonymous actor IDs, offset-aware timestamps, provenance, and licensing assertions;
never infer or conceal source history. Direct CSV editing is an advanced fallback and must preserve
append-only review/provenance history and pass full repository validation.
