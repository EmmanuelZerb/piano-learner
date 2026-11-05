"""Séparation de sources avec Demucs (htdemucs_6s) et cache par hash du WAV.

Les stems sont écrits dans {cache_dir}/{wav_sha256}/{model}/{stem}.flac. Le fichier
manifest.json est écrit en dernier : sa présence signifie que le cache est complet.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.pipeline.gpu import gpu_lock

if TYPE_CHECKING:
    import torch

MODEL_NAME = "htdemucs_6s"
STEMS = ("vocals", "drums", "bass", "piano", "guitar", "other")
MANIFEST = "manifest.json"
STEM_EXT = ".flac"

ProgressFn = Callable[[float], None]


@dataclass(frozen=True)
class SeparationResult:
    stems: dict[str, Path]
    cached: bool
    elapsed_s: float = 0.0


def stems_dir(cache_dir: Path, wav_sha256: str, model_name: str = MODEL_NAME) -> Path:
    return cache_dir / wav_sha256 / model_name


def cached_stems(directory: Path) -> dict[str, Path] | None:
    """Stems déjà calculés, ou None si le cache est absent ou incomplet."""
    manifest = directory / MANIFEST
    if not manifest.exists():
        return None
    names: list[str] = json.loads(manifest.read_text(encoding="utf-8"))["stems"]
    paths = {name: directory / f"{name}{STEM_EXT}" for name in names}
    return paths if all(p.exists() for p in paths.values()) else None


@lru_cache(maxsize=1)
def load_model(model_name: str = MODEL_NAME):  # type: ignore[no-untyped-def]  (non exporté)
    from demucs.pretrained import get_model

    model = get_model(model_name)
    model.eval()
    return model


def _read_wav(path: Path) -> "torch.Tensor":
    import soundfile as sf
    import torch

    data, _ = sf.read(path, dtype="float32", always_2d=True)  # (frames, channels)
    return torch.from_numpy(np.ascontiguousarray(data.T))


def _run_model(
    mix: "torch.Tensor", device: str, on_progress: ProgressFn | None
) -> tuple[list[str], "torch.Tensor"]:
    """Applique Demucs. Renvoie (noms des sources, tenseur (sources, canaux, frames))."""
    import torch
    from demucs.apply import apply_model

    model = load_model()
    # Normalisation identique à la CLI demucs : centrer/réduire sur le mixage mono.
    ref = mix.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    total = mix.shape[-1]

    def callback(info: dict) -> None:
        if on_progress and info.get("state") == "end":
            on_progress(min(1.0, info["segment_offset"] / total))

    # split=True découpe en segments de ~8 s : la VRAM reste bornée quelle que soit la
    # durée, et les sorties s'accumulent sur le CPU.
    with torch.no_grad():
        out = apply_model(
            model, ((mix - mean) / std)[None], device=device, split=True,
            overlap=0.25, shifts=0, progress=False, callback=callback,
        )[0]  # fmt: skip
    return list(model.sources), out * std + mean


def _write_stem(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    import soundfile as sf

    tmp = path.with_suffix(".part")
    sf.write(tmp, np.clip(audio.T, -1.0, 1.0), sample_rate, format="FLAC", subtype="PCM_24")
    tmp.replace(path)


def separate(
    wav_path: Path,
    out_dir: Path,
    device: str,
    sample_rate: int = 44100,
    on_progress: ProgressFn | None = None,
) -> SeparationResult:
    """Sépare `wav_path` dans `out_dir`, sauf si le cache y est déjà complet."""
    if (existing := cached_stems(out_dir)) is not None:
        return SeparationResult(existing, cached=True)

    start = time.perf_counter()
    with gpu_lock:
        names, sources = _run_model(_read_wav(wav_path), device, on_progress)

    out_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, Path] = {}
    for name, audio in zip(names, sources.cpu().numpy(), strict=True):
        stems[name] = out_dir / f"{name}{STEM_EXT}"
        _write_stem(stems[name], audio, sample_rate)
    if on_progress:
        on_progress(1.0)
    (out_dir / MANIFEST).write_text(
        json.dumps({"model": MODEL_NAME, "stems": names}), encoding="utf-8"
    )
    return SeparationResult(stems, cached=False, elapsed_s=time.perf_counter() - start)
