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

M2.5 places a `DatasetRepository` boundary in front of all CLI data access. It resolves explicit option, environment, or bundled roots; validates the dataset manifest and layout; and then passes one root through profiles, curation, engineering, builds, and publication. Core loaders remain filesystem-format focused and do not know whether the repository is bundled or external.

Despite its class name, this boundary represents a versioned dataset interface, not a Git checkout. It does not inspect repository names, remotes, branches, parent directories, or hosting providers. A directory, mounted CI artefact, extracted release, language-specific repository, or future integration is equivalent when it implements the documented interface.

M3.0 adds an editorial service above the dataset and validator layers. Operations propose structured full-file changes; the service validates an isolated shadow repository and emits an immutable changeset. Rendering is separate. Apply verifies source hashes, revalidates, atomically replaces files, and rolls back partial replacement failures. Future CLI and editor layers must depend on this service rather than CSV serialization details.

M3.1 supplies immutable operation planners for candidate creation/editing/withdrawal/supersession, provenance addition, and append-only review transitions. CLI commands only collect typed input and render service results. Audit times and identities are explicit, candidate IDs survive edits, normalization and transitions remain centralized, and an applied operation always receives final repository validation.

M3.2 adds a Textual presentation layer. It loads one immutable, read-optimized candidate snapshot per explicit repository reload, while every proposed mutation remains an M3.1 operation passed to `EditorialService`. The preview pane calls the shared renderer verbatim; apply uses the pending validated `ChangeSet`. Textual widgets contain no serializers, normalization rules, moderation rules, or eligibility decisions.

Language behavior is configuration-driven; adding a compatible profile does not change validator logic. M0 deliberately has no persistence service, web framework, accounts, external API, plugin architecture, or semantic classifier.
