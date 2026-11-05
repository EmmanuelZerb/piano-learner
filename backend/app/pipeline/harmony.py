"""Tonalité (profils de Krumhansl-Schmuckler) et noms d'accords par temps."""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from app.pipeline.notes import Note
from app.pipeline.rhythm import BeatGrid

NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Suffixe → intervalles. Les accords de 4 sons ont une petite pénalité : à score égal on
# préfère la triade, plus lisible.
CHORD_TEMPLATES: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "dim": (0, 3, 6),
    "sus4": (0, 5, 7),
}
NO_CHORD = "N"


@dataclass(frozen=True)
class Key:
    tonic: int  # classe de hauteur, 0 à 11
    mode: str  # "major" | "minor"

    @property
    def name(self) -> str:
        """Notation courte compatible avec les key_signature de mido : « Eb », « F#m »."""
        return NAMES[self.tonic] if self.mode == "major" else f"{MINOR_NAMES[self.tonic]}m"


@dataclass(frozen=True)
class Chord:
    start: float
    end: float
    name: str
    root: int | None  # classe de hauteur, None pour NO_CHORD


def pitch_class_weights(notes: list[Note], start: float = -1e9, end: float = 1e9) -> np.ndarray:
    """Poids de chaque classe de hauteur : durée de présence dans [start, end] x vélocité."""
    weights = np.zeros(12)
    for n in notes:
        overlap = min(n.end, end) - max(n.start, start)
        if overlap > 0:
            weights[n.pitch % 12] += overlap * n.velocity
    return weights


def detect_key(notes: list[Note]) -> Key | None:
    weights = pitch_class_weights(notes)
    if weights.sum() == 0:
        return None
    best: tuple[float, Key] | None = None
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            score = float(np.corrcoef(weights, np.roll(profile, tonic))[0, 1])
            if best is None or score > best[0]:
                best = (score, Key(tonic, mode))
    return best[1] if best else None


def name_chord(weights: np.ndarray, bass: int | None = None) -> tuple[str, int | None]:
    total = weights.sum()
    if total == 0:
        return NO_CHORD, None
    w = weights / total
    best = (-1e9, NO_CHORD, None)
    for root in range(12):
        for suffix, intervals in CHORD_TEMPLATES.items():
            tones = {(root + i) % 12 for i in intervals}
            score = sum(w[pc] for pc in tones) - 0.6 * sum(
                w[pc] for pc in range(12) if pc not in tones
            )
            score -= 0.05 * (len(intervals) - 3)
            if bass is not None and bass % 12 == root:
                score += 0.08
            if score > best[0]:
                name = (
                    MINOR_NAMES[root]
                    if suffix.startswith("m") and suffix != "maj7"
                    else NAMES[root]
                )
                best = (score, name + suffix, root)
    return (best[1], best[2]) if best[0] > 0.3 else (NO_CHORD, None)


def detect_chords(notes: list[Note], grid: BeatGrid, end_time: float) -> list[Chord]:
    """Un accord par temps, puis fusion des temps consécutifs portant le même accord."""
    bounds = [b for b in grid.beats if b < end_time] + [end_time]
    chords: list[Chord] = []
    for start, end in pairwise(bounds):
        sounding = [n for n in notes if n.start < end and n.end > start]
        bass = min((n.pitch for n in sounding), default=None)
        name, root = name_chord(pitch_class_weights(sounding, start, end), bass)
        if chords and chords[-1].name == name:
            chords[-1] = Chord(chords[-1].start, end, name, root)
        else:
            chords.append(Chord(start, end, name, root))
    return chords
