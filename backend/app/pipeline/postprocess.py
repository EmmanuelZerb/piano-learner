"""Post-traitement : transcriptions brutes → arrangements piano jouables (3 niveaux).

Ne relance aucun modèle : relit les JSON de transcription et la grille des temps (cache),
d'où une relance en quelques secondes avec d'autres paramètres.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.pipeline.cleanup import clean
from app.pipeline.difficulty import LEVELS, build_levels, by_hand
from app.pipeline.hands import split_hands
from app.pipeline.harmony import Chord, Key, detect_chords, detect_key
from app.pipeline.midi_io import write_arrangement_midi
from app.pipeline.notes import Note, Pedal, StemTranscription, max_polyphony
from app.pipeline.rhythm import BeatGrid, Division, detect_beats, quantize

MANIFEST = "manifest.json"
BEATS_FILE = "beats.json"


class PostprocessParams(BaseModel):
    quantize: Division = "sixteenth"
    quantize_strength: int = Field(50, ge=0, le=100)  # %
    min_note_ms: float = Field(60, ge=0, le=1000)
    min_velocity: int = Field(15, ge=1, le=127)
    merge_window_ms: float = Field(40, ge=0, le=200)
    split_point: int = Field(60, ge=36, le=84)  # 60 = do central
    dynamic_split: bool = True
    melody_from_vocals: bool = True  # si la voix est transcrite, elle donne la mélodie débutant


@dataclass
class Arrangement:
    level: str
    notes: list[Note]
    pedals: list[Pedal]
    grid: BeatGrid
    key: Key | None
    chords: list[Chord]

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "tempo": round(self.grid.tempo, 2),
            "beats": self.grid.to_dict()["beats"],
            "key": self.key.name if self.key else None,
            "chords": [[round(c.start, 4), round(c.end, 4), c.name] for c in self.chords],
            "pedals": [[round(p.start, 4), round(p.end, 4)] for p in self.pedals],
            "notes": [
                [n.pitch, round(n.start, 4), round(n.end, 4), n.velocity, n.hand]
                for n in self.notes
            ],
        }

    def summary(self) -> dict[str, object]:
        right, left = by_hand(self.notes, "R"), by_hand(self.notes, "L")
        return {
            "level": self.level,
            "right_notes": len(right),
            "left_notes": len(left),
            "max_polyphony_right": max_polyphony(right),
            "max_polyphony_left": max_polyphony(left),
        }


def load_beats(wav_path: Path, cache_dir: Path) -> BeatGrid:
    """Détection des temps (quelques secondes), mise en cache par morceau."""
    path = cache_dir / BEATS_FILE
    if path.exists():
        return BeatGrid.from_dict(json.loads(path.read_text(encoding="utf-8")))
    grid = detect_beats(wav_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grid.to_dict()), encoding="utf-8")
    return grid


def arrange(
    transcriptions: list[StemTranscription], grid: BeatGrid, params: PostprocessParams
) -> dict[str, Arrangement]:
    raw = [n for t in transcriptions for n in t.notes]
    cleaned = clean(
        raw,
        min_duration=params.min_note_ms / 1000,
        min_velocity=params.min_velocity,
        merge_window=params.merge_window_ms / 1000,
    )
    timed = quantize(cleaned, grid, params.quantize, params.quantize_strength / 100)
    notes = split_hands(timed, params.split_point, params.dynamic_split)

    vocals = next((t for t in transcriptions if t.stem == "vocals"), None)
    melody = None
    if params.melody_from_vocals and vocals and vocals.notes:
        melody = clean(vocals.notes, params.min_note_ms / 1000, params.min_velocity, 0.04)
    pedals = [p for t in transcriptions if t.stem == "piano" for p in t.pedals]

    key = detect_key(notes)
    end = max((n.end for n in notes), default=grid.beats[-1])
    chords = detect_chords(notes, grid, end)
    levels = build_levels(notes, grid, chords, melody)
    return {
        level: Arrangement(
            level, levels[level], [] if level == "beginner" else pedals, grid, key, chords
        )
        for level in LEVELS
    }


def write_arrangements(
    arrangements: dict[str, Arrangement], params: PostprocessParams, out_dir: Path
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for level, arrangement in arrangements.items():
        write_arrangement_midi(arrangement, out_dir / f"{level}.mid")
        (out_dir / f"{level}.json").write_text(json.dumps(arrangement.to_dict()), encoding="utf-8")
    any_arrangement = next(iter(arrangements.values()))
    manifest: dict[str, object] = {
        "params": params.model_dump(),
        "tempo": round(any_arrangement.grid.tempo, 1),
        "key": any_arrangement.key.name if any_arrangement.key else None,
        "chords": len([c for c in any_arrangement.chords if c.root is not None]),
        "levels": [a.summary() for a in arrangements.values()],
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def read_manifest(out_dir: Path) -> dict[str, object] | None:
    path = out_dir / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


Level = Literal["beginner", "intermediate", "advanced"]
