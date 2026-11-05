from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class PracticeSession(SQLModel, table=True):
    """Une séance d'entraînement sur un morceau (mode entraînement du lecteur)."""

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    track_id: str = Field(index=True)
    level: str  # beginner | intermediate | advanced
    mode: str  # wait | free
    hands: str  # "R", "L" ou "LR"
    speed: float
    hits: int
    wrongs: int
    misses: int
    duration_s: float
    created_at: datetime = Field(default_factory=_now)

    @property
    def accuracy(self) -> float:
        total = self.hits + self.wrongs + self.misses
        return self.hits / total if total else 0.0
