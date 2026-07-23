import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import Static

from lexiforge.constants import DEFAULT_DATA_ROOT
from lexiforge.editorial import BatchReviewOperation, BlocklistEditOperation, EditorialService
from lexiforge.editorial.errors import MutationRejectedError
from lexiforge.models import CriterionValue, ReviewCriteria, ReviewDecision
from lexiforge.repository import DatasetRepository
from lexiforge.workbench import CandidateFilter, EditorialWorkbench, RepositorySnapshot
from lexiforge.workbench.tools import (
    SavedSearch,
    SavedSearchStore,
    SessionState,
    SessionStore,
    repository_statistics,
    similarity_browser,
)


def repository_copy(tmp_path: Path) -> DatasetRepository:
    root = tmp_path / "external-data"
    shutil.copytree(DEFAULT_DATA_ROOT, root)
    return DatasetRepository(root)


def test_statistics_and_similarity_are_deterministic() -> None:
    snapshot = RepositorySnapshot.load(DatasetRepository(DEFAULT_DATA_ROOT))
    first = repository_statistics(snapshot)
    second = repository_statistics(snapshot)
    assert first == second
    assert first.total_candidates == 72
    assert first.approved > 0
    assert first.to_csv() == second.to_csv()
    findings = similarity_browser(snapshot, "nb")
    assert findings == tuple(
        sorted(findings, key=lambda item: (item.language, item.word_a, item.word_b, item.rule_id))
    )
    assert all(item.word_a < item.word_b for item in findings)


def test_saved_search_and_session_persist_outside_dataset(tmp_path: Path) -> None:
    search_store = SavedSearchStore(tmp_path / "editor.json")
    searches = {
        "Needs Review": SavedSearch("Needs Review", CandidateFilter(review_state="pending"))
    }
    search_store.save(searches)
    assert search_store.load()["Needs Review"].filters.review_state == "pending"
    session_store = SessionStore(tmp_path / "session.json")
    state = SessionState(repository="/external/data", search="fjord", selected_candidate="id")
    session_store.save(state)
    assert session_store.load() == state
    assert not (tmp_path / "external-data").exists()


def test_batch_review_is_one_service_changeset_and_atomic_apply(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    criteria = ReviewCriteria.model_validate(
        {name: CriterionValue.UNKNOWN for name in ReviewCriteria.model_fields}
    )
    operation = BatchReviewOperation(
        candidate_ids=(
            "10000000-0000-4000-8000-000000000006",
            "10000000-0000-4000-8000-000000000022",
        ),
        decision=ReviewDecision.NEEDS_REVIEW,
        reviewer_id="reviewer-001",
        reviewed_at=datetime.fromisoformat("2026-07-23T12:00:00+02:00"),
        criteria=criteria,
        comment="Batch triage",
    )
    changeset = service.preview(operation)
    assert changeset.operation == "review.batch_needs_review"
    assert len(changeset.records_added) == 2
    service.apply(changeset)
    assert service.candidate(operation.candidate_ids[0]).status.value == "needs_review"
    assert service.candidate(operation.candidate_ids[1]).status.value == "needs_review"


def yes_criteria() -> ReviewCriteria:
    return ReviewCriteria.model_validate(
        {name: CriterionValue.YES for name in ReviewCriteria.model_fields}
    )


def test_batch_approval_requires_complete_criteria_and_is_atomic(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_ids = (
        "10000000-0000-4000-8000-000000000005",
        "10000000-0000-4000-8000-000000000021",
    )
    before = {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }
    incomplete = ReviewCriteria.model_validate(
        {name: CriterionValue.UNKNOWN for name in ReviewCriteria.model_fields}
    )
    with pytest.raises(MutationRejectedError, match="approval requires criteria"):
        service.preview(
            BatchReviewOperation(
                candidate_ids=candidate_ids,
                decision=ReviewDecision.APPROVE,
                reviewer_id="reviewer-001",
                reviewed_at=datetime.fromisoformat("2026-07-23T12:00:00+02:00"),
                criteria=incomplete,
            )
        )
    assert before == {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }

    valid = BatchReviewOperation(
        candidate_ids=candidate_ids,
        decision=ReviewDecision.APPROVE,
        reviewer_id="reviewer-001",
        reviewed_at=datetime.fromisoformat("2026-07-23T12:00:00+02:00"),
        criteria=yes_criteria(),
        comment="Batch approval",
    )
    change = service.preview(valid)
    assert "common=yes" in dict(change.details)["criteria"]
    service.apply(change)
    assert all(service.candidate(item).status.value == "approved" for item in candidate_ids)
    assert all(len(service.reviews(item)) == 1 for item in candidate_ids)


def test_batch_approval_validates_all_candidates_before_any_write(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    candidate_ids = (
        "10000000-0000-4000-8000-000000000005",
        "10000000-0000-4000-8000-000000000006",  # submitted, cannot approve directly
    )
    operation = BatchReviewOperation(
        candidate_ids=candidate_ids,
        decision=ReviewDecision.APPROVE,
        reviewer_id="reviewer-001",
        reviewed_at=datetime.fromisoformat("2026-07-23T12:00:00+02:00"),
        criteria=yes_criteria(),
    )
    before = {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(MutationRejectedError) as error:
        service.preview(operation)
    assert candidate_ids[1] in str(error.value)
    assert before == {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }


def test_blocklist_edit_uses_editorial_service_and_preserves_metadata(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)
    service = EditorialService(repository)
    operation = BlocklistEditOperation(
        language="en",
        blocklist_id="en-reserved-examples",
        action="add",
        word="workbench",
    )
    changeset = service.preview(operation)
    assert changeset.operation == "blocklist.edit"
    service.apply(changeset)
    assert "workbench\n" in (repository.root / "languages/en/blocklists/words.txt").read_text()
    assert (
        "en-reserved-examples"
        in (repository.root / "languages/en/blocklists/metadata.yaml").read_text()
    )


def test_dashboard_and_power_screens_open_without_writes(tmp_path: Path) -> None:
    repository = repository_copy(tmp_path)

    async def scenario() -> None:
        application = EditorialWorkbench(repository)
        async with application.run_test(size=(160, 55)) as pilot:
            await pilot.pause()
            dashboard = str(application.query_one("#dashboard", Static).render())
            assert "Candidates 72" in dashboard
            application.action_statistics()
            await pilot.pause()
            await pilot.press("escape")
            application.action_similarity()
            await pilot.pause()
            assert application.screen.__class__.__name__ == "SimilarityScreen"
            await pilot.press("escape")
            application.action_command_palette()
            await pilot.pause()
            assert application.screen.__class__.__name__ == "CommandPaletteScreen"
            await pilot.press("escape")

    before = {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }
    asyncio.run(scenario())
    after = {
        path.relative_to(repository.root).as_posix(): path.read_bytes()
        for path in repository.root.rglob("*")
        if path.is_file()
    }
    assert before == after
