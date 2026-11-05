import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(storage_dir=tmp_path / "storage", max_upload_mb=5, max_duration_min=1)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


AudioFactory = Callable[..., Path]


@pytest.fixture
def make_audio(tmp_path: Path) -> AudioFactory:
    """Génère un fichier audio réel (sinusoïde) via ffmpeg."""

    def factory(name: str = "tone.mp3", seconds: float = 1.0, freq: int = 440, **tags: str) -> Path:
        out = tmp_path / "inputs" / name
        out.parent.mkdir(exist_ok=True)
        metadata = [arg for k, v in tags.items() for arg in ("-metadata", f"{k}={v}")]
        cmd = [
            "ffmpeg", "-nostdin", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}:sample_rate=22050",
            *metadata, str(out),
        ]  # fmt: skip
        subprocess.run(cmd, check=True, capture_output=True)
        return out

    return factory
