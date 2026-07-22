# Release process

Run the complete quality suite, validate all languages, and generate curation reports. The build selects only structurally valid approved records with provenance, acceptable licensing, resolved mandatory criteria, no error blocklist match, and no mandatory flags. Development sizes 16, 32, and 64 require `--allow-development-size`; they are not production releases. Selection uses normalized lexical order. Build twice, verify manifests and hashes, and compare exact bytes. Never manually edit generated reports or release artefacts.
