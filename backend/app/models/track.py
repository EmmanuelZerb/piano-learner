from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

# La « prod » sans voix ni batterie. La batterie n'est jamais transcriptible en notes.
DEFAULT_TRANSCRIBE_STEMS = ["piano", "other", "bass"]
TRANSCRIBABLE_STEMS = {"piano", "other", "bass", "guitar", "vocals"}


class TrackSource(StrEnum):
    UPLOAD = "upload"
    YOUTUBE = "youtube"


def _new_id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Track(SQLModel, table=True):
    """Un morceau importé. Ses fichiers vivent dans storage/tracks/{id}/."""

    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str
    artist: str | None = None
    source: TrackSource
    source_url: str | None = None
    original_filename: str | None = None
    duration_s: float
    # Hash du WAV normalisé : déduplication et clé de cache pour la séparation (phase 2).
    wav_sha256: str = Field(index=True, unique=True)
    has_thumbnail: bool = False
    created_at: datetime = Field(default_factory=_now)
    # None = sélection par défaut (DEFAULT_TRANSCRIBE_STEMS).
    transcribe_stems: list[str] | None = Field(default=None, sa_column=Column(JSON))

    @property
    def stems_to_transcribe(self) -> list[str]:
        return self.transcribe_stems or list(DEFAULT_TRANSCRIBE_STEMS)
