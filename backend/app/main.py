from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.arrangement import router as arrangement_router
from app.api.jobs import router as jobs_router
from app.api.stems import router as stems_router
from app.api.tracks import router as tracks_router
from app.api.transcription import router as transcription_router
from app.config import Settings, get_settings
from app.db import make_engine
from app.jobs import JobManager
from app.pipeline.errors import PipelineError
from app.system import DeviceInfo, ToolInfo, device_info, ffmpeg_info, ffprobe_info


class HealthResponse(BaseModel):
    status: str
    ffmpeg: ToolInfo
    ffprobe: ToolInfo
    device: DeviceInfo


async def pipeline_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PipelineError)
    return JSONResponse({"code": exc.code, "detail": exc.message}, status_code=exc.status_code)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await app.state.jobs.start()
    yield
    await app.state.jobs.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Piano Learner API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.jobs = JobManager(settings, app.state.engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(PipelineError, pipeline_error_handler)
    app.include_router(tracks_router)
    app.include_router(stems_router)
    app.include_router(transcription_router)
    app.include_router(arrangement_router)
    app.include_router(jobs_router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        ffmpeg, ffprobe = ffmpeg_info(), ffprobe_info()
        ok = ffmpeg.available and ffprobe.available
        return HealthResponse(
            status="ok" if ok else "degraded",
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            device=device_info(),
        )

    return app


app = create_app()
