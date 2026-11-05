"""Corrections manuelles d'un niveau (éditeur minimal).

Les corrections sont des opérations rejouées sur l'arrangement calculé (`{niveau}.base.json`).
Elles survivent donc à un recalcul du post-traitement tant que la note visée existe encore,
c'est-à-dire même hauteur, attaque à ±40 ms. Sinon la correction est ignorée et signalée.
"""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

EDITS_FILE = "edits.json"
MATCH_S = 0.04

RawNote = list  # [pitch, start, end, velocity, hand], format des JSON de niveau


class DeleteNote(BaseModel):
    op: Literal["delete"]
    pitch: int
    start: float


class ChangePitch(BaseModel):
    op: Literal["pitch"]
    pitch: int
    start: float
    new_pitch: int = Field(ge=21, le=108)


class ChangeHand(BaseModel):
    op: Literal["hand"]
    pitch: int
    start: float
    hand: Literal["L", "R"]


class SplitPassage(BaseModel):
    """Sur [start, end[, sous `split` → main gauche, à partir de `split` → main droite."""

    op: Literal["split"]
    start: float
    end: float
    split: int = Field(ge=21, le=108)


Edit = Annotated[DeleteNote | ChangePitch | ChangeHand | SplitPassage, Field(discriminator="op")]
EditList = TypeAdapter(list[Edit])


def _find(notes: list[RawNote], pitch: int, start: float) -> int | None:
    candidates = [
        (abs(n[1] - start), i)
        for i, n in enumerate(notes)
        if n[0] == pitch and abs(n[1] - start) <= MATCH_S
    ]
    return min(candidates)[1] if candidates else None


def apply_edits(notes: list[RawNote], edits: list[Edit]) -> tuple[list[RawNote], int]:
    """Applique les corrections dans l'ordre. Renvoie (notes, nombre de corrections ignorées)."""
    result = [list(n) for n in notes]
    unmatched = 0
    for edit in edits:
        if isinstance(edit, SplitPassage):
            for n in result:
                if edit.start <= n[1] < edit.end:
                    n[4] = "L" if n[0] < edit.split else "R"
            continue
        index = _find(result, edit.pitch, edit.start)
        if index is None:
            unmatched += 1
        elif isinstance(edit, DeleteNote):
            result.pop(index)
        elif isinstance(edit, ChangePitch):
            result[index][0] = edit.new_pitch
        else:
            result[index][4] = edit.hand
    result.sort(key=lambda n: (n[1], n[0]))
    return result, unmatched


def load_edits(out_dir: Path) -> dict[str, list[Edit]]:
    path = out_dir / EDITS_FILE
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {level: EditList.validate_python(edits) for level, edits in raw.items()}


def save_edits(out_dir: Path, edits: dict[str, list[Edit]]) -> None:
    data = {level: [e.model_dump() for e in items] for level, items in edits.items() if items}
    (out_dir / EDITS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
