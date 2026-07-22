# Curation workflow

A candidate enters with explicit provenance and remains unapproved. Structural validation runs before human review. Blocklists and similarity provide explicit findings; configured scoring summarizes explainable signals but never changes status. A human records criteria and a transition in append-only review history. Release eligibility then checks approval, criteria, provenance, licensing, blocklists, and flags before normalized lexical selection and deterministic export.

Candidate imports and review commands are dry-run by default. `--apply` stages complete files and atomically replaces each related CSV. M1 serializes candidate then audit data from already validated staged content; interruption between replacements is detectable by repository-hygiene link/status checks and must be repaired from version control.

