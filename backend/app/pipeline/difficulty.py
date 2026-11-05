"""Niveaux de difficulté, dérivés de la transcription nettoyée et répartie entre les mains.

- Débutant : mélodie (voix supérieure, ou piste voix si transcrite) à droite, une note par
  main au plus ; à gauche, la fondamentale de chaque accord.
- Intermédiaire : accords de 3 notes au plus par main, rythme aimanté à la croche.
- Avancé : transcription complète nettoyée.
"""

from dataclasses import replace

from app.pipeline.cleanup import fold_into_range, sort_notes
from app.pipeline.hands import group_onsets
from app.pipeline.harmony import Chord
from app.pipeline.notes import Hand, Note
from app.pipeline.rhythm import BeatGrid, quantize

LEVELS = ("beginner", "intermediate", "advanced")
MELODY_RANGE = (60, 88)  # C4 à E6 : main droite confortable
BASS_RANGE = (43, 55)  # G2 à G3 : fondamentale main gauche
MIN_BEGINNER_NOTE_S = 0.12


def by_hand(notes: list[Note], hand: Hand) -> list[Note]:
    return [n for n in notes if n.hand == hand]


def cap_polyphony(notes: list[Note], cap: int, keep_high: bool) -> list[Note]:
    """Au plus `cap` notes tenues à la fois dans une main : les accords trop fournis perdent
    leurs voix intérieures, et les notes encore tenues sont coupées à l'attaque suivante."""
    out: list[Note] = []
    active: list[int] = []  # indices dans out
    for cluster in group_onsets(notes):
        # Ordre de priorité : voix extérieure de la main (haut à droite, bas à gauche),
        # puis l'autre extrémité, puis l'intérieur.
        ranked = sorted(cluster, key=lambda n: -n.pitch if keep_high else n.pitch)
        ranked = ranked[:1] + ranked[:0:-1] if len(ranked) > 1 else ranked
        chosen = ranked[:cap]
        start = min(n.start for n in chosen)
        active = [i for i in active if out[i].end > start]
        while len(active) + len(chosen) > cap:
            oldest = active.pop(0)
            out[oldest] = replace(out[oldest], end=start)
        for n in chosen:
            active.append(len(out))
            out.append(n)
    return [n for n in out if n.end - n.start > 1e-3]


def advanced(notes: list[Note]) -> list[Note]:
    return notes


def intermediate(notes: list[Note], grid: BeatGrid) -> list[Note]:
    simplified = quantize(notes, grid, "eighth", 1.0)
    right = cap_polyphony(by_hand(simplified, "R"), 3, keep_high=True)
    left = cap_polyphony(by_hand(simplified, "L"), 3, keep_high=False)
    return sort_notes(right + left)


def _shift_into(note: Note, low: int, high: int) -> Note:
    pitch = note.pitch
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return replace(note, pitch=pitch)


def beginner_melody(notes: list[Note], melody: list[Note] | None, grid: BeatGrid) -> list[Note]:
    source = melody if melody else by_hand(notes, "R")
    skyline = [max(c, key=lambda n: n.pitch) for c in group_onsets(source)]
    placed = [_shift_into(replace(n, hand="R"), *MELODY_RANGE) for n in skyline]
    single = cap_polyphony(quantize(placed, grid, "eighth", 1.0), 1, keep_high=True)
    return [n for n in single if n.duration >= MIN_BEGINNER_NOTE_S]


def beginner_bass(notes: list[Note], chords: list[Chord]) -> list[Note]:
    """Fondamentale de chaque accord détecté ; à défaut, note la plus grave de la main gauche."""
    left = by_hand(notes, "L")
    velocity = round(sum(n.velocity for n in left) / len(left)) if left else 70
    out: list[Note] = []
    for chord in chords:
        if chord.root is not None:
            pitch = BASS_RANGE[0] + (chord.root - BASS_RANGE[0]) % 12
        else:
            sounding = [n for n in left if n.start < chord.end and n.end > chord.start]
            if not sounding:
                continue
            pitch = _shift_into(min(sounding, key=lambda n: n.pitch), *BASS_RANGE).pitch
        out.append(Note(pitch, chord.start, chord.end, velocity, "L"))
    return cap_polyphony(out, 1, keep_high=False)


def beginner(
    notes: list[Note], grid: BeatGrid, chords: list[Chord], melody: list[Note] | None
) -> list[Note]:
    return sort_notes(beginner_melody(notes, melody, grid) + beginner_bass(notes, chords))


def build_levels(
    notes: list[Note], grid: BeatGrid, chords: list[Chord], melody: list[Note] | None
) -> dict[str, list[Note]]:
    melody = fold_into_range(melody) if melody else None
    return {
        "beginner": beginner(notes, grid, chords, melody),
        "intermediate": intermediate(notes, grid),
        "advanced": advanced(notes),
    }
