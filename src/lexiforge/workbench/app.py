from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Input, Select, Static

from ..editorial import ChangeSet, EditorialError, EditorialService
from ..editorial.operations import EditorialOperation
from ..editorial.preview import render_text
from ..models import CandidateStatus
from ..repository import DatasetRepository
from .model import CandidateFilter, CandidateView, RepositorySnapshot
from .power_screens import (
    BatchReviewScreen,
    BlocklistEditorScreen,
    CommandPaletteScreen,
    ComparisonScreen,
    DuplicateAssistantScreen,
    SimilarityScreen,
    StatisticsScreen,
)
from .screens import (
    AddCandidateScreen,
    EditCandidateScreen,
    HelpScreen,
    ProvenanceScreen,
    ReviewScreen,
    SupersedeScreen,
    WithdrawScreen,
)
from .tools import (
    SavedSearchStore,
    SessionState,
    SessionStore,
    repository_statistics,
    similarity_browser,
)


class EditorialWorkbench(App[None]):
    """Full-screen, local-first editor backed exclusively by EditorialService."""

    TITLE = "LexiForge Editorial Workbench"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+f", "focus_search", "Search", show=True, priority=True),
        Binding("ctrl+r", "reload", "Reload", show=True, priority=True),
        Binding("ctrl+p", "focus_preview", "Preview", show=True, priority=True),
        Binding("ctrl+a", "apply", "Apply", show=True, priority=True),
        Binding("ctrl+enter", "apply", "Apply", show=False, priority=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("f1", "help", "Help", show=True, priority=True),
        Binding("ctrl+shift+p", "command_palette", "Commands", show=True, priority=True),
        Binding("a", "add", "Add", show=True),
        Binding("e", "edit", "Edit", show=True),
        Binding("r", "review", "Review", show=True),
        Binding("p", "provenance", "Provenance", show=True),
        Binding("w", "withdraw", "Withdraw", show=True),
        Binding("s", "supersede", "Supersede", show=True),
        Binding("d", "dashboard", "Dashboard", show=True),
        Binding("space", "toggle_selection", "Select", show=True),
        Binding("c", "compare", "Compare", show=True),
        Binding("i", "similarity", "Similarity", show=True),
        Binding("b", "blocklist", "Blocklist", show=True),
        Binding("m", "batch_review", "Batch review", show=True),
        Binding("v", "import_review", "Import review", show=True),
        Binding("x", "statistics", "Statistics", show=True),
        Binding("u", "duplicates", "Duplicates", show=True),
    ]

    CSS = """
    Screen { layout: vertical; }
    #title-bar { height: 3; padding: 1 2; background: $primary; color: $text; text-style: bold; }
    #filters { height: 3; padding: 0 1; }
    #dashboard { height: 5; padding: 1 2; border: round $accent; }
    #filters Input { width: 2fr; }
    #filters Select { width: 1fr; }
    #workspace { height: 1fr; min-height: 12; }
    #candidate-table { width: 42%; min-width: 32; border: round $accent; }
    #candidate-details { width: 58%; border: round $accent; padding: 1 2; overflow-y: auto; }
    #preview {
        height: 12; min-height: 6; border: round $secondary;
        padding: 1 2; overflow-y: auto;
    }
    #status-bar { height: 1; padding: 0 1; background: $boost; }
    """

    def __init__(self, repository: DatasetRepository):
        super().__init__()
        self.repository = repository
        self.service = EditorialService(repository)
        self.snapshot = RepositorySnapshot.load(repository)
        self.session_store = SessionStore()
        self.saved_search_store = SavedSearchStore()
        persisted = self.session_store.load()
        self._persisted = (
            persisted if persisted.repository == str(repository.root) else SessionState()
        )
        self.pending_changeset: ChangeSet | None = None
        self.selected_id: str | None = self._persisted.selected_candidate
        self.selected_ids: set[str] = set()
        self._visible: tuple[CandidateView, ...] = ()
        self._sort_field = self._persisted.sort_field
        self._sort_reverse = self._persisted.sort_reverse

    def compose(self) -> ComposeResult:
        yield Static(self._title_text(), id="title-bar")
        yield Static("Loading dashboard…", id="dashboard", markup=False)
        with Horizontal(id="filters"):
            yield Input(
                value=self._persisted.search,
                placeholder="Search word, normalized word, or UUID",
                id="search",
            )
            yield Select(
                [("All languages", "all"), *[(item, item) for item in self.snapshot.languages]],
                value=self._persisted.language or "all",
                id="language-filter",
            )
            yield Select(
                [("All categories", "all"), *[(item, item) for item in self.snapshot.categories]],
                value=self._persisted.category or "all",
                id="category-filter",
            )
            yield Select(
                [("All states", "all"), *[(item.value, item.value) for item in CandidateStatus]],
                value=self._persisted.status or "all",
                id="status-filter",
            )
            yield Select(
                [("Any eligibility", "all"), ("Eligible", "yes"), ("Ineligible", "no")],
                value=("yes" if self._persisted.release_eligible else "no")
                if self._persisted.release_eligible is not None
                else "all",
                id="eligibility-filter",
            )
            yield Select(
                [
                    ("All sources", "all"),
                    ("Manual", "manual"),
                    ("Import", "import"),
                    ("Community", "community"),
                ],
                value="all",
                id="source-filter",
            )
        with Horizontal(id="advanced-filters"):
            yield Input(placeholder="Contributor", id="contributor-filter")
            yield Input(placeholder="Reviewer", id="reviewer-filter")
            yield Select(
                [
                    ("All review states", "all"),
                    ("Pending", "pending"),
                    ("Complete", "complete"),
                    ("Flagged", "flagged"),
                ],
                value="all",
                id="review-filter",
            )
            yield Select(
                [("Any license", "all"), ("Eligible", "yes"), ("Ineligible", "no")],
                value="all",
                id="license-filter",
            )
            yield Select(
                [("Any blocklist", "all"), ("Matches", "match"), ("Clear", "clear")],
                value="all",
                id="blocklist-filter",
            )
        with Horizontal(id="workspace"):
            yield DataTable(id="candidate-table", cursor_type="row", zebra_stripes=True)
            yield Static("Select a candidate", id="candidate-details", markup=False)
        yield Static("No pending change set.", id="preview", markup=False)
        yield Static("", id="status-bar", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#candidate-table", DataTable)
        table.add_columns("Word", "Lang", "Category", "Status", "Eligible")
        self.refresh_candidates()
        table.focus()
        self.refresh_dashboard()

    def _title_text(self) -> str:
        return f"LexiForge Editorial Workbench  ·  {self.repository.root}"

    @staticmethod
    def _select_value(widget: Select[object]) -> str:
        return str(widget.value)

    def current_filter(self) -> CandidateFilter:
        language = self._select_value(self.query_one("#language-filter", Select))
        category = self._select_value(self.query_one("#category-filter", Select))
        status = self._select_value(self.query_one("#status-filter", Select))
        eligibility = self._select_value(self.query_one("#eligibility-filter", Select))
        source = self._select_value(self.query_one("#source-filter", Select))
        review_state = self._select_value(self.query_one("#review-filter", Select))
        license_state = self._select_value(self.query_one("#license-filter", Select))
        blocklist_state = self._select_value(self.query_one("#blocklist-filter", Select))
        return CandidateFilter(
            search=self.query_one("#search", Input).value,
            language=None if language == "all" else language,
            category=None if category == "all" else category,
            status=None if status == "all" else CandidateStatus(status),
            release_eligible=None if eligibility == "all" else eligibility == "yes",
            source_type=None if source == "all" else source,
            review_state=None if review_state == "all" else review_state,
            contributor=self.query_one("#contributor-filter", Input).value or None,
            reviewer=self.query_one("#reviewer-filter", Input).value or None,
            license_eligible=None if license_state == "all" else license_state == "yes",
            blocklist_state=None if blocklist_state == "all" else blocklist_state,
        )

    def refresh_candidates(self) -> None:
        items = list(self.snapshot.filtered(self.current_filter()))
        sorters = {
            "word": lambda item: (item.normalized_word, item.candidate.id),
            "language": lambda item: (item.candidate.language, item.normalized_word),
            "category": lambda item: (item.candidate.category or "", item.normalized_word),
            "status": lambda item: (item.candidate.status.value, item.normalized_word),
            "eligible": lambda item: (item.release_eligible, item.normalized_word),
        }
        items.sort(key=sorters[self._sort_field], reverse=self._sort_reverse)
        self._visible = tuple(items)
        table = self.query_one("#candidate-table", DataTable)
        table.clear()
        for item in self._visible:
            candidate = item.candidate
            table.add_row(
                candidate.word,
                candidate.language,
                candidate.category or "—",
                candidate.status.value,
                "yes" if item.release_eligible else "no",
                key=candidate.id,
            )
        if self._visible:
            selected = self.snapshot.candidate(self.selected_id) if self.selected_id else None
            if selected not in self._visible:
                selected = self._visible[0]
            self.select_candidate(selected)
        else:
            self.selected_id = None
            self.query_one("#candidate-details", Static).update("No matching candidates")
        self.update_status()
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        stats = repository_statistics(self.snapshot)
        self.query_one("#dashboard", Static).update(
            " · ".join(
                (
                    f"Candidates {stats.total_candidates}",
                    f"Pending reviews {stats.pending_reviews}",
                    f"Flagged {stats.flagged}",
                    f"Approved {stats.approved}",
                    f"Eligible {stats.release_eligible}",
                    f"Blocked {stats.release_blocked}",
                    f"Missing provenance {stats.provenance_missing}",
                    f"Blocklist matches {stats.blocklist_matches}",
                )
            )
        )

    def select_candidate(self, item: CandidateView) -> None:
        self.selected_id = item.candidate.id
        candidate = item.candidate
        reasons = ", ".join(item.eligibility_reasons) or "none"
        provenance = (
            "\n".join(
                f"  {record.source_kind.value}: {record.license_basis}"
                for record in item.provenance
            )
            or "  none"
        )
        reviews = (
            "\n".join(
                f"  {record.reviewed_at.isoformat()} · {record.decision.value} · "
                f"{record.reviewer_id}"
                for record in item.reviews[-5:]
            )
            or "  none"
        )
        self.query_one("#candidate-details", Static).update(
            "\n".join(
                (
                    f"Word: {candidate.word}",
                    f"Normalized: {item.normalized_word}",
                    f"Language: {candidate.language}",
                    f"Category: {candidate.category or '—'}",
                    f"UUID: {candidate.id}",
                    f"Status: {candidate.status.value}",
                    f"Release eligible: {'yes' if item.release_eligible else 'no'}",
                    f"Eligibility warnings: {reasons}",
                    "",
                    "Provenance:",
                    provenance,
                    "",
                    "Recent reviews:",
                    reviews,
                )
            )
        )
        self.update_status()

    def selected_candidate(self) -> CandidateView | None:
        return self.snapshot.candidate(self.selected_id) if self.selected_id else None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        candidate_id = str(event.row_key.value)
        item = self.snapshot.candidate(candidate_id)
        if item:
            self.select_candidate(item)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        fields = ("word", "language", "category", "status", "eligible")
        field = fields[event.column_index]
        if field == self._sort_field:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_field = field
            self._sort_reverse = False
        self.refresh_candidates()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and (event.input.id == "search" or event.input.id.endswith("-filter")):
            self.refresh_candidates()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id and event.select.id.endswith("-filter"):
            self.refresh_candidates()

    def prepare_operation(self, operation: EditorialOperation | None) -> None:
        if operation is None:
            return
        try:
            changeset = self.service.preview(operation)
        except EditorialError as error:
            self.pending_changeset = None
            self.query_one("#preview", Static).update(f"Editorial error: {error}")
            self.update_status("invalid preview")
            return
        self.pending_changeset = changeset
        self.query_one("#preview", Static).update(render_text(changeset))
        self.update_status("preview valid")

    def action_add(self) -> None:
        language = self.current_filter().language or self.snapshot.languages[0]
        self.push_screen(AddCandidateScreen(language), self.prepare_operation)

    def action_edit(self) -> None:
        if item := self.selected_candidate():
            self.push_screen(EditCandidateScreen(item), self.prepare_operation)

    def action_review(self) -> None:
        if item := self.selected_candidate():
            self.push_screen(ReviewScreen(item), self.prepare_operation)

    def action_provenance(self) -> None:
        if item := self.selected_candidate():
            self.push_screen(ProvenanceScreen(item), self.prepare_operation)

    def action_withdraw(self) -> None:
        if item := self.selected_candidate():
            self.push_screen(WithdrawScreen(item), self.prepare_operation)

    def action_supersede(self) -> None:
        if item := self.selected_candidate():
            self.push_screen(
                SupersedeScreen(item, self.service.lookup_candidate),
                self.prepare_operation,
            )

    def action_apply(self) -> None:
        if self.pending_changeset is None:
            self.query_one("#preview", Static).update("No validated change set to apply.")
            return
        try:
            self.service.apply(self.pending_changeset)
        except EditorialError as error:
            self.query_one("#preview", Static).update(f"Editorial error: {error}")
            self.update_status("apply failed")
            return
        operation = self.pending_changeset.operation
        self.pending_changeset = None
        self.reload_repository(message=f"Applied {operation}")

    def action_cancel(self) -> None:
        self.pending_changeset = None
        self.query_one("#preview", Static).update("No pending change set.")
        self.update_status("preview discarded")

    def action_toggle_selection(self) -> None:
        if self.selected_id is None:
            return
        if self.selected_id in self.selected_ids:
            self.selected_ids.remove(self.selected_id)
        else:
            self.selected_ids.add(self.selected_id)
        self.update_status()

    def action_compare(self) -> None:
        selected = [self.snapshot.candidate(item) for item in sorted(self.selected_ids)]
        if len(selected) == 2 and selected[0] and selected[1]:
            self.push_screen(ComparisonScreen(selected[0], selected[1]))
        else:
            self.query_one("#preview", Static).update("Select exactly two candidates to compare.")

    def action_similarity(self) -> None:
        self.push_screen(
            SimilarityScreen(similarity_browser(self.snapshot, self.current_filter().language))
        )

    def action_statistics(self) -> None:
        self.push_screen(StatisticsScreen(repository_statistics(self.snapshot)))

    def action_duplicates(self) -> None:
        self.push_screen(DuplicateAssistantScreen(similarity_browser(self.snapshot)))

    def action_blocklist(self) -> None:
        self.push_screen(
            BlocklistEditorScreen(self.current_filter().language or self.snapshot.languages[0]),
            self.prepare_operation,
        )

    def action_batch_review(self) -> None:
        if self.selected_ids:
            self.push_screen(
                BatchReviewScreen(tuple(sorted(self.selected_ids))),
                self.prepare_operation,
            )
        else:
            self.query_one("#preview", Static).update("Select candidates for batch review.")

    def action_import_review(self) -> None:
        source = self.query_one("#source-filter", Select)
        source.value = "import"
        self.query_one("#status-filter", Select).value = "submitted"
        self.refresh_candidates()

    def action_reload(self) -> None:
        self.reload_repository(message="Repository reloaded")

    def reload_repository(self, message: str = "") -> None:
        try:
            self.service = EditorialService(self.repository)
            self.snapshot = RepositorySnapshot.load(self.repository)
        except EditorialError as error:
            self.query_one("#preview", Static).update(f"Editorial error: {error}")
            self.update_status("reload failed")
            return
        self.pending_changeset = None
        self.refresh_candidates()
        if message:
            self.query_one("#preview", Static).update(message)
        self.update_status(message)
        self.refresh_dashboard()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_preview(self) -> None:
        self.query_one("#preview", Static).focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_dashboard(self) -> None:
        self.query_one("#dashboard", Static).focus()

    def action_command_palette(self) -> None:
        self.push_screen(
            CommandPaletteScreen(
                (
                    ("Add candidate", self.action_add),
                    ("Edit candidate", self.action_edit),
                    ("Record review", self.action_review),
                    ("Open dashboard", self.action_dashboard),
                    ("Find similar", self.action_similarity),
                    ("Reload repository", self.action_reload),
                    ("Export statistics", self.action_statistics),
                )
            )
        )

    def update_status(self, message: str = "") -> None:
        language = self.current_filter().language or "all"
        selection = self.selected_id or "none"
        dirty = "preview" if self.pending_changeset else "clean"
        suffix = f" · {message}" if message else ""
        self.query_one("#status-bar", Static).update(
            f"{self.repository.root} · language={language} · "
            f"selection={selection} · {dirty} · {len(self._visible)} shown{suffix}"
        )

    def on_unmount(self) -> None:
        if not self.query("#language-filter"):
            return
        filters = self.current_filter()
        self.session_store.save(
            SessionState(
                repository=str(self.repository.root),
                language=filters.language,
                search=filters.search,
                category=filters.category,
                status=filters.status.value if filters.status else None,
                release_eligible=filters.release_eligible,
                sort_field=self._sort_field,
                sort_reverse=self._sort_reverse,
                selected_candidate=self.selected_id,
            )
        )
