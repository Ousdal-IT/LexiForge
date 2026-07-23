from contextlib import suppress
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Input, Select, Static

from ..editorial import ChangeSet, EditorialError, EditorialService
from ..editorial.operations import EditorialOperation
from ..editorial.preview import render_text
from ..index import RepositoryIndexBuilder, RepositoryIndexError
from ..models import CandidateStatus
from ..repository import DatasetRepository
from .model import CandidateFilter, CandidateView
from .power_screens import (
    BatchReviewScreen,
    BlocklistEditorScreen,
    CommandPaletteScreen,
    ComparisonScreen,
    DuplicateAssistantScreen,
    SimilarityScreen,
    StatisticsScreen,
)
from .query import (
    CandidatePage,
    CandidateQuery,
    CandidateSummary,
    CanonicalWorkbenchView,
    WorkbenchRepositoryView,
    open_workbench_view,
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
from .tools import SavedSearchStore, SessionState, SessionStore


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
        Binding("alt+left", "previous_page", "Previous page", show=True),
        Binding("alt+right", "next_page", "Next page", show=True),
        Binding("ctrl+home", "first_page", "First page", show=False),
        Binding("ctrl+end", "last_page", "Last page", show=False),
        Binding("ctrl+i", "build_index", "Build index", show=True),
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

    PAGE_SIZE = 50

    def __init__(self, repository: DatasetRepository, index_root: Path | None = None):
        super().__init__()
        self.repository = repository
        self.index_root = index_root
        self.service = EditorialService(repository)
        self.view: WorkbenchRepositoryView = open_workbench_view(repository, index_root)
        self.session_store = SessionStore()
        self.saved_search_store = SavedSearchStore()
        persisted = self.session_store.load()
        self._persisted = (
            persisted if persisted.repository == str(repository.root) else SessionState()
        )
        self.pending_changeset: ChangeSet | None = None
        self.selected_id: str | None = self._persisted.selected_candidate
        self.selected_ids: set[str] = set()
        self._visible: tuple[CandidateSummary, ...] = ()
        self._page = CandidatePage((), 0, self._persisted.page_offset, self.PAGE_SIZE)
        self._selected_details: CandidateView | None = None
        self._sort_field = self._persisted.sort_field
        self._sort_reverse = self._persisted.sort_reverse
        self._page_offset = self._persisted.page_offset
        self._rendering_table = False
        self._repository_generation = 0
        self._index_build_state: str | None = None
        self._index_build_progress: tuple[str, int, int] | None = None

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
                [("All languages", "all"), *[(item, item) for item in self.view.languages]],
                value=self._persisted.language or "all",
                id="language-filter",
            )
            yield Select(
                [("All categories", "all"), *[(item, item) for item in self.view.categories]],
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

    def refresh_candidates(self, *, reset_page: bool = False) -> None:
        if reset_page:
            self._page_offset = 0
        query = CandidateQuery(
            filters=self.current_filter(),
            sort=self._sort_field,  # type: ignore[arg-type]
            reverse=self._sort_reverse,
            offset=self._page_offset,
            limit=self.PAGE_SIZE,
        )
        page = self.view.list_candidates(query)
        if page.total_count and page.offset >= page.total_count:
            self._page_offset = ((page.total_count - 1) // page.limit) * page.limit
            page = self.view.list_candidates(
                CandidateQuery(
                    filters=query.filters,
                    sort=query.sort,
                    reverse=query.reverse,
                    offset=self._page_offset,
                    limit=query.limit,
                )
            )
        self._page = page
        self._visible = page.items
        table = self.query_one("#candidate-table", DataTable)
        self._rendering_table = True
        try:
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
        finally:
            self._rendering_table = False
        if self._visible:
            selected = next(
                (item for item in self._visible if item.candidate.id == self.selected_id),
                self._visible[0],
            )
            self.select_candidate(selected)
        else:
            self.selected_id = None
            self._selected_details = None
            self.query_one("#candidate-details", Static).update("No matching candidates")
        self.update_status()
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        stats = self.view.get_dashboard_statistics()
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

    def select_candidate(self, item: CandidateSummary | CandidateView) -> None:
        candidate_id = item.candidate.id
        details = self.view.get_candidate(candidate_id)
        if details is None:
            if self.selected_id == candidate_id:
                self.selected_id = None
                self._selected_details = None
            self.query_one("#candidate-details", Static).update("Candidate no longer exists")
            return
        self.selected_id = candidate_id
        self._selected_details = details
        candidate = details.candidate
        reasons = ", ".join(details.eligibility_reasons) or "none"
        provenance = (
            "\n".join(
                f"  {record.source_kind.value}: {record.license_basis}"
                for record in details.provenance
            )
            or "  none"
        )
        reviews = (
            "\n".join(
                f"  {record.reviewed_at.isoformat()} · {record.decision.value} · "
                f"{record.reviewer_id}"
                for record in details.reviews[-5:]
            )
            or "  none"
        )
        self.query_one("#candidate-details", Static).update(
            "\n".join(
                (
                    f"Word: {candidate.word}",
                    f"Normalized: {details.normalized_word}",
                    f"Language: {candidate.language}",
                    f"Category: {candidate.category or '—'}",
                    f"UUID: {candidate.id}",
                    f"Status: {candidate.status.value}",
                    f"Release eligible: {'yes' if details.release_eligible else 'no'}",
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
        if self.selected_id is None:
            return None
        if (
            self._selected_details is None
            or self._selected_details.candidate.id != self.selected_id
        ):
            self._selected_details = self.view.get_candidate(self.selected_id)
        return self._selected_details

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._rendering_table or not self.query("#candidate-details"):
            return
        candidate_id = str(event.row_key.value)
        item = next(
            (item for item in self._visible if item.candidate.id == candidate_id),
            None,
        )
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
        self.refresh_candidates(reset_page=True)

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self.query("#candidate-table"):
            return
        if event.input.id and (event.input.id == "search" or event.input.id.endswith("-filter")):
            self.refresh_candidates(reset_page=True)

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self.query("#candidate-table"):
            return
        if event.select.id and event.select.id.endswith("-filter"):
            self.refresh_candidates(reset_page=True)

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
        language = self.current_filter().language or self.view.languages[0]
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
        self._repository_generation += 1
        self._activate_canonical(
            index_state="stale",
            reason="canonical mutation requires a full index rebuild",
        )
        self.reload_repository(message=f"Applied {operation} · canonical fallback active")
        self.rebuild_index()

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
        selected = [self.view.get_candidate(item) for item in sorted(self.selected_ids)]
        if len(selected) == 2 and selected[0] and selected[1]:
            self.push_screen(ComparisonScreen(selected[0], selected[1]))
        else:
            self.query_one("#preview", Static).update("Select exactly two candidates to compare.")

    def action_similarity(self) -> None:
        if self.selected_id is None:
            self.query_one("#preview", Static).update("Select a candidate for similarity review.")
            return
        self.push_screen(SimilarityScreen(self.view.find_similarity_candidates(self.selected_id)))

    def action_statistics(self) -> None:
        self.push_screen(StatisticsScreen(self.view.get_dashboard_statistics()))

    def action_duplicates(self) -> None:
        selected = self.selected_candidate()
        if selected is None:
            self.query_one("#preview", Static).update("Select a candidate for duplicate lookup.")
            return
        self.push_screen(
            DuplicateAssistantScreen(
                self.view.find_duplicates(
                    selected.candidate.language,
                    selected.normalized_word,
                )
            )
        )

    def action_blocklist(self) -> None:
        self.push_screen(
            BlocklistEditorScreen(self.current_filter().language or self.view.languages[0]),
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
        self.refresh_candidates(reset_page=True)

    def action_reload(self) -> None:
        self.reload_repository(message="Repository reloaded")

    def reload_repository(self, message: str = "") -> None:
        try:
            self.service = EditorialService(self.repository)
            replacement = open_workbench_view(self.repository, self.index_root)
            self.view.close()
            self.view = replacement
        except EditorialError as error:
            self.query_one("#preview", Static).update(f"Editorial error: {error}")
            self.update_status("reload failed")
            return
        self.pending_changeset = None
        self._selected_details = None
        self.selected_ids = {
            item for item in self.selected_ids if self.view.get_candidate(item) is not None
        }
        self.refresh_candidates()
        if message:
            self.query_one("#preview", Static).update(message)
        self.update_status(message)
        self.refresh_dashboard()

    def _activate_canonical(self, *, index_state: str, reason: str | None = None) -> None:
        previous = self.view
        self.view = CanonicalWorkbenchView(
            self.repository,
            index_state=index_state,
            reason=reason,
        )
        previous.close()
        self._selected_details = None

    @work(thread=True, exclusive=True, group="index-build", exit_on_error=False)
    def rebuild_index(self) -> None:
        generation = self._repository_generation
        self._index_build_state = "building"
        try:
            RepositoryIndexBuilder(self.repository, self.index_root).build(
                progress=self._report_index_progress
            )
        except (RepositoryIndexError, OSError, RuntimeError) as error:
            with suppress(RuntimeError):
                self.call_from_thread(self._finish_index_build, generation, str(error))
            return
        with suppress(RuntimeError):
            self.call_from_thread(self._finish_index_build, generation, None)

    def _finish_index_build(self, generation: int, error: str | None) -> None:
        if generation != self._repository_generation or not self.query("#status-bar"):
            return
        if error is not None:
            self._index_build_state = "failed"
            self._index_build_progress = None
            self.update_status("index rebuild failed · canonical fallback active")
            return
        replacement = open_workbench_view(self.repository, self.index_root)
        if replacement.status.kind != "indexed":
            replacement.close()
            self._index_build_state = "failed"
            self._index_build_progress = None
            self.update_status("index verification failed · canonical fallback active")
            return
        self.view.close()
        self.view = replacement
        self._index_build_state = None
        self._index_build_progress = None
        self._selected_details = None
        self.refresh_candidates()
        self.update_status("rebuilt index active")

    def action_build_index(self) -> None:
        if self._index_build_state == "building":
            self.update_status("index build already running")
            return
        self.rebuild_index()
        self.update_status("index building · editorial access remains available")

    def _report_index_progress(self, language: str, completed: int, total: int) -> None:
        with suppress(RuntimeError):
            self.call_from_thread(
                self._set_index_progress,
                language,
                completed,
                total,
            )

    def _set_index_progress(self, language: str, completed: int, total: int) -> None:
        self._index_build_progress = (language, completed, total)
        self.update_status(f"index building {language} {completed}/{total}")

    def action_next_page(self) -> None:
        if self._page.has_next:
            self._page_offset += self.PAGE_SIZE
            self.refresh_candidates()

    def action_previous_page(self) -> None:
        if self._page.has_previous:
            self._page_offset = max(0, self._page_offset - self.PAGE_SIZE)
            self.refresh_candidates()

    def action_first_page(self) -> None:
        if self._page_offset:
            self._page_offset = 0
            self.refresh_candidates()

    def action_last_page(self) -> None:
        if self._page.total_count:
            self._page_offset = ((self._page.total_count - 1) // self.PAGE_SIZE) * self.PAGE_SIZE
            self.refresh_candidates()

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
        backend = (
            "Index building" if self._index_build_state == "building" else self.view.status.label
        )
        self.query_one("#status-bar", Static).update(
            f"{self.repository.root} · language={language} · "
            f"selection={selection} · {dirty} · {self._page.total_count} matches · "
            f"page={self._page.page_number}/{self._page.page_count} · backend={backend}{suffix}"
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
                page_offset=self._page_offset,
            )
        )
        self.view.close()
