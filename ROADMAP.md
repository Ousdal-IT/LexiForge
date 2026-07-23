# LexiForge roadmap

LexiForge has completed the local editorial and repository-index foundation. The next releases
integrate those stable contracts into richer presentation layers without adding alternative
mutation paths or weakening canonical dataset validation.

| Status | Version | Focus |
| --- | --- | --- |
| ✅ | v0.4.0 | Editorial Service |
| ✅ | v0.4.1 | Editorial CLI |
| ✅ | v0.5.0 | Textual Workbench |
| ✅ | v0.5.1 | Editorial Power Tools |
| ✅ | v0.6.0 | Repository Index & Hardening |
| ✅ | v0.7.0 | Workbench Performance |
| Planned | v0.8.0 | PySide6 Desktop Workbench |
| Planned | v0.9.0 | Web API / Cloudflare Workers |
| Planned | v1.0.0 | Stable Editorial Platform |

The check mark means implementation is complete; release tags and package publication remain
separate release-process steps.

## v0.7.0 — Workbench Performance

Use the disposable repository index for safe Textual read paths while preserving exact canonical
fallback parity. Keep the immutable workbench snapshot model, approval-critical completeness and
all mutations through `EditorialService`. This release does not require incremental indexing.

## v0.8.0 — PySide6 Desktop Workbench

Add a desktop presentation layer over the existing operation, preview and editorial-service
contracts. It must not write CSV directly or duplicate validation, normalization, moderation or
eligibility rules.

## v0.9.0 — Web API / Cloudflare Workers

Build web submission and moderation infrastructure in a separate repository after the local
contracts are stable. The web layer must consume the versioned dataset interface and editorial
contracts, with explicit authentication, durable audit storage and deployment safeguards.

## v1.0.0 — Stable Editorial Platform

Stabilize the dataset and editorial contracts across CLI, Textual, desktop and web consumers.
Release readiness requires documented compatibility, deterministic canonical outputs and complete
validation independent of disposable indexes or presentation layers.

The roadmap does not imply that development datasets are production security wordlists.
