from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProposedFile:
    relative_path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class OperationPlan:
    files: tuple[ProposedFile, ...]
    records_added: tuple[str, ...] = ()
    records_modified: tuple[str, ...] = ()
    records_superseded: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class EditorialContextProtocol(Protocol):
    def read_bytes(self, relative_path: str) -> bytes: ...

    def normalize(self, language: str, word: str) -> str: ...

    def candidate_exists(self, language: str, normalized_word: str) -> bool: ...


class EditorialOperation(Protocol):
    @property
    def name(self) -> str: ...

    def plan(self, context: EditorialContextProtocol) -> OperationPlan: ...


@dataclass(frozen=True, slots=True)
class AddCandidateOperation:
    language: str
    word: str

    @property
    def name(self) -> str:
        return "add_candidate"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        from .errors import MutationRejectedError

        raise MutationRejectedError("AddCandidateOperation is reserved for M3.1")


@dataclass(frozen=True, slots=True)
class EditCandidateOperation:
    candidate_id: str

    @property
    def name(self) -> str:
        return "edit_candidate"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        from .errors import MutationRejectedError

        raise MutationRejectedError("EditCandidateOperation is reserved for M3.1")


@dataclass(frozen=True, slots=True)
class ReviewOperation:
    candidate_id: str

    @property
    def name(self) -> str:
        return "review"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        from .errors import MutationRejectedError

        raise MutationRejectedError("ReviewOperation is reserved for M3.1")


@dataclass(frozen=True, slots=True)
class ProvenanceOperation:
    candidate_id: str

    @property
    def name(self) -> str:
        return "provenance"

    def plan(self, context: EditorialContextProtocol) -> OperationPlan:
        from .errors import MutationRejectedError

        raise MutationRejectedError("ProvenanceOperation is reserved for M3.1")
