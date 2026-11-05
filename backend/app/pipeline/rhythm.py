"""Tempo, grille des temps et quantification.

Les temps détectés par librosa servent de grille : la quantification se fait en
« position de temps » (2,5 = au milieu du 3e temps), ce qui suit les variations de tempo.
"""

import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import numpy as np

from app.pipeline.notes import Note

Division = Literal["none", "eighth", "sixteenth", "triplet"]
SUBDIVISIONS: dict[str, int] = {"eighth": 2, "sixteenth": 4, "triplet": 3}

# Écart maximal toléré entre les temps détectés et une grille à tempo constant.
STEADY_TOLERANCE_S = 0.07


@dataclass(frozen=True)
class BeatGrid:
    tempo: float  # BPM
    beats: list[float]  # secondes, strictement croissants, au moins 2

    def to_dict(self) -> dict[str, object]:
        return {"tempo": self.tempo, "beats": [round(b, 4) for b in self.beats]}

    @classmethod
    def from_dict(cls, data: dict) -> "BeatGrid":
        return cls(float(data["tempo"]), [float(b) for b in data["beats"]])


def regular_grid(tempo: float, duration: float, offset: float = 0.0) -> BeatGrid:
    period = 60.0 / tempo
    count = max(2, math.ceil((duration - offset) / period) + 1)
    return BeatGrid(tempo, [offset + i * period for i in range(count)])


def regularize(grid: BeatGrid) -> BeatGrid:
    """Si le morceau est à tempo constant (cas de la plupart des prods), remplace les temps
    détectés (bruités de ±20 ms) par une droite ajustée : MIDI à tempo unique, plus lisible."""
    beats = np.asarray(grid.beats)
    k = np.arange(beats.size)
    period, offset = np.polyfit(k, beats, 1)
    fitted = offset + period * k
    if np.abs(beats - fitted).max() > STEADY_TOLERANCE_S:
        return grid
    return BeatGrid(60.0 / period, fitted.tolist())


def detect_beats(wav_path: Path) -> BeatGrid:
    import librosa

    y, sr = librosa.load(str(wav_path), sr=22050, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    beats = [float(b) for b in beats]
    bpm = float(np.atleast_1d(tempo)[0]) or 120.0
    if len(beats) < 4:  # silence ou signal sans pulsation : grille arbitraire
        return regular_grid(bpm, len(y) / sr)
    return regularize(BeatGrid(bpm, beats))


def beat_position(grid: BeatGrid, t: float) -> float:
    """Temps (s) → position en temps, extrapolée linéairement avant/après la grille."""
    b = grid.beats
    if t <= b[0]:
        return (t - b[0]) / (b[1] - b[0])
    if t >= b[-1]:
        return len(b) - 1 + (t - b[-1]) / (b[-1] - b[-2])
    return float(np.interp(t, b, np.arange(len(b))))


def position_to_time(grid: BeatGrid, pos: float) -> float:
    b = grid.beats
    if pos <= 0:
        return b[0] + pos * (b[1] - b[0])
    if pos >= len(b) - 1:
        return b[-1] + (pos - len(b) + 1) * (b[-1] - b[-2])
    return float(np.interp(pos, np.arange(len(b)), b))


def quantize(notes: list[Note], grid: BeatGrid, division: Division, strength: float) -> list[Note]:
    """Rapproche début et fin des notes de la grille, de `strength` (0 = rien, 1 = aimanté)."""
    if division == "none" or strength <= 0:
        return notes
    sub = SUBDIVISIONS[division]
    out = []
    for n in notes:
        start, end = beat_position(grid, n.start), beat_position(grid, n.end)
        q_start = start + strength * (round(start * sub) / sub - start)
        q_end = end + strength * (round(end * sub) / sub - end)
        if q_end - q_start < strength / sub:  # une note aimantée dure au moins une case
            q_end = q_start + max(end - start, strength / sub)
        out.append(
            replace(n, start=position_to_time(grid, q_start), end=position_to_time(grid, q_end))
        )
    return out
