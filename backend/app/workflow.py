"""Enchaînement des étapes du pipeline pour un morceau : chemins, caches et dépendances
entre étapes. Les routes l'appellent directement ; les tâches de fond (phase 5) aussi.
"""

from collections.abc import Callable
from pathlib import Path

from app.config import Settings
from app.library import track_dir
from app.models import Track
from app.pipeline import postprocess as pp
from app.pipeline import separate as sep
from app.pipeline import transcribe as tr
from app.pipeline.errors import PipelineError
from app.pipeline.ingest import WAV_NAME
from app.pipeline.notes import StemTranscription
from app.system import torch_device
from app.telemetry import timed

ProgressFn = Callable[[float], None]
StepFn = Callable[[str, float], None]


def wav_path(settings: Settings, track: Track) -> Path:
    return track_dir(settings, track.id) / WAV_NAME


def midi_dir(settings: Settings, track: Track) -> Path:
    return track_dir(settings, track.id) / "midi"


def arrangement_dir(settings: Settings, track: Track) -> Path:
    return track_dir(settings, track.id) / "arrangement"


def separate(
    settings: Settings, track: Track, on_progress: ProgressFn | None = None
) -> sep.SeparationResult:
    with timed("separate", track_id=track.id, device=torch_device()) as info:
        result = sep.separate(
            wav_path(settings, track),
            sep.stems_dir(settings.stems_cache_dir, track.wav_sha256),
            torch_device(),
            on_progress=on_progress,
        )
        info["cached"] = result.cached
    return result


def transcribe(
    settings: Settings,
    track: Track,
    stems: list[str],
    params: tr.TranscribeParams,
    postprocess: pp.PostprocessParams | None = None,
    on_step: StepFn | None = None,
) -> tr.TranscriptionResult:
    """Sépare si besoin, transcrit, puis régénère les niveaux (avec `postprocess`, ou à défaut
    les derniers réglages utilisés). `on_step(étape, fraction)` suit l'avancement."""

    def progress(step: str) -> ProgressFn | None:
        return (lambda fraction: on_step(step, fraction)) if on_step else None

    separation = separate(settings, track, progress("separate"))
    with timed("transcribe", track_id=track.id, stems=stems) as info:
        result = tr.transcribe_stems(
            separation.stems,
            stems,
            params,
            settings.transcriptions_cache_dir / track.wav_sha256,
            midi_dir(settings, track),
            torch_device(),
            settings.models_dir,
            on_progress=progress("transcribe"),
        )
        info["cached_stems"] = result.cached
    if on_step:
        on_step("arrange", 0.0)
    if postprocess is None:
        previous = pp.read_manifest(arrangement_dir(settings, track))
        postprocess = pp.PostprocessParams(**previous["params"]) if previous else None
    arrange(settings, track, postprocess)
    return result


def load_transcriptions(settings: Settings, track: Track) -> list[StemTranscription]:
    manifest = tr.read_manifest(midi_dir(settings, track))
    if manifest is None:
        raise PipelineError("not_transcribed", "Lance d'abord la transcription.", 409)
    params = tr.TranscribeParams(**manifest["params"])
    cache = settings.transcriptions_cache_dir / track.wav_sha256
    return [
        StemTranscription.load(
            cache / f"{tr.cache_key(s, params.engine_for(s), params.params_for(s))}.json"
        )
        for s in (entry["stem"] for entry in manifest["stems"])
    ]


def arrange(
    settings: Settings, track: Track, params: pp.PostprocessParams | None = None
) -> dict[str, object]:
    """Post-traitement seul : relit les transcriptions, sans relancer de modèle."""
    params = params or pp.PostprocessParams()
    with timed("arrange", track_id=track.id):
        grid = pp.load_beats(
            wav_path(settings, track), settings.analysis_cache_dir / track.wav_sha256
        )
        arrangements = pp.arrange(load_transcriptions(settings, track), grid, params)
        return pp.write_arrangements(arrangements, params, arrangement_dir(settings, track))
