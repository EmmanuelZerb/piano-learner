from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import workflow
from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.api.files import serve_track_file
from app.models import Track
from app.pipeline import postprocess as pp

router = APIRouter(tags=["arrangement"])


class LevelRead(BaseModel):
    level: pp.Level
    right_notes: int
    left_notes: int
    max_polyphony_right: int
    max_polyphony_left: int
    midi_url: str
    notes_url: str


class ArrangementRead(BaseModel):
    available: bool
    tempo: float | None = None
    key: str | None = None
    chords: int | None = None
    levels: list[LevelRead] = []
    params: pp.PostprocessParams | None = None


def _read(track: Track, manifest: dict | None) -> ArrangementRead:
    if manifest is None:
        return ArrangementRead(available=False)
    base = f"/tracks/{track.id}/arrangement"
    return ArrangementRead(
        available=True,
        tempo=manifest["tempo"],
        key=manifest["key"],
        chords=manifest["chords"],
        levels=[
            LevelRead(
                **lvl,
                midi_url=f"{base}/{lvl['level']}.mid",
                notes_url=f"{base}/{lvl['level']}.json",
            )
            for lvl in manifest["levels"]
        ],
        params=pp.PostprocessParams(**manifest["params"]),
    )


@router.get("/arrangement/defaults", response_model=pp.PostprocessParams)
def arrangement_defaults() -> pp.PostprocessParams:
    return pp.PostprocessParams()


@router.get("/tracks/{track_id}/arrangement", response_model=ArrangementRead)
def get_arrangement(track_id: str, session: SessionDep, settings: SettingsDep) -> ArrangementRead:
    track = get_track_or_404(session, track_id)
    return _read(track, pp.read_manifest(workflow.arrangement_dir(settings, track)))


@router.post("/tracks/{track_id}/arrange", response_model=ArrangementRead)
def arrange_track(
    track_id: str, body: pp.PostprocessParams, session: SessionDep, settings: SettingsDep
) -> ArrangementRead:
    """Relance seulement le post-traitement (quelques secondes, sans modèle)."""
    track = get_track_or_404(session, track_id)
    return _read(track, workflow.arrange(settings, track, body))


@router.get("/tracks/{track_id}/arrangement/{filename}")
def get_arrangement_file(
    track_id: str, filename: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    track = get_track_or_404(session, track_id)
    return serve_track_file(workflow.arrangement_dir(settings, track), filename, track.title)
