from datetime import datetime
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import SessionDep, get_track_or_404
from app.models import PracticeSession

router = APIRouter(prefix="/tracks/{track_id}/practice", tags=["practice"])


class PracticeCreate(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    mode: Literal["wait", "free"]
    hands: Literal["R", "L", "LR"]
    speed: float = Field(ge=0.25, le=1.5)
    hits: int = Field(ge=0)
    wrongs: int = Field(ge=0)
    misses: int = Field(ge=0)
    duration_s: float = Field(ge=0)


class PracticeRead(PracticeCreate):
    id: str
    accuracy: float
    created_at: datetime

    @classmethod
    def from_session(cls, s: PracticeSession) -> "PracticeRead":
        return cls(**s.model_dump(), accuracy=round(s.accuracy, 4))


class PracticeHistory(BaseModel):
    sessions: list[PracticeRead]
    best_accuracy: float | None
    total_duration_s: float


@router.post("", response_model=PracticeRead, status_code=status.HTTP_201_CREATED)
def record_session(track_id: str, body: PracticeCreate, session: SessionDep) -> PracticeRead:
    track = get_track_or_404(session, track_id)
    practice = PracticeSession(track_id=track.id, **body.model_dump())
    session.add(practice)
    session.commit()
    session.refresh(practice)
    return PracticeRead.from_session(practice)


@router.get("", response_model=PracticeHistory)
def practice_history(track_id: str, session: SessionDep) -> PracticeHistory:
    track = get_track_or_404(session, track_id)
    rows = session.exec(
        select(PracticeSession)
        .where(PracticeSession.track_id == track.id)
        .order_by(col(PracticeSession.created_at).desc())
    ).all()
    return PracticeHistory(
        sessions=[PracticeRead.from_session(r) for r in rows[:50]],
        best_accuracy=max((round(r.accuracy, 4) for r in rows), default=None),
        total_duration_s=round(sum(r.duration_s for r in rows), 1),
    )
