from collections.abc import Callable, Iterable
from datetime import datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from ..editorial.errors import EditorialError
from ..editorial.operations import (
    AddCandidateOperation,
    AddProvenanceOperation,
    EditCandidateOperation,
    EditorialOperation,
    RecordReviewOperation,
    SupersedeCandidateOperation,
    WithdrawCandidateOperation,
)
from ..models import (
    CriterionValue,
    ReviewCriteria,
    ReviewDecision,
    SourceKind,
    SourceType,
    WordCandidate,
)
from .model import CandidateView


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
    return parsed


class OperationScreen(ModalScreen[EditorialOperation | None]):
    """Base modal that only collects operation input; it never mutates data."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]
    dialog_title = "Editorial operation"

    DEFAULT_CSS = """
    OperationScreen { align: center middle; }
    OperationScreen > Vertical {
        width: 76; max-height: 95%; border: round $accent;
        padding: 1 2; background: $surface;
    }
    OperationScreen VerticalScroll { height: 1fr; }
    OperationScreen Input, OperationScreen Select { margin-bottom: 1; }
    OperationScreen .buttons { height: 3; align-horizontal: right; }
    OperationScreen #form-error { color: $error; min-height: 1; }
    """

    def compose_fields(self) -> Iterable[object]:
        return ()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.dialog_title, classes="dialog-title")
            with VerticalScroll():
                yield from self.compose_fields()  # type: ignore[misc]
                yield Static("", id="form-error")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Preview", id="preview", variant="primary")

    def value(self, identifier: str) -> str:
        return self.query_one(f"#{identifier}", Input).value

    def checked(self, identifier: str) -> bool:
        return self.query_one(f"#{identifier}", Checkbox).value

    def build_operation(self) -> EditorialOperation:
        raise NotImplementedError

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        try:
            self.dismiss(self.build_operation())
        except (EditorialError, ValueError, TypeError) as error:
            self.query_one("#form-error", Static).update(str(error))

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddCandidateScreen(OperationScreen):
    dialog_title = "Add candidate"

    def __init__(self, language: str = "nb"):
        super().__init__()
        self.language = language

    def compose_fields(self) -> Iterable[object]:
        yield Input(value=self.language, placeholder="Language", id="language")
        yield Input(placeholder="Word", id="word")
        yield Input(placeholder="Category", id="category")
        yield Input(placeholder="Submitter ID", id="submitter")
        yield Select(
            [(item.value, item.value) for item in SourceType],
            value=SourceType.MANUAL.value,
            id="source-type",
        )
        yield Select(
            [(item.value, item.value) for item in SourceKind],
            value=SourceKind.MANUAL.value,
            id="source-kind",
        )
        yield Input(placeholder="Source reference", id="source-reference")
        yield Input(placeholder="License basis", id="license-basis")
        yield Checkbox("License eligible", id="license-eligible")
        yield Input(placeholder="Created at (ISO 8601 with offset)", id="created-at")
        yield Input(placeholder="Comment", id="comment")

    def build_operation(self) -> EditorialOperation:
        return AddCandidateOperation(
            language=self.value("language"),
            word=self.value("word"),
            category=self.value("category"),
            submitter_id=self.value("submitter"),
            source_type=SourceType(str(self.query_one("#source-type", Select).value)),
            source_kind=SourceKind(str(self.query_one("#source-kind", Select).value)),
            source_reference=self.value("source-reference") or None,
            license_basis=self.value("license-basis"),
            license_eligible=self.checked("license-eligible"),
            created_at=_timestamp(self.value("created-at")),
            comment=self.value("comment"),
        )


class EditCandidateScreen(OperationScreen):
    dialog_title = "Edit candidate"

    def __init__(self, item: CandidateView):
        super().__init__()
        self.item = item

    def compose_fields(self) -> Iterable[object]:
        candidate = self.item.candidate
        yield Static(f"{candidate.id}\n{candidate.language} · {candidate.status.value}")
        yield Input(value=candidate.word, placeholder="Word", id="word")
        yield Input(value=candidate.category or "", placeholder="Category", id="category")
        yield Input(value=candidate.notes, placeholder="Editorial note", id="note")

    def build_operation(self) -> EditorialOperation:
        return EditCandidateOperation(
            self.item.candidate.id,
            word=self.value("word"),
            category=self.value("category") or None,
            notes=self.value("note"),
        )


class ReviewScreen(OperationScreen):
    dialog_title = "Record review"

    def __init__(self, item: CandidateView):
        super().__init__()
        self.item = item

    def compose_fields(self) -> Iterable[object]:
        yield Static(f"{self.item.candidate.word} · {self.item.candidate.status.value}")
        yield Select(
            [
                ("Approve", ReviewDecision.APPROVE.value),
                ("Reject", ReviewDecision.REJECT.value),
                ("Needs review", ReviewDecision.NEEDS_REVIEW.value),
            ],
            value=ReviewDecision.NEEDS_REVIEW.value,
            id="decision",
        )
        yield Input(placeholder="Reviewer ID", id="reviewer")
        yield Input(placeholder="Reviewed at (ISO 8601 with offset)", id="reviewed-at")
        for name in ReviewCriteria.model_fields:
            yield Select(
                [(item.value.replace("_", " ").title(), item.value) for item in CriterionValue],
                value=CriterionValue.UNKNOWN.value,
                id=f"criterion-{name.replace('_', '-')}",
                prompt=name.replace("_", " "),
            )
        yield Input(placeholder="Reason (required for rejection)", id="reason")
        yield Input(placeholder="Flag (optional)", id="flag")
        yield Input(placeholder="Comment", id="comment")

    def build_operation(self) -> EditorialOperation:
        criteria = ReviewCriteria.model_validate(
            {
                name: str(self.query_one(f"#criterion-{name.replace('_', '-')}", Select).value)
                for name in ReviewCriteria.model_fields
            }
        )
        flag = self.value("flag")
        return RecordReviewOperation(
            candidate_id=self.item.candidate.id,
            decision=ReviewDecision(str(self.query_one("#decision", Select).value)),
            reviewer_id=self.value("reviewer"),
            reviewed_at=_timestamp(self.value("reviewed-at")),
            criteria=criteria,
            comment=self.value("comment"),
            reason=self.value("reason") or None,
            flags=(flag,) if flag else (),
        )


class WithdrawScreen(OperationScreen):
    dialog_title = "Withdraw candidate"

    def __init__(self, item: CandidateView):
        super().__init__()
        self.item = item

    def compose_fields(self) -> Iterable[object]:
        yield Static(f"{self.item.candidate.word} · {self.item.candidate.id}")
        yield Input(placeholder="Actor ID", id="actor")
        yield Input(placeholder="Timestamp (ISO 8601 with offset)", id="timestamp")
        yield Input(placeholder="Reason", id="reason")

    def build_operation(self) -> EditorialOperation:
        return WithdrawCandidateOperation(
            self.item.candidate.id,
            self.value("actor"),
            _timestamp(self.value("timestamp")),
            self.value("reason"),
        )


class SupersedeScreen(OperationScreen):
    dialog_title = "Supersede candidate"

    def __init__(
        self,
        item: CandidateView,
        lookup: Callable[[str, str | None], WordCandidate],
    ):
        super().__init__()
        self.item = item
        self.lookup = lookup

    def compose_fields(self) -> Iterable[object]:
        yield Static(f"{self.item.candidate.word} · {self.item.candidate.id}")
        yield Input(placeholder="Replacement UUID or exact word", id="replacement")
        yield Input(placeholder="Actor ID", id="actor")
        yield Input(placeholder="Timestamp (ISO 8601 with offset)", id="timestamp")
        yield Input(placeholder="Reason", id="reason")

    def build_operation(self) -> EditorialOperation:
        replacement = self.lookup(self.value("replacement"), self.item.candidate.language)
        return SupersedeCandidateOperation(
            self.item.candidate.id,
            replacement.id,
            self.value("actor"),
            _timestamp(self.value("timestamp")),
            self.value("reason"),
        )


class ProvenanceScreen(OperationScreen):
    dialog_title = "Provenance history / add assertion"

    def __init__(self, item: CandidateView):
        super().__init__()
        self.item = item

    def compose_fields(self) -> Iterable[object]:
        history = (
            "\n".join(
                f"{item.created_at.isoformat() if item.created_at else '-'} · "
                f"{item.source_kind.value} · {item.license_basis}"
                for item in self.item.provenance
            )
            or "No provenance records"
        )
        yield Static(history)
        yield Select(
            [(item.value, item.value) for item in SourceKind],
            value=SourceKind.MANUAL.value,
            id="source-kind",
        )
        yield Input(placeholder="Source reference", id="source-reference")
        yield Input(placeholder="Contributor ID", id="contributor")
        yield Input(placeholder="License basis", id="license-basis")
        yield Checkbox("License eligible", id="license-eligible")
        yield Input(placeholder="Recorded at (ISO 8601 with offset)", id="recorded-at")
        yield Input(placeholder="Comment", id="comment")

    def build_operation(self) -> EditorialOperation:
        return AddProvenanceOperation(
            candidate_id=self.item.candidate.id,
            source_kind=SourceKind(str(self.query_one("#source-kind", Select).value)),
            source_reference=self.value("source-reference") or None,
            contributor_id=self.value("contributor"),
            license_basis=self.value("license-basis"),
            license_eligible=self.checked("license-eligible"),
            recorded_at=_timestamp(self.value("recorded-at")),
            comment=self.value("comment"),
        )


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Vertical { width: 72; border: round $accent; padding: 1 2; background: $surface; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("LexiForge Editorial Workbench")
            yield Static(
                "Ctrl-F search · Ctrl-R reload · Ctrl-P preview · Ctrl-A/Ctrl-Enter apply\n"
                "a add · e edit · r review · p provenance · w withdraw · s supersede\n"
                "Esc cancel/discard · F1 help"
            )
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
