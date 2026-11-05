"""Export MusicXML d'un niveau (music21), pour l'ouvrir dans MuseScore.

Deux portées (main droite en clé de sol, main gauche en clé de fa), armure, tempo, 4/4.
Les positions sont exprimées en temps sur la grille détectée (comme le MIDI d'arrangement),
puis arrondies à la double croche : la partition reste lisible même si le niveau n'a pas
été quantifié. Les notes qui se chevauchent dans une main sont regroupées en accords liés.
"""

from fractions import Fraction
from pathlib import Path

from app.pipeline.midi_io import lead_beats
from app.pipeline.rhythm import BeatGrid, beat_position

GRID_DIVISOR = 4  # double croche
HANDS = (("R", "Main droite", "treble"), ("L", "Main gauche", "bass"))


def music21_key(name: str) -> str:
    """« Eb » → « E- » (majeur), « F#m » → « f# » (mineur, en minuscules pour music21)."""
    minor = name.endswith("m")
    tonic = (name[:-1] if minor else name).replace("b", "-")
    return tonic.lower() if minor else tonic


def _quarters(grid: BeatGrid, lead: int, t: float) -> Fraction:
    position = beat_position(grid, t) + lead
    return Fraction(max(0, round(position * GRID_DIVISOR)), GRID_DIVISOR)


def write_musicxml(level: dict, path: Path, title: str) -> None:
    from music21 import clef, key, metadata, meter, note, stream, tempo

    grid = BeatGrid(float(level["tempo"]), [float(b) for b in level["beats"]])
    lead = lead_beats(grid)
    score = stream.Score()
    score.metadata = metadata.Metadata(title=title)
    score.metadata.composer = "Transcription automatique (Piano Learner)"

    for hand, name, clef_name in HANDS:
        part = stream.Part()
        part.partName = name
        part.insert(0, clef.TrebleClef() if clef_name == "treble" else clef.BassClef())
        part.insert(0, meter.TimeSignature("4/4"))
        if level.get("key"):
            part.insert(0, key.Key(music21_key(level["key"])))
        if hand == "R":
            part.insert(0, tempo.MetronomeMark(number=round(float(level["tempo"]))))
        for pitch, start, end, velocity, note_hand in level["notes"]:
            if note_hand != hand:
                continue
            offset = _quarters(grid, lead, start)
            length = max(_quarters(grid, lead, end) - offset, Fraction(1, GRID_DIVISOR))
            n = note.Note(int(pitch), quarterLength=length)
            n.volume.velocity = int(velocity)
            part.insert(offset, n)
        if not part.notes:
            part.insert(0, note.Rest(quarterLength=4))
            score.insert(0, part)
            continue
        chorded = part.chordify(addTies=True)
        chorded.partName = name
        score.insert(0, chorded)

    tmp = path.with_suffix(".part")
    score.write("musicxml", fp=str(tmp))
    tmp.replace(path)
