import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import workflow
from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.api.files import serve_track_file
from app.config import Settings
from app.models import Track
from app.pipeline import edits as ed
from app.pipeline import postprocess as pp
from app.pipeline.notation import write_musicxml

router = APIRouter(tags=["arrangement"])


class LevelRead(BaseModel):
    level: pp.Level
    right_notes: int
    left_notes: int
    max_polyphony_right: int
    max_polyphony_left: int
    edits: int = 0
    unmatched_edits: int = 0  # corrections dont la note n'existe plus après un recalcul
    midi_url: str
    notes_url: str
    musicxml_url: str


class ArrangementRead(BaseModel):
    available: bool
    tempo: float | None = None
    key: str | None = None
    chords: int | None = None
    levels: list[LevelRead] = []
    params: pp.PostprocessParams | None = None


class EditsBody(BaseModel):
    edits: list[ed.Edit]


def _read(track: Track, manifest: dict | None) -> ArrangementRead:
    if manifest is None:
        return ArrangementRead(available=False)
    base = f"/tracks/{track.id}"
    return ArrangementRead(
        available=True,
        tempo=manifest["tempo"],
        key=manifest["key"],
        chords=manifest["chords"],
        levels=[
            LevelRead(
                **lvl,
                midi_url=f"{base}/arrangement/{lvl['level']}.mid",
                notes_url=f"{base}/arrangement/{lvl['level']}.json",
                musicxml_url=f"{base}/export/{lvl['level']}.musicxml",
            )
            for lvl in manifest["levels"]
        ],
        params=pp.PostprocessParams(**manifest["params"]),
    )


def _arranged_dir(settings: Settings, track: Track, level: str) -> Path:
    directory = workflow.arrangement_dir(settings, track)
    if level not in pp.LEVELS or not (directory / f"{level}{pp.BASE_SUFFIX}").exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Niveau introuvable (post-traitement lancé ?)."
        )
    return directory


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


# --- Éditeur : corrections manuelles d'un niveau ---------------------------------------------


@router.get("/tracks/{track_id}/arrangement/{level}/edits", response_model=list[ed.Edit])
def list_edits(
    track_id: str, level: str, session: SessionDep, settings: SettingsDep
) -> list[ed.Edit]:
    directory = _arranged_dir(settings, get_track_or_404(session, track_id), level)
    return ed.load_edits(directory).get(level, [])


@router.post("/tracks/{track_id}/arrangement/{level}/edits", response_model=ArrangementRead)
def add_edits(
    track_id: str, level: str, body: EditsBody, session: SessionDep, settings: SettingsDep
) -> ArrangementRead:
    track = get_track_or_404(session, track_id)
    directory = _arranged_dir(settings, track, level)
    edits = ed.load_edits(directory)
    edits[level] = [*edits.get(level, []), *body.edits]
    ed.save_edits(directory, edits)
    return _read(track, pp.refresh_level(directory, level))


@router.delete("/tracks/{track_id}/arrangement/{level}/edits", response_model=ArrangementRead)
def reset_edits(
    track_id: str, level: str, session: SessionDep, settings: SettingsDep, last: bool = False
) -> ArrangementRead:
    """`last=true` : annule la dernière correction ; sinon les efface toutes."""
    track = get_track_or_404(session, track_id)
    directory = _arranged_dir(settings, track, level)
    edits = ed.load_edits(directory)
    edits[level] = edits.get(level, [])[:-1] if last else []
    ed.save_edits(directory, edits)
    return _read(track, pp.refresh_level(directory, level))


# --- Fichiers ------------------------------------------------------------------------------


@router.get("/tracks/{track_id}/export/{level}.musicxml")
def export_musicxml(
    track_id: str, level: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    """Partition MusicXML du niveau (générée à la demande, puis gardée jusqu'à la
    prochaine modification du niveau)."""
    track = get_track_or_404(session, track_id)
    directory = _arranged_dir(settings, track, level)
    path = directory / f"{level}.musicxml"
    if not path.exists():
        level_data = json.loads((directory / f"{level}.json").read_text(encoding="utf-8"))
        write_musicxml(level_data, path, track.title)
    return FileResponse(
        path,
        media_type="application/vnd.recordare.musicxml+xml",
        filename=f"{track.title} - {level}.musicxml",
    )


@router.get("/tracks/{track_id}/arrangement/{filename}")
def get_arrangement_file(
    track_id: str, filename: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    track = get_track_or_404(session, track_id)
    if ".base." in filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.")
    return serve_track_file(workflow.arrangement_dir(settings, track), filename, track.title)
