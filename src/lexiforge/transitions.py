from .errors import ValidationFailure
from .models import CandidateStatus

ALLOWED_TRANSITIONS: frozenset[tuple[CandidateStatus, CandidateStatus]] = frozenset(
    {
        (CandidateStatus.SUBMITTED, CandidateStatus.NEEDS_REVIEW),
        (CandidateStatus.SUBMITTED, CandidateStatus.REJECTED),
        (CandidateStatus.SUBMITTED, CandidateStatus.AUTOMATIC_REJECT),
        (CandidateStatus.NEEDS_REVIEW, CandidateStatus.APPROVED),
        (CandidateStatus.NEEDS_REVIEW, CandidateStatus.REJECTED),
        (CandidateStatus.APPROVED, CandidateStatus.SUPERSEDED),
        (CandidateStatus.APPROVED, CandidateStatus.WITHDRAWN),
        (CandidateStatus.REJECTED, CandidateStatus.NEEDS_REVIEW),
    }
)


def validate_transition(
    previous: CandidateStatus, new: CandidateStatus, *, override: bool = False
) -> None:
    if (previous, new) in ALLOWED_TRANSITIONS:
        return
    if (
        override
        and previous == CandidateStatus.AUTOMATIC_REJECT
        and new == CandidateStatus.NEEDS_REVIEW
    ):
        return
    raise ValidationFailure(f"invalid moderation transition: {previous.value} -> {new.value}")
