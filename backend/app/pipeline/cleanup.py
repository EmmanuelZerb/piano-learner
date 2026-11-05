"""Nettoyage des notes brutes : tessiture, vélocité, doublons, notes trop courtes."""

from dataclasses import replace

from app.pipeline.notes import Note

A0, C8 = 21, 108


def fold_into_range(notes: list[Note], low: int = A0, high: int = C8) -> list[Note]:
    """Ramène à l'octave jouable les notes hors du clavier 88 touches."""

    def fold(pitch: int) -> int:
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        return pitch

    return [replace(n, pitch=fold(n.pitch)) if not low <= n.pitch <= high else n for n in notes]


def merge_duplicates(notes: list[Note], window: float) -> list[Note]:
    """Même hauteur attaquée à moins de `window` s d'écart (souvent deux stems qui jouent la
    même note) → une seule note. Un chevauchement plus tardif tronque la note précédente."""
    by_pitch: dict[int, list[Note]] = {}
    for n in sorted(notes, key=lambda n: (n.pitch, n.start)):
        group = by_pitch.setdefault(n.pitch, [])
        if group and n.start - group[-1].start <= window:
            prev = group[-1]
            group[-1] = replace(
                prev, end=max(prev.end, n.end), velocity=max(prev.velocity, n.velocity)
            )
        else:
            if group and n.start < group[-1].end:
                group[-1] = replace(group[-1], end=n.start)
            group.append(n)
    return sort_notes([n for group in by_pitch.values() for n in group])


def sort_notes(notes: list[Note]) -> list[Note]:
    return sorted(notes, key=lambda n: (n.start, n.pitch))


def clean(
    notes: list[Note], min_duration: float, min_velocity: int, merge_window: float
) -> list[Note]:
    loud = [n for n in notes if n.velocity >= min_velocity]
    merged = merge_duplicates(fold_into_range(loud), merge_window)
    return [n for n in merged if n.duration >= min_duration]
