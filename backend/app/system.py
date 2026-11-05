"""Détection de l'environnement : ffmpeg et accélérateur (CUDA / MPS / CPU)."""

import importlib.util
import shutil
import subprocess
from functools import lru_cache

from pydantic import BaseModel


class ToolInfo(BaseModel):
    available: bool
    path: str | None = None
    version: str | None = None


class DeviceInfo(BaseModel):
    torch_installed: bool
    torch_version: str | None = None
    device: str  # "cuda", "mps" ou "cpu"
    name: str | None = None
    vram_gb: float | None = None


def _tool_info(binary: str) -> ToolInfo:
    path = shutil.which(binary)
    if path is None:
        return ToolInfo(available=False)
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
        version = out.splitlines()[0] if out else None
    except (OSError, subprocess.TimeoutExpired):
        version = None
    return ToolInfo(available=True, path=path, version=version)


@lru_cache
def ffmpeg_info() -> ToolInfo:
    return _tool_info("ffmpeg")


@lru_cache
def ffprobe_info() -> ToolInfo:
    return _tool_info("ffprobe")


@lru_cache
def device_info() -> DeviceInfo:
    """Torch est optionnel (groupe `ml`) : on ne l'importe que s'il est installé."""
    if importlib.util.find_spec("torch") is None:
        return DeviceInfo(torch_installed=False, device="cpu")

    import torch

    version = str(torch.__version__)
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        return DeviceInfo(
            torch_installed=True,
            torch_version=version,
            device="cuda",
            name=props.name,
            vram_gb=round(props.total_memory / 1024**3, 1),
        )
    if torch.backends.mps.is_available():
        return DeviceInfo(
            torch_installed=True, torch_version=version, device="mps", name="Apple MPS"
        )
    return DeviceInfo(torch_installed=True, torch_version=version, device="cpu")


def torch_device() -> str:
    return device_info().device
