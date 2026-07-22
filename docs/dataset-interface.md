# Dataset interface

The dataset interface is the only filesystem contract between LexiForge tooling and data producers. It is independent of Git and repository topology.

## Root contract

A data-root directory contains:

```text
manifest.yaml
shared/
  categories.yaml
  policy.yaml
  scoring.yaml
  blocklist-types.yaml
languages/
  <declared-language>/
    language.yaml
    candidates.csv
    provenance.csv
    reviews.csv
    blocklists/
      metadata.yaml
      <declared blocklist files>
```

The manifest declares the dataset schema, dataset version, supported languages, licensing identity, maintainer, optional generated date, and compatible LexiForge version range. Every declared language must have exactly one matching directory and a profile whose code matches that directory. Additional language codes require no tooling-repository layout change.

## Independence guarantees

LexiForge does not require:

- a particular repository name such as `LexiForge-Data`;
- a Git checkout, remote, branch, tag, or sibling directory;
- datasets to share a repository with tooling;
- one repository to contain every future language;
- a web application, SDK, integration, or hosting provider.

CI mounts, extracted archives, generated local directories, independently versioned language collections, and future integrations are valid sources when they materialize this interface before invocation. Network retrieval remains outside core tooling.

## Evolution

Breaking file-contract changes increment `schema_version`. Compatible additive data releases increment `dataset_version`. Tool compatibility uses an inclusive minimum and exclusive maximum version. LexiForge rejects unsupported schemas and selected roots that do not fully implement their declared interface; it never silently substitutes bundled data.

Future SDKs should model the manifest and files rather than CLI internals. Future `LexiForge-Web` output must pass `validate-repository` and the same structural, provenance, review, and release-eligibility boundaries as hand-maintained data.
