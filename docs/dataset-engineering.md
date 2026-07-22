# Dataset engineering

M2 analyses candidate spelling and curation metadata without changing source data or making semantic decisions.

## Statistics

Dataset reports include word-length histograms; first and last letters; character, bigram, and trigram frequencies; profile-configured vowel/consonant counts; categories; review completion; provenance; score distribution; similarity findings; and release eligibility. Sorting and rounding are fixed and locale-independent.

## Optimisation

`lexiforge optimise` emits suggestions for category and length imbalance, repeated two-letter prefixes/suffixes, double letters, skewed character frequency, single-occurrence bigrams, and similarity findings. Thresholds are deterministic heuristics. A suggestion is neither rejection nor evidence of linguistic unsuitability, and the command never writes source data.

## Release planning and comparison

`lexiforge release plan` compares release-eligible counts with a requested or profile target. Approximate category needs divide the target evenly across stable shared categories and subtract existing eligible counts. It identifies gaps but never proposes words.

`lexiforge compare nb nn` compares counts, categories, lengths, characters, review progress, and provenance coverage. It performs no translation or semantic comparison.

## Balanced selection

`build --balanced` greedily selects the candidate with the least represented category, then least represented word length, then least represented initial letter. Remaining ties prefer higher advisory score and finally normalized lexical order. Eligibility is evaluated before balancing. Selected exports are still written in normalized lexical order. Scores influence only the last selection tie and never moderation status.

## Reports and charts

`report generate` writes Markdown, stable JSON, or static HTML. `report publish` creates a root index plus one directory per language with HTML, JSON, and five SVG charts: word length, categories, characters, review status, and release readiness. SVG is pure XML with no scripts, embedded fonts, or external assets. Reports contain no volatile timestamp.

