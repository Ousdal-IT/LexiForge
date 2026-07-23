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
from .screens import (
    AddCandidateScreen,
    EditCandidateScreen,
    HelpScreen,
    ProvenanceScreen,
    ReviewScreen,
    SupersedeScreen,
    WithdrawScreen,
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
        Binding("a", "add", "Add", show=True),
        Binding("e", "edit", "Edit", show=True),
        Binding("r", "review", "Review", show=True),
        Binding("p", "provenance", "Provenance", show=True),
        Binding("w", "withdraw", "Withdraw", show=True),
        Binding("s", "supersede", "Supersede", show=True),
    ]

    CSS = """
    Screen { layout: vertical; }
    #title-bar { height: 3; padding: 1 2; background: $primary; color: $text; text-style: bold; }
    #filters { height: 3; padding: 0 1; }
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
        self.pending_changeset: ChangeSet | None = None
        self.selected_id: str | None = None
        self._visible: tuple[CandidateView, ...] = ()
        self._sort_field = "word"
        self._sort_reverse = False

    def compose(self) -> ComposeResult:
        yield Static(self._title_text(), id="title-bar")
        with Horizontal(id="filters"):
            yield Input(placeholder="Search word, normalized word, or UUID", id="search")
            yield Select(
                [("All languages", "all"), *[(item, item) for item in self.snapshot.languages]],
                value="all",
                id="language-filter",
            )
            yield Select(
                [("All categories", "all"), *[(item, item) for item in self.snapshot.categories]],
                value="all",
                id="category-filter",
            )
            yield Select(
                [("All states", "all"), *[(item.value, item.value) for item in CandidateStatus]],
                value="all",
                id="status-filter",
            )
            yield Select(
                [("Any eligibility", "all"), ("Eligible", "yes"), ("Ineligible", "no")],
                value="all",
                id="eligibility-filter",
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
        return CandidateFilter(
            search=self.query_one("#search", Input).value,
            language=None if language == "all" else language,
            category=None if category == "all" else category,
            status=None if status == "all" else CandidateStatus(status),
            release_eligible=None if eligibility == "all" else eligibility == "yes",
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
        if event.input.id == "search":
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

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_preview(self) -> None:
        self.query_one("#preview", Static).focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def update_status(self, message: str = "") -> None:
        language = self.current_filter().language or "all"
        selection = self.selected_id or "none"
        dirty = "preview" if self.pending_changeset else "clean"
        suffix = f" · {message}" if message else ""
        self.query_one("#status-bar", Static).update(
            f"{self.repository.root} · language={language} · "
            f"selection={selection} · {dirty} · {len(self._visible)} shown{suffix}"
        )
