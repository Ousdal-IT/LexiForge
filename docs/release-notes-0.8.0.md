# LexiForge 0.8.0

LexiForge 0.8.0 adds an optional native PySide6 desktop workbench and makes regular wheel
installation self-contained for the development dataset contract.

## Dataset and installation contract

- Regular wheels include the complete bundled `data/` tree.
- Bundled data is a small project-created development/example dataset, not an official production
  security wordlist.
- Bundled data is read-only for editorial mutations. Use a writable external repository for
  candidate, provenance, and review changes.
- External datasets can be selected with `--data-root` or `LEXIFORGE_DATA_ROOT`; invalid selected
  roots fail clearly and never silently fall back.
- The optional desktop client is installed with `lexiforge[desktop]` and uses the same dataset
  resolution contract.

## Highlights

- Bounded desktop search, language/category filters, pagination, and lazy details.
- Canonical fallback and verified disposable-index reads.
- Stale asynchronous result protection across searches, repository switches, and shutdown.
- Deterministic session state outside dataset repositories.
- Clean CLI configuration errors with exit code 2.

The bundled examples remain unsuitable for production passphrase security use. Official dataset
release and licensing decisions belong to the separately reviewed external data repository.
