from collections.abc import Callable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from ..editorial.operations import BatchReviewOperation, BlocklistEditOperation, EditorialOperation
from ..models import CriterionValue, ReviewCriteria, ReviewDecision, SimilarityFinding
from .model import CandidateView
from .query import CandidateSummary
from .tools import RepositoryStatistics


class CommandPaletteScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]
    DEFAULT_CSS = """
    CommandPaletteScreen { align: center middle; }
    CommandPaletteScreen > Vertical {
        width: 64; border: round $accent; padding: 1 2; background: $surface;
    }
    """

    def __init__(self, commands: tuple[tuple[str, Callable[[], None]], ...]):
        super().__init__()
        self.commands = commands

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Command palette")
            yield Input(placeholder="Search commands", id="command-search")
            yield Static("\n".join(f"{name}" for name, _ in self.commands), id="commands")
            for index, (name, _) in enumerate(self.commands):
                yield Button(name, id=f"command-{index}")
            yield Button("Close", id="close")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-search":
            return
        query = event.value.casefold()
        self.query_one("#commands", Static).update(
            "\n".join(name for name, _ in self.commands if query in name.casefold())
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("command-"):
            index = int(event.button.id.removeprefix("command-"))
            self.dismiss(None)
            self.commands[index][1]()
            return
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class StatisticsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, statistics: RepositoryStatistics):
        super().__init__()
        self.statistics = statistics

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Repository statistics")
            yield Static(str(self.statistics.as_dict()), id="statistics")
            yield Button("Close", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class SimilarityScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, findings: tuple[SimilarityFinding, ...]):
        super().__init__()
        self.findings = findings

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Similarity browser")
            yield Input(placeholder="Minimum distance", value="1", id="threshold")
            yield Static(self.render_findings(1), id="similarity")
            yield Button("Close", id="close")

    def render_findings(self, threshold: int) -> str:
        return (
            "\n".join(
                f"{item.language}: {item.word_a} / {item.word_b} · d={item.distance} · "
                f"{item.rule_id}"
                for item in self.findings
                if item.distance <= threshold
            )
            or "No similarity findings"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "threshold":
            return
        try:
            threshold = int(event.value)
        except ValueError:
            return
        self.query_one("#similarity", Static).update(self.render_findings(threshold))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class DuplicateAssistantScreen(ModalScreen[None]):
    """Advisory duplicate triage; final actions remain explicit service operations."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, candidates: tuple[CandidateSummary, ...]):
        super().__init__()
        self.candidates = candidates

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Duplicate resolution assistant")
            yield Static(
                "Possible duplicates are advisory. Compare candidates, then use the normal "
                "service-backed withdraw, supersede, flag, or keep-both workflow.",
                id="duplicate-guidance",
            )
            yield Static(
                "\n".join(
                    f"{item.candidate.language}: {item.candidate.word} · "
                    f"{item.candidate.id} · {item.candidate.status.value}"
                    for item in self.candidates
                )
                or "No normalized duplicates",
                id="duplicates",
            )
            yield Button("Close", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class ComparisonScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, left: CandidateView, right: CandidateView):
        super().__init__()
        self.left = left
        self.right = right

    def compose(self) -> ComposeResult:
        fields = ("word", "normalized", "category", "status", "eligible")
        lines = ["field                 A                         B"]
        for field in fields:
            left = {
                "word": self.left.candidate.word,
                "normalized": self.left.normalized_word,
                "category": self.left.candidate.category,
                "status": self.left.candidate.status.value,
                "eligible": self.left.release_eligible,
            }[field]
            right = {
                "word": self.right.candidate.word,
                "normalized": self.right.normalized_word,
                "category": self.right.candidate.category,
                "status": self.right.candidate.status.value,
                "eligible": self.right.release_eligible,
            }[field]
            marker = "*" if left != right else " "
            lines.append(f"{marker}{field:20} {str(left):25} {str(right):25}")
        lines.extend(
            (
                "",
                f"A provenance: {len(self.left.provenance)} · reviews: {len(self.left.reviews)}",
                f"B provenance: {len(self.right.provenance)} · reviews: {len(self.right.reviews)}",
            )
        )
        with Vertical():
            yield Label("Candidate comparison")
            yield Static("\n".join(lines), id="comparison")
            yield Button("Close", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class BatchReviewScreen(ModalScreen[EditorialOperation | None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, candidate_ids: tuple[str, ...]):
        super().__init__()
        self.candidate_ids = candidate_ids

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Batch review · {len(self.candidate_ids)} candidates")
            yield Select(
                [
                    (item.value, item.value)
                    for item in ReviewDecision
                    if item
                    in {
                        ReviewDecision.APPROVE,
                        ReviewDecision.REJECT,
                        ReviewDecision.NEEDS_REVIEW,
                    }
                ],
                value=ReviewDecision.NEEDS_REVIEW.value,
                id="decision",
            )
            yield Input(placeholder="Reviewer ID", id="reviewer")
            yield Input(placeholder="Reviewed at (ISO 8601 with offset)", id="reviewed-at")
            yield Static("Review criteria (approval requires Yes for every required criterion)")
            for name in ReviewCriteria.model_fields:
                yield Select(
                    [(item.value.replace("_", " ").title(), item.value) for item in CriterionValue],
                    value=CriterionValue.UNKNOWN.value,
                    id=f"criterion-{name.replace('_', '-')}",
                    prompt=name.replace("_", " "),
                )
            yield Input(placeholder="Flags (comma-separated, optional)", id="flags")
            yield Input(placeholder="Reason or comment", id="comment")
            yield Button("Cancel", id="cancel")
            yield Button("Preview", id="preview", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        try:
            from datetime import datetime

            timestamp = datetime.fromisoformat(self.query_one("#reviewed-at", Input).value)
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("timestamp must include an explicit UTC offset")
            criteria = ReviewCriteria.model_validate(
                {
                    name: str(self.query_one(f"#criterion-{name.replace('_', '-')}", Select).value)
                    for name in ReviewCriteria.model_fields
                }
            )
            flags = tuple(
                value.strip()
                for value in self.query_one("#flags", Input).value.split(",")
                if value.strip()
            )
            self.dismiss(
                BatchReviewOperation(
                    candidate_ids=self.candidate_ids,
                    decision=ReviewDecision(str(self.query_one("#decision", Select).value)),
                    reviewer_id=self.query_one("#reviewer", Input).value,
                    reviewed_at=timestamp,
                    criteria=criteria,
                    comment=self.query_one("#comment", Input).value,
                    reason=self.query_one("#comment", Input).value or None,
                    flags=flags,
                )
            )
        except (ValueError, TypeError):
            return

    def action_cancel(self) -> None:
        self.dismiss(None)


class BlocklistEditorScreen(ModalScreen[EditorialOperation | None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, language: str):
        super().__init__()
        self.language = language

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Blocklist editor")
            yield Input(value=self.language, placeholder="Language", id="language")
            yield Input(placeholder="Blocklist ID", id="blocklist")
            yield Select(
                [(item, item) for item in ("add", "edit", "disable")],
                value="add",
                id="action",
            )
            yield Input(placeholder="Word", id="word")
            yield Input(placeholder="Replacement (edit only)", id="replacement")
            yield Input(placeholder="Reason", id="reason")
            yield Button("Cancel", id="cancel")
            yield Button("Preview", id="preview", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self.dismiss(
            BlocklistEditOperation(
                language=self.query_one("#language", Input).value,
                blocklist_id=self.query_one("#blocklist", Input).value,
                action=str(self.query_one("#action", Select).value),
                word=self.query_one("#word", Input).value,
                replacement=self.query_one("#replacement", Input).value or None,
                reason=self.query_one("#reason", Input).value,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
