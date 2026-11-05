from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlmodel import select

from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.library import delete_track, register_track, track_dir, work_dir
from app.models import TRANSCRIBABLE_STEMS, Track, TrackSource
from app.pipeline.ingest import THUMBNAIL_NAME, WAV_NAME, ingest_upload, ingest_youtube

router = APIRouter(prefix="/tracks", tags=["tracks"])


class TrackRead(BaseModel):
    id: str
    title: str
    artist: str | None
    source: TrackSource
    source_url: str | None
    original_filename: str | None
    duration_s: float
    created_at: datetime
    audio_url: str
    thumbnail_url: str | None
    transcribe_stems: list[str]

    @classmethod
    def from_track(cls, track: Track) -> "TrackRead":
        base = f"/tracks/{track.id}"
        return cls(
            **track.model_dump(exclude={"wav_sha256", "has_thumbnail", "transcribe_stems"}),
            audio_url=f"{base}/audio",
            thumbnail_url=f"{base}/thumbnail" if track.has_thumbnail else None,
            transcribe_stems=track.stems_to_transcribe,
        )


class TrackCreated(BaseModel):
    track: TrackRead
    duplicate: bool


class YouTubeImport(BaseModel):
    url: str


class TrackUpdate(BaseModel):
    transcribe_stems: list[str]

    @field_validator("transcribe_stems")
    @classmethod
    def check_stems(cls, stems: list[str]) -> list[str]:
        if not stems:
            raise ValueError("Choisis au moins une piste à transcrire.")
        unknown = set(stems) - TRANSCRIBABLE_STEMS
        if unknown:
            raise ValueError(f"Pistes non transcriptibles : {', '.join(sorted(unknown))}.")
        return sorted(set(stems), key=stems.index)


# Routes synchrones : FastAPI les exécute dans un pool de threads (ffmpeg / yt-dlp bloquants).
# Elles passeront en tâches de fond avec suivi de progression en phase 5.


@router.post("/upload", response_model=TrackCreated, status_code=status.HTTP_201_CREATED)
def upload_track(
    file: Annotated[UploadFile, File()], session: SessionDep, settings: SettingsDep
) -> TrackCreated:
    with work_dir(settings) as work:
        audio = ingest_upload(
            file.file,
            file.filename or "upload",
            work,
            settings.max_upload_bytes,
            settings.max_duration_s,
        )
        track, duplicate = register_track(session, settings, work, audio, TrackSource.UPLOAD)
    return TrackCreated(track=TrackRead.from_track(track), duplicate=duplicate)


@router.post("/youtube", response_model=TrackCreated, status_code=status.HTTP_201_CREATED)
def import_youtube(body: YouTubeImport, session: SessionDep, settings: SettingsDep) -> TrackCreated:
    with work_dir(settings) as work:
        audio = ingest_youtube(body.url, work, settings.max_duration_s)
        track, duplicate = register_track(session, settings, work, audio, TrackSource.YOUTUBE)
    return TrackCreated(track=TrackRead.from_track(track), duplicate=duplicate)


@router.get("", response_model=list[TrackRead])
def list_tracks(session: SessionDep) -> list[TrackRead]:
    tracks = session.exec(select(Track).order_by(Track.created_at.desc())).all()  # type: ignore[attr-defined]
    return [TrackRead.from_track(t) for t in tracks]


@router.get("/{track_id}", response_model=TrackRead)
def get_track(track_id: str, session: SessionDep) -> TrackRead:
    return TrackRead.from_track(get_track_or_404(session, track_id))


@router.patch("/{track_id}", response_model=TrackRead)
def update_track(track_id: str, body: TrackUpdate, session: SessionDep) -> TrackRead:
    track = get_track_or_404(session, track_id)
    track.transcribe_stems = body.transcribe_stems
    session.add(track)
    session.commit()
    session.refresh(track)
    return TrackRead.from_track(track)


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_track(
    track_id: str, request: Request, session: SessionDep, settings: SettingsDep
) -> None:
    track = get_track_or_404(session, track_id)
    if request.app.state.jobs.has_active(track.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Un traitement est en cours : annule-le avant de supprimer."
        )
    delete_track(session, settings, track)


@router.get("/{track_id}/audio")
def get_track_audio(track_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    track = get_track_or_404(session, track_id)
    return FileResponse(track_dir(settings, track.id) / WAV_NAME, media_type="audio/wav")


@router.get("/{track_id}/thumbnail")
def get_track_thumbnail(track_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    track = get_track_or_404(session, track_id)
    path = track_dir(settings, track.id) / THUMBNAIL_NAME
    if not track.has_thumbnail or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pas de miniature.")
    return FileResponse(path, media_type="image/jpeg")
