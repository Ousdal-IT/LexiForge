# Architecture

LexiForge follows a linear, deterministic boundary:

1. Strict YAML language profiles and shared policy/categories configure behavior.
2. Strict candidate CSV records preserve submitted words and metadata.
3. Normalization derives a canonical Unicode value without punctuation removal or transliteration.
4. Structural validation emits stable, contextual diagnostics.
5. Analysis reports the complete candidate set and its validation outcome.
6. Approved-word selection feeds deterministic TXT, JSON, and CSV exports.
7. A stable manifest embeds the profile, count, license, filenames, formats, and SHA-256 hashes.

M2 adds a read-only dataset-engineering layer above curation. It computes profile-driven statistics, optimisation suggestions, release plans, structural comparisons, and deterministic balanced selection. A presentation layer renders the same data as JSON, Markdown, static HTML, and pure-XML SVG. Publication writes a backend-free directory suitable for GitHub Pages.

Language behavior is configuration-driven; adding a compatible profile does not change validator logic. M0 deliberately has no persistence service, web framework, accounts, external API, plugin architecture, or semantic classifier.
