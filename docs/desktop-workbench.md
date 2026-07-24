# Native desktop workbench

v0.8.0 adds an optional PySide6 desktop browser for local LexiForge dataset repositories. It is a
presentation layer over the existing `WorkbenchRepositoryView`: canonical files remain
authoritative, indexed reads retain their normal stale-index protection, and the desktop code does
not open SQLite or write dataset CSV files.

Install the optional dependency and launch the application:

```bash
uv sync --extra desktop
uv run lexiforge desktop --data-root ../lexiforge-data/data
```

Pass `--canonical` to disable indexed reads. `--reset-session` starts without restored presentation
state. Search and filter changes reset pagination, candidate details load on demand, and stale
asynchronous page or detail results are ignored after a newer request or repository change.

The File menu opens another compatible dataset root and reloads the current view. Candidate pages
are bounded to 50 rows. The status bar identifies the selected dataset root and whether reads use a
valid disposable index or canonical fallback.

Desktop session data contains window geometry and up to ten recent repository paths. It is stored
at `~/.config/lexiforge/desktop.json`, outside the dataset, and is written by atomic replacement.
No network behavior, telemetry, or dataset mutation is introduced.

The base type-check job intentionally does not require PySide6. Desktop modules therefore have a
small mypy exception for Qt's optional, untyped boundary. A release CI follow-up should add a
separate `desktop` type-check job that installs the optional extra and validates the Qt modules
with the available PySide6 typing metadata.
