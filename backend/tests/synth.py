"""Synthèse audio de test : notes de « piano » additif avec vérité terrain connue."""

from pathlib import Path

import numpy as np

SR = 44100
C_MAJOR_SCALE = [60, 62, 64, 65, 67, 69, 71, 72]


def midi_to_hz(pitch: float) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def piano_tone(pitch: int, duration: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Partiels légèrement inharmoniques (corde raide), aigus amortis plus vite, attaque bruitée."""
    t = np.arange(int(sr * duration)) / sr
    f0 = midi_to_hz(pitch)
    inharmonicity = 4e-4
    sig = np.zeros_like(t)
    for k in range(1, 16):
        fk = k * f0 * np.sqrt(1 + inharmonicity * k * k)
        if fk > sr / 2.2:
            break
        sig += np.sin(2 * np.pi * fk * t) / k**1.1 * np.exp(-(1.2 + 0.6 * k) * t)
    attack = np.random.default_rng(seed + pitch).normal(0, 0.3, t.size) * np.exp(-200 * t)
    release = np.clip((duration - t) / 0.03, 0, 1)  # étouffoir en fin de note
    return (sig + attack) * release


def render_notes(notes: list[tuple[int, float, float]], sr: int = SR) -> np.ndarray:
    """notes = [(pitch, start_s, end_s)] → signal mono normalisé."""
    total = max(end for _, _, end in notes) + 0.5
    out = np.zeros(int(sr * total))
    for pitch, start, end in notes:
        tone = piano_tone(pitch, end - start, sr)
        i = int(start * sr)
        out[i : i + tone.size] += tone
    return (0.8 * out / np.abs(out).max()).astype(np.float32)


def scale_notes(
    pitches: list[int] = C_MAJOR_SCALE, note_s: float = 0.5, gap_s: float = 0.05
) -> list[tuple[int, float, float]]:
    step = note_s + gap_s
    return [(p, 0.25 + i * step, 0.25 + i * step + note_s) for i, p in enumerate(pitches)]


SALAMANDER_URL = "https://tonejs.github.io/audio/salamander/{name}.mp3"
SALAMANDER_SAMPLES = {60: "C4", 63: "Ds4", 66: "Fs4", 69: "A4", 72: "C5"}


def download_salamander(dest: Path) -> dict[int, np.ndarray]:
    """Quelques échantillons du Salamander Grand Piano (CC-BY 3.0), utilisés aussi en phase 6."""
    import urllib.request

    import librosa

    dest.mkdir(parents=True, exist_ok=True)
    samples = {}
    for pitch, name in SALAMANDER_SAMPLES.items():
        path = dest / f"{name}.mp3"
        if not path.exists():
            urllib.request.urlretrieve(SALAMANDER_URL.format(name=name), path)
        samples[pitch] = librosa.load(str(path), sr=SR, mono=True)[0]
    return samples


def render_with_samples(
    notes: list[tuple[int, float, float]], samples: dict[int, np.ndarray], sr: int = SR
) -> np.ndarray:
    """Comme un sampler : échantillon le plus proche au-dessus, transposé vers le bas.

    Transposer vers le haut par rééchantillonnage fait apparaître des octaves fantômes
    chez ByteDance : on l'évite pour que le test mesure le modèle, pas le rendu.
    """
    import librosa

    out = np.zeros(int(sr * (max(e for _, _, e in notes) + 0.5)))
    for pitch, start, end in notes:
        base = min((p for p in samples if p >= pitch), default=max(samples))
        y = samples[base]
        if pitch != base:
            y = librosa.resample(y, orig_sr=sr * 2 ** ((pitch - base) / 12), target_sr=sr)
        y = y[: int((end - start) * sr)].copy()
        y *= np.clip((end - start - np.arange(y.size) / sr) / 0.05, 0, 1)
        out[int(start * sr) : int(start * sr) + y.size] += y
    return (0.8 * out / np.abs(out).max()).astype(np.float32)


def write_wav(path: Path, mono: np.ndarray, sr: int = SR) -> Path:
    import soundfile as sf

    sf.write(path, np.stack([mono, mono], axis=1), sr, subtype="PCM_16")
    return path


def note_f1(
    reference: list[tuple[int, float, float]],
    estimated: list[tuple[int, float, float]],
    onset_tolerance: float = 0.05,
) -> tuple[float, float, float]:
    """(précision, rappel, F1) au sens mir_eval : hauteur exacte + onset à ±50 ms."""
    import mir_eval

    def arrays(notes: list[tuple[int, float, float]]) -> tuple[np.ndarray, np.ndarray]:
        if not notes:
            return np.zeros((0, 2)), np.zeros(0)
        intervals = np.array([[s, e] for _, s, e in notes])
        return intervals, np.array([midi_to_hz(p) for p, _, _ in notes])

    ref_i, ref_p = arrays(reference)
    est_i, est_p = arrays(estimated)
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ref_i, ref_p, est_i, est_p, onset_tolerance=onset_tolerance, offset_ratio=None
    )
    return p, r, f
