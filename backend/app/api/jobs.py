import shutil
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from app.api.deps import SessionDep, SettingsDep, get_track_or_404
from app.jobs import JobManager, JobRead, ProcessOptions
from app.pipeline.ingest import canonical_youtube_url, save_upload, validate_youtube_url

router = APIRouter(tags=["jobs"])


def get_manager(request: Request) -> JobManager:
    return request.app.state.jobs


class YouTubeJob(BaseModel):
    url: str
    options: ProcessOptions = ProcessOptions()


class TrackJob(BaseModel):
    options: ProcessOptions = ProcessOptions()


def _job_or_404(manager: JobManager, job_id: str) -> JobRead:
    state = manager.get(job_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return state


@router.post("/jobs/youtube", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def create_youtube_job(body: YouTubeJob, request: Request) -> JobRead:
    url = canonical_youtube_url(validate_youtube_url(body.url))  # URL invalide : refus immédiat
    payload = {"url": url, "options": body.options.model_dump()}
    return get_manager(request).submit(url, "youtube", payload)


@router.post("/jobs/upload", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def create_upload_job(
    file: Annotated[UploadFile, File()],
    request: Request,
    settings: SettingsDep,
    options: Annotated[str | None, Form()] = None,
) -> JobRead:
    """Le fichier est copié et son type vérifié pendant la requête ; la conversion et la
    suite du traitement se font en tâche de fond."""
    try:
        parsed = ProcessOptions.model_validate_json(options) if options else ProcessOptions()
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    filename = file.filename or "upload"
    upload_dir = settings.tmp_dir / uuid4().hex
    upload_dir.mkdir(parents=True)
    try:
        source = save_upload(file.file, filename, upload_dir, settings.max_upload_bytes)
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    payload = {
        "upload_dir": str(upload_dir),
        "source_path": str(source),
        "filename": filename,
        "options": parsed.model_dump(),
    }
    return get_manager(request).submit(filename, "upload", payload)


@router.post(
    "/tracks/{track_id}/jobs", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED
)
def create_track_job(
    track_id: str, body: TrackJob, request: Request, session: SessionDep
) -> JobRead:
    track = get_track_or_404(session, track_id)
    manager = get_manager(request)
    if manager.has_active(track.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un traitement est déjà en cours.")
    payload = {"options": body.options.model_dump()}
    return manager.submit(track.title, "track", payload, track_id=track.id)


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(request: Request, track_id: str | None = None, active: bool = False) -> list[JobRead]:
    return get_manager(request).list(track_id=track_id, active=active)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, request: Request) -> JobRead:
    return _job_or_404(get_manager(request), job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, request: Request) -> JobRead:
    manager = get_manager(request)
    _job_or_404(manager, job_id)
    return manager.cancel(job_id) or _job_or_404(manager, job_id)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events : un message JSON (JobRead) par mise à jour, jusqu'à la fin."""
    manager = get_manager(request)
    _job_or_404(manager, job_id)

    async def stream() -> AsyncIterator[str]:
        async for state in manager.subscribe(job_id):
            yield ": ping\n\n" if state is None else f"data: {state.model_dump_json()}\n\n"

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)
