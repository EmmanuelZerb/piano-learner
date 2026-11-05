import importlib.util
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import workflow
from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.config import Settings
from app.models import Track
from app.pipeline import separate as sep
from app.pipeline.errors import PipelineError

router = APIRouter(prefix="/tracks/{track_id}", tags=["stems"])


class StemRead(BaseModel):
    name: str
    url: str


class StemsRead(BaseModel):
    model: str
    available: bool
    stems: list[StemRead]
    cached: bool | None = None
    elapsed_s: float | None = None


def _stems_dir(settings: Settings, track: Track) -> Path:
    return sep.stems_dir(settings.stems_cache_dir, track.wav_sha256)


def _stems_read(
    track: Track,
    stems: dict[str, Path] | None,
    cached: bool | None = None,
    elapsed_s: float | None = None,
) -> StemsRead:
    names = [n for n in sep.STEMS if stems and n in stems]
    return StemsRead(
        model=sep.MODEL_NAME,
        available=bool(stems),
        stems=[StemRead(name=n, url=f"/tracks/{track.id}/stems/{n}") for n in names],
        cached=cached,
        elapsed_s=elapsed_s,
    )


@router.get("/stems", response_model=StemsRead)
def get_stems(track_id: str, session: SessionDep, settings: SettingsDep) -> StemsRead:
    track = get_track_or_404(session, track_id)
    return _stems_read(track, sep.cached_stems(_stems_dir(settings, track)))


@router.post("/separate", response_model=StemsRead)
def separate_track(track_id: str, session: SessionDep, settings: SettingsDep) -> StemsRead:
    """Synchrone jusqu'à la phase 5 (≈ 30 s sur GPU pour 3 min, plusieurs minutes sur CPU)."""
    track = get_track_or_404(session, track_id)
    if importlib.util.find_spec("demucs") is None:
        raise PipelineError("ml_missing", "Stack ML absente : lance `uv sync` dans backend.", 503)
    result = workflow.separate(settings, track)
    return _stems_read(
        track, result.stems, cached=result.cached, elapsed_s=round(result.elapsed_s, 1)
    )


@router.get("/stems/{stem}")
def get_stem_audio(
    track_id: str, stem: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    track = get_track_or_404(session, track_id)
    stems = sep.cached_stems(_stems_dir(settings, track)) or {}
    if stem not in stems:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Piste introuvable (séparation lancée ?).")
    return FileResponse(stems[stem], media_type="audio/flac")
