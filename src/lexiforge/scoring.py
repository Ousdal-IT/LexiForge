from pathlib import Path

import yaml
from pydantic import ValidationError

from .constants import DEFAULT_DATA_ROOT
from .errors import ConfigurationError
from .models import ScoreResult, ScoreSignal, StrictModel, WordCandidate


class ScoreBounds(StrictModel):
    minimum: int
    maximum: int


class ScoringConfig(StrictModel):
    base_score: int
    signals: dict[str, int]
    bounds: ScoreBounds
    preferred_length: dict[str, int]


def load_scoring_config(data_root: Path = DEFAULT_DATA_ROOT) -> ScoringConfig:
    path = data_root / "shared" / "scoring.yaml"
    try:
        return ScoringConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"invalid scoring configuration {path}: {error}") from error


def score_candidate(
    candidate: WordCandidate,
    *,
    has_provenance: bool,
    review_complete: bool,
    similarity_warning: bool = False,
    blocklist_warning: bool = False,
    config: ScoringConfig | None = None,
) -> ScoreResult:
    config = config or load_scoring_config()
    signals = [
        ScoreSignal(id="base_score", value=config.base_score, message="Configured base score")
    ]
    states = {
        "all_required_review_criteria_yes": review_complete,
        "concrete_category": candidate.category is not None,
        "preferred_length": config.preferred_length["minimum"]
        <= len(candidate.word)
        <= config.preferred_length["maximum"],
        "similarity_distance_1": similarity_warning,
        "blocklist_warning": blocklist_warning,
        "missing_provenance": not has_provenance,
        "unresolved_required_criterion": not review_complete,
    }
    for signal_id in sorted(states):
        if states[signal_id] and signal_id in config.signals:
            signals.append(
                ScoreSignal(
                    id=signal_id,
                    value=config.signals[signal_id],
                    message=signal_id.replace("_", " "),
                )
            )
    raw = sum(signal.value for signal in signals)
    total = min(config.bounds.maximum, max(config.bounds.minimum, raw))
    return ScoreResult(total=total, signals=signals)
