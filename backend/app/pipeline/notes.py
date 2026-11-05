"""Représentation interne d'une transcription : notes + pédale, sérialisable en JSON.

C'est le format pivot du pipeline : la transcription le produit, le post-traitement
(phase 4) le relit sans relancer les modèles, et l'export MIDI en est dérivé.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Note:
    pitch: int  # numéro MIDI (21 = A0, 108 = C8)
    start: float  # secondes
    end: float
    velocity: int  # 1 à 127


@dataclass(frozen=True)
class Pedal:
    start: float
    end: float


@dataclass
class StemTranscription:
    stem: str
    engine: str
    params: dict[str, object]
    notes: list[Note] = field(default_factory=list)
    pedals: list[Pedal] = field(default_factory=list)

    def save(self, path: Path) -> None:
        data = {
            "stem": self.stem,
            "engine": self.engine,
            "params": self.params,
            "notes": [
                [n.pitch, round(n.start, 4), round(n.end, 4), n.velocity] for n in self.notes
            ],
            "pedals": [[round(p.start, 4), round(p.end, 4)] for p in self.pedals],
        }
        tmp = path.with_suffix(".part")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "StemTranscription":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            stem=data["stem"],
            engine=data["engine"],
            params=data["params"],
            notes=[Note(int(p), float(s), float(e), int(v)) for p, s, e, v in data["notes"]],
            pedals=[Pedal(float(s), float(e)) for s, e in data["pedals"]],
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
