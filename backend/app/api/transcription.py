from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from app import workflow
from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.api.files import serve_track_file
from app.models import TRANSCRIBABLE_STEMS, Track
from app.pipeline import transcribe as tr

router = APIRouter(tags=["transcription"])


class TranscribeRequest(BaseModel):
    stems: list[str] | None = None  # None = sélection enregistrée sur le morceau
    params: tr.TranscribeParams = tr.TranscribeParams()

    @field_validator("stems")
    @classmethod
    def check_stems(cls, stems: list[str] | None) -> list[str] | None:
        if stems is not None and (not stems or set(stems) - TRANSCRIBABLE_STEMS):
            raise ValueError("Pistes invalides : piano, other, bass, guitar ou vocals.")
        return stems


class StemTranscriptionRead(BaseModel):
    stem: str
    engine: str
    notes: int
    pedals: int
    cached: bool
    midi_url: str


class TranscriptionRead(BaseModel):
    available: bool
    stems: list[StemTranscriptionRead] = []
    merged_url: str | None = None
    params: tr.TranscribeParams | None = None
    elapsed_s: float | None = None


def _read(track: Track, manifest: dict | None) -> TranscriptionRead:
    if manifest is None:
        return TranscriptionRead(available=False)
    base = f"/tracks/{track.id}/midi"
    return TranscriptionRead(
        available=True,
        stems=[
            StemTranscriptionRead(**s, midi_url=f"{base}/{s['stem']}.mid")
            for s in manifest["stems"]
        ],
        merged_url=f"{base}/{tr.MERGED}.mid",
        params=tr.TranscribeParams(**manifest["params"]),
        elapsed_s=manifest.get("elapsed_s"),
    )


@router.get("/transcription/defaults", response_model=tr.TranscribeParams)
def transcription_defaults() -> tr.TranscribeParams:
    return tr.TranscribeParams()


@router.get("/tracks/{track_id}/transcription", response_model=TranscriptionRead)
def get_transcription(
    track_id: str, session: SessionDep, settings: SettingsDep
) -> TranscriptionRead:
    track = get_track_or_404(session, track_id)
    return _read(track, tr.read_manifest(workflow.midi_dir(settings, track)))


@router.post("/tracks/{track_id}/transcribe", response_model=TranscriptionRead)
def transcribe_track(
    track_id: str, body: TranscribeRequest, session: SessionDep, settings: SettingsDep
) -> TranscriptionRead:
    """Sépare si nécessaire (cache), transcrit puis régénère les niveaux. Synchrone (phase 5)."""
    track = get_track_or_404(session, track_id)
    stems = body.stems or track.stems_to_transcribe
    result = workflow.transcribe(settings, track, stems, body.params)
    return _read(track, result.manifest)


@router.get("/tracks/{track_id}/midi/{filename}")
def get_midi(
    track_id: str, filename: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    track = get_track_or_404(session, track_id)
    if not filename.endswith(".mid"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MIDI introuvable.")
    return serve_track_file(workflow.midi_dir(settings, track), filename, track.title)
