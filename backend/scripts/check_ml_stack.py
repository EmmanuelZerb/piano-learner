"""Vérifie que la stack ML cohabite dans le venv : imports, GPU, et (option --models)
une mini-inférence de chaque modèle sur un signal synthétique.

Usage : uv run python scripts/check_ml_stack.py [--models]
"""

import argparse
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path

import numpy as np

SR = 44100


def sine_scale(sr: int, seconds_per_note: float = 0.5) -> np.ndarray:
    """Gamme de do majeur (C4→C5) en sinusoïdes avec harmoniques, mono float32."""
    midi_notes = [60, 62, 64, 65, 67, 69, 71, 72]
    t = np.arange(int(sr * seconds_per_note)) / sr
    envelope = np.exp(-3 * t)
    chunks = []
    for note in midi_notes:
        f = 440.0 * 2 ** ((note - 69) / 12)
        tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3))
        chunks.append(0.3 * envelope * tone)
    return np.concatenate(chunks).astype(np.float32)


def check_torch() -> str:
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    x = torch.randn(1024, 1024, device=device)
    _ = (x @ x).sum().item()
    name = torch.cuda.get_device_name(0) if device == "cuda" else "CPU"
    return f"torch {torch.__version__}, device={device} ({name})"


ML_PACKAGES = {
    "numpy": "numpy",
    "librosa": "librosa",
    "demucs": "demucs",
    "basic_pitch": "basic-pitch",
    "piano_transcription_inference": "piano-transcription-inference",
    "pretty_midi": "pretty-midi",
    "mido": "mido",
    "soundfile": "soundfile",
    "onnxruntime": "onnxruntime",
}


def check_imports() -> str:
    import importlib
    from importlib.metadata import version

    for module in ML_PACKAGES:
        importlib.import_module(module)
    return ", ".join(f"{dist} {version(dist)}" for dist in ML_PACKAGES.values())


def check_demucs() -> str:
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model("htdemucs_6s")
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mono = torch.from_numpy(sine_scale(model.samplerate))
    mix = torch.stack([mono, mono])[None]
    with torch.no_grad():
        out = apply_model(model, mix, device=device, split=True, progress=False)
    return f"sources={model.sources}, sortie={tuple(out.shape)}"


def check_basic_pitch(wav_path: Path) -> str:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    _, _, notes = predict(wav_path, ICASSP_2022_MODEL_PATH)
    pitches = sorted({int(n[2]) for n in notes})
    model = Path(str(ICASSP_2022_MODEL_PATH)).name
    return f"modèle={model}, {len(notes)} notes, hauteurs={pitches}"


def check_bytedance(wav_path: Path) -> str:
    import librosa
    import torch
    from piano_transcription_inference import PianoTranscription, sample_rate

    from app.config import get_settings
    from app.pipeline.transcribe import ensure_bytedance_checkpoint

    audio, _ = librosa.load(str(wav_path), sr=sample_rate, mono=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    checkpoint = ensure_bytedance_checkpoint(get_settings().models_dir)
    transcriptor = PianoTranscription(device=device, checkpoint_path=str(checkpoint))
    midi_out = wav_path.with_suffix(".mid")
    result = transcriptor.transcribe(audio, str(midi_out))
    events = result["est_note_events"]
    pitches = sorted({int(e["midi_note"]) for e in events})
    return f"{len(events)} notes, hauteurs={pitches}"


def run(name: str, fn: Callable[[], str]) -> bool:
    start = time.perf_counter()
    try:
        detail = fn()
    except Exception:
        print(f"[ÉCHEC] {name}")
        traceback.print_exc()
        return False
    print(f"[OK]    {name} ({time.perf_counter() - start:.1f}s) : {detail}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true", help="télécharge et teste les modèles")
    args = parser.parse_args()
    from app.config import get_settings
    from app.system import use_project_model_caches

    use_project_model_caches(get_settings().models_dir)

    ok = run("imports", check_imports) and run("torch", check_torch)
    if ok and args.models:
        import soundfile as sf

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "scale.wav"
            sf.write(wav, sine_scale(SR), SR)
            ok = run("demucs htdemucs_6s", check_demucs) and ok
            ok = run("basic-pitch", lambda: check_basic_pitch(wav)) and ok
            ok = run("piano_transcription_inference", lambda: check_bytedance(wav)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
