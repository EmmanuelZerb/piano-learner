from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from sqlmodel import col, select

from app import workflow
from app.api.deps import SessionDep, SettingsDep
from app.api.tracks import TrackRead
from app.config import Settings
from app.jobs import JobRead
from app.models import PracticeSession, Track
from app.pipeline import postprocess as pp
from app.pipeline import separate as sep
from app.pipeline import transcribe as tr

router = APIRouter(tags=["library"])

Stage = Literal["imported", "separated", "transcribed", "arranged"]


class LibraryItem(TrackRead):
    stage: Stage
    levels: list[str]
    sessions: int
    best_accuracy: float | None
    practice_seconds: float
    last_practiced_at: datetime | None
    last_level: str | None
    active_job: JobRead | None


def _stage(settings: Settings, track: Track) -> tuple[Stage, list[str]]:
    manifest = pp.read_manifest(workflow.arrangement_dir(settings, track))
    if manifest:
        return "arranged", [lvl["level"] for lvl in manifest["levels"]]
    if tr.read_manifest(workflow.midi_dir(settings, track)):
        return "transcribed", []
    stems = sep.stems_dir(settings.stems_cache_dir, track.wav_sha256)
    return ("separated" if sep.cached_stems(stems) else "imported"), []


@router.get("/library", response_model=list[LibraryItem])
def library(request: Request, session: SessionDep, settings: SettingsDep) -> list[LibraryItem]:
    """Bibliothèque : chaque morceau avec son état de traitement et sa progression."""
    tracks = session.exec(select(Track).order_by(col(Track.created_at).desc())).all()
    practice = session.exec(
        select(PracticeSession).order_by(col(PracticeSession.created_at).desc())
    ).all()
    active = {j.track_id: j for j in request.app.state.jobs.list(active=True) if j.track_id}

    items = []
    for track in tracks:
        mine = [p for p in practice if p.track_id == track.id]
        stage, levels = _stage(settings, track)
        items.append(
            LibraryItem(
                **TrackRead.from_track(track).model_dump(),
                stage=stage,
                levels=levels,
                sessions=len(mine),
                best_accuracy=round(max(p.accuracy for p in mine), 4) if mine else None,
                practice_seconds=round(sum(p.duration_s for p in mine), 1),
                last_practiced_at=mine[0].created_at if mine else None,
                last_level=mine[0].level if mine else None,
                active_job=active.get(track.id),
            )
        )
    return items
