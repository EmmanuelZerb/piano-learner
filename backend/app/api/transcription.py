from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.config import Settings
from app.library import track_dir
from app.models import TRANSCRIBABLE_STEMS, Track
from app.pipeline import separate as sep
from app.pipeline import transcribe as tr
from app.pipeline.ingest import WAV_NAME
from app.system import torch_device

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


def midi_dir(settings: Settings, track: Track) -> Path:
    return track_dir(settings, track.id) / "midi"


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
    return _read(track, tr.read_manifest(midi_dir(settings, track)))


@router.post("/tracks/{track_id}/transcribe", response_model=TranscriptionRead)
def transcribe_track(
    track_id: str, body: TranscribeRequest, session: SessionDep, settings: SettingsDep
) -> TranscriptionRead:
    """Sépare si nécessaire (cache), puis transcrit. Synchrone jusqu'à la phase 5."""
    track = get_track_or_404(session, track_id)
    device = torch_device()
    separation = sep.separate(
        track_dir(settings, track.id) / WAV_NAME,
        sep.stems_dir(settings.stems_cache_dir, track.wav_sha256),
        device,
    )
    result = tr.transcribe_stems(
        separation.stems,
        body.stems or track.stems_to_transcribe,
        body.params,
        settings.transcriptions_cache_dir / track.wav_sha256,
        midi_dir(settings, track),
        device,
        settings.models_dir,
    )
    return _read(track, result.manifest)


@router.get("/tracks/{track_id}/midi/{filename}")
def get_midi(
    track_id: str, filename: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    track = get_track_or_404(session, track_id)
    directory = midi_dir(settings, track).resolve()
    path = (directory / filename).resolve()
    # Le nom vient de l'URL : on n'accepte que les fichiers .mid produits dans ce dossier.
    if path.suffix != ".mid" or path.parent != directory or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MIDI introuvable (transcription lancée ?).")
    download_name = f"{track.title} - {path.stem}.mid"
    return FileResponse(path, media_type="audio/midi", filename=download_name)
