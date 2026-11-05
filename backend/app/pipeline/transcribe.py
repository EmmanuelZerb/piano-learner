"""Transcription audio → notes : ByteDance pour le piano, Basic Pitch pour le reste.

Résultats mis en cache par (hash du WAV, stem, moteur, paramètres) : changer un seuil
ne relance que les stems concernés, et le post-traitement relit les JSON sans modèle.
"""

import contextlib
import hashlib
import io
import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.gpu import gpu_lock
from app.pipeline.midi_io import write_midi
from app.pipeline.notes import Note, Pedal, StemTranscription

Engine = Literal["bytedance", "basic_pitch"]
ProgressFn = Callable[[float], None]

BYTEDANCE_URL = "https://zenodo.org/records/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
BYTEDANCE_CHECKPOINT = "bytedance_piano_note_pedal.pth"

# Bornes de fréquence par stem pour Basic Pitch (évite les harmoniques prises pour des notes).
STEM_FREQ_RANGE: dict[str, tuple[float | None, float | None]] = {
    "bass": (None, 500.0),
}


class PianoParams(BaseModel):
    """Seuils du post-traitement ByteDance (valeurs par défaut de la bibliothèque)."""

    onset_threshold: float = Field(0.3, ge=0.05, le=0.95)
    offset_threshold: float = Field(0.3, ge=0.05, le=0.95)
    frame_threshold: float = Field(0.1, ge=0.05, le=0.95)


class BasicPitchParams(BaseModel):
    onset_threshold: float = Field(0.5, ge=0.05, le=0.95)
    frame_threshold: float = Field(0.3, ge=0.05, le=0.95)
    min_note_ms: float = Field(127.7, ge=10, le=1000)


class TranscribeParams(BaseModel):
    piano_engine: Engine = "bytedance"
    piano: PianoParams = PianoParams()
    basic_pitch: BasicPitchParams = BasicPitchParams()

    def engine_for(self, stem: str) -> Engine:
        return self.piano_engine if stem == "piano" else "basic_pitch"

    def params_for(self, stem: str) -> dict[str, object]:
        if self.engine_for(stem) == "bytedance":
            return self.piano.model_dump()
        low, high = STEM_FREQ_RANGE.get(stem, (None, None))
        return {**self.basic_pitch.model_dump(), "min_freq": low, "max_freq": high}


# --- Moteurs ------------------------------------------------------------------------------


def ensure_bytedance_checkpoint(models_dir: Path) -> Path:
    """La bibliothèque télécharge via `wget` (absent sous Windows) : on le fait nous-mêmes."""
    path = models_dir / BYTEDANCE_CHECKPOINT
    if not path.exists():
        models_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(BYTEDANCE_URL, tmp)
        tmp.replace(path)
    return path


@lru_cache(maxsize=1)
def _bytedance_model(checkpoint: str, device: str):  # type: ignore[no-untyped-def]
    from piano_transcription_inference import PianoTranscription

    with contextlib.redirect_stdout(io.StringIO()):  # la lib imprime sa configuration
        return PianoTranscription(device=device, checkpoint_path=checkpoint)


def run_bytedance(
    audio_path: Path, params: PianoParams, device: str, models_dir: Path
) -> tuple[list[Note], list[Pedal]]:
    import librosa
    from piano_transcription_inference import sample_rate

    model = _bytedance_model(str(ensure_bytedance_checkpoint(models_dir)), device)
    model.onset_threshold = params.onset_threshold
    model.offset_threshod = params.offset_threshold  # sic : faute de frappe dans la lib
    model.frame_threshold = params.frame_threshold
    audio, _ = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    with contextlib.redirect_stdout(io.StringIO()):
        result = model.transcribe(audio, None)
    notes = [
        Note(
            int(e["midi_note"]), float(e["onset_time"]), float(e["offset_time"]), int(e["velocity"])
        )
        for e in result["est_note_events"]
    ]
    pedals = [
        Pedal(float(e["onset_time"]), float(e["offset_time"])) for e in result["est_pedal_events"]
    ]
    return notes, pedals


@lru_cache(maxsize=1)
def _basic_pitch_model():  # type: ignore[no-untyped-def]
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model

    return Model(ICASSP_2022_MODEL_PATH)


def run_basic_pitch(audio_path: Path, params: dict[str, object]) -> list[Note]:
    from basic_pitch.inference import predict

    with contextlib.redirect_stdout(io.StringIO()):
        _, _, events = predict(
            audio_path,
            _basic_pitch_model(),
            onset_threshold=float(params["onset_threshold"]),  # type: ignore[arg-type]
            frame_threshold=float(params["frame_threshold"]),  # type: ignore[arg-type]
            minimum_note_length=float(params["min_note_ms"]),  # type: ignore[arg-type]
            minimum_frequency=params["min_freq"],  # type: ignore[arg-type]
            maximum_frequency=params["max_freq"],  # type: ignore[arg-type]
        )
    notes = [
        Note(int(pitch), float(start), float(end), max(1, min(127, round(float(amp) * 127))))
        for start, end, pitch, amp, _ in events
    ]
    return sorted(notes, key=lambda n: (n.start, n.pitch))


def transcribe_stem(
    stem: str, audio_path: Path, params: TranscribeParams, device: str, models_dir: Path
) -> StemTranscription:
    engine = params.engine_for(stem)
    engine_params = params.params_for(stem)
    if engine == "bytedance":
        with gpu_lock:
            notes, pedals = run_bytedance(audio_path, params.piano, device, models_dir)
    else:
        notes, pedals = run_basic_pitch(audio_path, engine_params), []
    return StemTranscription(stem, engine, engine_params, notes, pedals)


# --- Orchestration et cache ---------------------------------------------------------------


MANIFEST = "manifest.json"
MERGED = "merged"


@dataclass(frozen=True)
class TranscriptionResult:
    stems: dict[str, Path]  # stem → JSON de notes en cache
    midi: dict[str, Path]  # stem → .mid ; clé MERGED pour le fichier fusionné
    cached: list[str]
    elapsed_s: float
    manifest: dict[str, object]


def read_manifest(out_dir: Path) -> dict[str, object] | None:
    path = out_dir / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def cache_key(stem: str, engine: str, engine_params: dict[str, object]) -> str:
    raw = json.dumps({"engine": engine, "params": engine_params}, sort_keys=True)
    return f"{stem}-{engine}-{hashlib.sha1(raw.encode()).hexdigest()[:10]}"


def transcribe_stems(
    stem_paths: dict[str, Path],
    stems: list[str],
    params: TranscribeParams,
    cache_dir: Path,
    out_dir: Path,
    device: str,
    models_dir: Path,
    on_progress: ProgressFn | None = None,
) -> TranscriptionResult:
    """Transcrit chaque stem demandé (ou le relit du cache) puis écrit les MIDI dans out_dir."""
    start = time.perf_counter()
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    jsons: dict[str, Path] = {}
    cached: list[str] = []
    transcriptions: list[StemTranscription] = []
    for i, stem in enumerate(stems):
        if on_progress:  # aussi un point d'annulation avant chaque stem
            on_progress(i / len(stems))
        key = cache_key(stem, params.engine_for(stem), params.params_for(stem))
        path = cache_dir / f"{key}.json"
        if path.exists():
            transcription = StemTranscription.load(path)
            cached.append(stem)
        else:
            transcription = transcribe_stem(stem, stem_paths[stem], params, device, models_dir)
            transcription.save(path)
        jsons[stem] = path
        transcriptions.append(transcription)
        if on_progress:
            on_progress((i + 1) / len(stems))

    for old in out_dir.glob(
        "*.mid"
    ):  # une sélection plus courte ne doit pas laisser d'anciens MIDI
        old.unlink()
    midi = {t.stem: out_dir / f"{t.stem}.mid" for t in transcriptions}
    for t in transcriptions:
        write_midi([t], midi[t.stem])
    midi[MERGED] = out_dir / f"{MERGED}.mid"
    write_midi(transcriptions, midi[MERGED])

    elapsed = time.perf_counter() - start
    manifest: dict[str, object] = {
        "params": params.model_dump(),
        "elapsed_s": round(elapsed, 1),
        "stems": [
            {
                "stem": t.stem,
                "engine": t.engine,
                "notes": len(t.notes),
                "pedals": len(t.pedals),
                "cached": t.stem in cached,
            }
            for t in transcriptions
        ],
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return TranscriptionResult(jsons, midi, cached, elapsed, manifest)
