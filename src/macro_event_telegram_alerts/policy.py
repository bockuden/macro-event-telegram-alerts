"""Project-owned event classification policy."""

from dataclasses import dataclass
from enum import StrEnum


class EventSignificance(StrEnum):
    """Significance assigned by this project, never by a source institution."""

    SIGNIFICANT = "significant"
    INFORMATIONAL = "informational"


class EventImportance(StrEnum):
    """Project-owned impact tier; it is not an official institution rating."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class SignificancePolicy:
    """Traceable project classification attached to a normalized event."""

    significance: EventSignificance
    revision: str
    importance: EventImportance = EventImportance.MEDIUM

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise ValueError("policy revision must not be empty")


def importance_at_least(policy: SignificancePolicy, minimum: EventImportance) -> bool:
    """Return whether a project-policy tier passes the configured minimum."""
    order = {EventImportance.LOW: 0, EventImportance.MEDIUM: 1, EventImportance.HIGH: 2}
    return order[policy.importance] >= order[minimum]
