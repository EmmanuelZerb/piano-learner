from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.system import DeviceInfo, ToolInfo, device_info, ffmpeg_info, ffprobe_info


class HealthResponse(BaseModel):
    status: str
    ffmpeg: ToolInfo
    ffprobe: ToolInfo
    device: DeviceInfo


def create_app() -> FastAPI:
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Piano Learner API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
