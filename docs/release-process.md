# Release process

Run the complete quality suite, validate all languages, and build each language into a clean ignored directory. The build selects approved records, writes TXT/JSON/CSV in Unicode code-point order, generates a timestamp-free manifest, and verifies SHA-256 hashes and word count. Build twice and compare exact bytes. Never manually edit or commit generated release artefacts.

