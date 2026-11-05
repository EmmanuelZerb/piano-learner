"""Bibliothèque : dossiers de travail temporaires et enregistrement des morceaux en base."""

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.config import Settings
from app.models import Job, PracticeSession, Track, TrackSource
from app.pipeline.ingest import WAV_NAME, IngestedAudio, sha256_file


@contextmanager
def work_dir(settings: Settings) -> Iterator[Path]:
    """Dossier temporaire supprimé en cas d'erreur (ou s'il n'a pas été déplacé)."""
    path = settings.tmp_dir / uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def track_dir(settings: Settings, track_id: str) -> Path:
    return settings.tracks_dir / track_id


def delete_track(session: Session, settings: Settings, track: Track) -> None:
    """Supprime le morceau, ses fichiers, ses caches (stems, notes, temps), ses tâches et
    son historique d'entraînement."""
    shutil.rmtree(track_dir(settings, track.id), ignore_errors=True)
    for cache in (
        settings.stems_cache_dir,
        settings.transcriptions_cache_dir,
        settings.analysis_cache_dir,
    ):
        shutil.rmtree(cache / track.wav_sha256, ignore_errors=True)
    for job in session.exec(select(Job).where(Job.track_id == track.id)).all():
        session.delete(job)
    for practice in session.exec(
        select(PracticeSession).where(PracticeSession.track_id == track.id)
    ).all():
        session.delete(practice)
    session.delete(track)
    session.commit()


def register_track(
    session: Session, settings: Settings, work: Path, audio: IngestedAudio, source: TrackSource
) -> tuple[Track, bool]:
    """Enregistre le morceau, ou renvoie l'existant si le même WAV a déjà été importé.

    Renvoie (track, duplicate).
    """
    digest = sha256_file(work / WAV_NAME)
    existing = session.exec(select(Track).where(Track.wav_sha256 == digest)).first()
    if existing is not None:
        return existing, True

    track = Track(
        title=audio.title,
        artist=audio.artist,
        source=source,
        source_url=audio.source_url,
        original_filename=audio.original_filename,
        duration_s=audio.duration_s,
        wav_sha256=digest,
        has_thumbnail=audio.has_thumbnail,
    )
    settings.tracks_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(work, track_dir(settings, track.id))
    session.add(track)
    session.commit()
    session.refresh(track)
    return track, False
