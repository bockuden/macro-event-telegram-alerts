"""Project-owned event classification policy."""

from dataclasses import dataclass
from enum import StrEnum


class EventSignificance(StrEnum):
    """Significance assigned by this project, never by a source institution."""

    SIGNIFICANT = "significant"
    INFORMATIONAL = "informational"


@dataclass(frozen=True, slots=True)
class SignificancePolicy:
    """Traceable project classification attached to a normalized event."""

    significance: EventSignificance
    revision: str

    def __post_init__(self) -> None:
        if not self.revision.strip():
            raise ValueError("policy revision must not be empty")
