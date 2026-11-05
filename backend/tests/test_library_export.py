import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.pipeline import postprocess as pp
from app.pipeline.edits import ChangeHand, ChangePitch, DeleteNote, SplitPassage, apply_edits
from app.pipeline.harmony import Chord, Key
from app.pipeline.notation import music21_key, write_musicxml
from app.pipeline.notes import Note
from app.pipeline.rhythm import regular_grid
from tests.conftest import AudioFactory, requires_ffmpeg

NOTES = [
    [60, 0.0, 0.5, 80, "R"],
    [64, 0.0, 0.5, 80, "R"],
    [48, 0.0, 1.0, 70, "L"],
    [62, 0.5, 1.0, 80, "R"],
    [55, 1.0, 2.0, 70, "R"],
]


# --- Corrections ----------------------------------------------------------------------------


def test_apply_edits() -> None:
    edits = [
        DeleteNote(op="delete", pitch=64, start=0.01),  # tolérance de 40 ms
        ChangePitch(op="pitch", pitch=62, start=0.5, new_pitch=74),
        ChangeHand(op="hand", pitch=48, start=0.0, hand="R"),
        DeleteNote(op="delete", pitch=99, start=0.0),  # introuvable
    ]
    notes, unmatched = apply_edits(NOTES, edits)
    assert unmatched == 1
    assert [(n[0], n[4]) for n in notes] == [(48, "R"), (60, "R"), (74, "R"), (55, "R")]
    assert NOTES[1][0] == 64  # l'original n'est pas modifié


def test_split_passage_only_affects_its_range() -> None:
    notes, _ = apply_edits(NOTES, [SplitPassage(op="split", start=0.9, end=1.5, split=60)])
    hands = {(n[0], n[1]): n[4] for n in notes}
    assert hands[(55, 1.0)] == "L"  # dans le passage, sous le point de partage
    assert hands[(48, 0.0)] == "L" and hands[(60, 0.0)] == "R"  # hors passage : inchangé


@pytest.mark.parametrize(
    ("name", "expected"), [("C", "C"), ("Eb", "E-"), ("F#m", "f#"), ("Bbm", "b-"), ("Am", "a")]
)
def test_music21_key(name: str, expected: str) -> None:
    assert music21_key(name) == expected


# --- MusicXML -------------------------------------------------------------------------------


def _level(notes: list = NOTES, key: str | None = "Eb") -> dict:
    return {
        "level": "advanced",
        "tempo": 120,
        "beats": [i * 0.5 for i in range(20)],
        "key": key,
        "chords": [],
        "pedals": [],
        "notes": notes,
    }


def test_musicxml_has_two_staves_key_and_chords(tmp_path: Path) -> None:
    from music21 import converter

    path = tmp_path / "level.musicxml"
    write_musicxml(_level(), path, "Mon morceau")
    score = converter.parse(str(path))
    assert score.metadata.bestTitle == "Mon morceau"
    right, left = score.parts
    assert (right.partName, left.partName) == ("Main droite", "Main gauche")
    assert right.flatten().keySignature.sharps == -3  # mi bémol majeur
    first_chord = right.flatten().notes[0]
    assert sorted(p.midi for p in first_chord.pitches) == [60, 64]
    assert [p.midi for p in left.flatten().notes[0].pitches] == [48]


def test_musicxml_with_empty_hand_and_no_key(tmp_path: Path) -> None:
    from music21 import converter

    path = tmp_path / "level.musicxml"
    write_musicxml(_level([[72, 0.0, 0.5, 80, "R"]], key=None), path, "Solo")
    score = converter.parse(str(path))
    assert len(score.parts) == 2
    assert not score.parts[1].flatten().notes


# --- API ------------------------------------------------------------------------------------


def _arranged_track(client: TestClient, settings: Settings, make_audio: AudioFactory) -> str:
    """Morceau importé + niveaux écrits directement (sans séparation ni transcription)."""
    with make_audio("a.mp3").open("rb") as f:
        track_id = client.post("/tracks/upload", files={"file": ("a.mp3", f)}).json()["track"]["id"]
    notes = [Note(p, s, e, v, h) for p, s, e, v, h in NOTES]
    grid = regular_grid(120, 4)
    arrangements = {
        level: pp.Arrangement(level, notes, [], grid, Key(3, "major"), [Chord(0, 1, "Eb", 3)])
        for level in pp.LEVELS
    }
    pp.write_arrangements(
        arrangements, pp.PostprocessParams(), settings.tracks_dir / track_id / "arrangement"
    )
    return track_id


@requires_ffmpeg
def test_edits_api(client: TestClient, settings: Settings, make_audio: AudioFactory) -> None:
    track_id = _arranged_track(client, settings, make_audio)
    url = f"/tracks/{track_id}/arrangement/advanced/edits"

    res = client.post(url, json={"edits": [{"op": "delete", "pitch": 64, "start": 0.0}]})
    assert res.status_code == 200
    advanced = res.json()["levels"][2]
    assert (advanced["right_notes"], advanced["edits"]) == (3, 1)
    assert res.json()["levels"][0]["edits"] == 0  # les autres niveaux ne bougent pas

    client.post(url, json={"edits": [{"op": "hand", "pitch": 55, "start": 1.0, "hand": "L"}]})
    level = client.get(f"/tracks/{track_id}/arrangement/advanced.json").json()
    assert [n[0] for n in level["notes"] if n[4] == "L"] == [48, 55]
    assert len(client.get(url).json()) == 2

    undo = client.delete(f"{url}?last=true").json()["levels"][2]
    assert (undo["edits"], undo["left_notes"]) == (1, 1)
    assert client.delete(url).json()["levels"][2]["right_notes"] == 4

    bad = {"edits": [{"op": "pitch", "pitch": 60, "start": 0, "new_pitch": 200}]}
    assert client.post(url, json=bad).status_code == 422
    assert (
        client.post(f"/tracks/{track_id}/arrangement/expert/edits", json={"edits": []}).status_code
        == 404
    )
    assert client.get(f"/tracks/{track_id}/arrangement/advanced.base.json").status_code == 404


@requires_ffmpeg
def test_edits_survive_rearrangement(
    client: TestClient, settings: Settings, make_audio: AudioFactory
) -> None:
    track_id = _arranged_track(client, settings, make_audio)
    url = f"/tracks/{track_id}/arrangement/beginner/edits"
    client.post(url, json={"edits": [{"op": "delete", "pitch": 60, "start": 0.0}]})
    _arranged_track_again = settings.tracks_dir / track_id / "arrangement"
    # Recalcul du post-traitement : la base est réécrite, la correction est rejouée.
    pp.write_arrangements(
        {
            lvl: pp.Arrangement.from_dict(
                json.loads((_arranged_track_again / f"{lvl}.base.json").read_text())
            )
            for lvl in pp.LEVELS
        },
        pp.PostprocessParams(),
        _arranged_track_again,
    )
    beginner = client.get(f"/tracks/{track_id}/arrangement").json()["levels"][0]
    assert (beginner["edits"], beginner["unmatched_edits"], beginner["right_notes"]) == (1, 0, 3)


@requires_ffmpeg
def test_musicxml_export_endpoint(
    client: TestClient, settings: Settings, make_audio: AudioFactory
) -> None:
    track_id = _arranged_track(client, settings, make_audio)
    arrangement = client.get(f"/tracks/{track_id}/arrangement").json()
    url = arrangement["levels"][1]["musicxml_url"]
    res = client.get(url)
    assert res.status_code == 200
    assert b"<score-partwise" in res.content
    assert "attachment" in res.headers["content-disposition"]
    cached = settings.tracks_dir / track_id / "arrangement" / "intermediate.musicxml"
    assert cached.exists()
    # Une correction invalide la partition, régénérée à la demande suivante.
    client.post(
        f"/tracks/{track_id}/arrangement/intermediate/edits",
        json={"edits": [{"op": "delete", "pitch": 60, "start": 0.0}]},
    )
    assert not cached.exists()
    assert client.get(url).status_code == 200
    assert client.get(f"/tracks/{track_id}/export/expert.musicxml").status_code == 404


@requires_ffmpeg
def test_library_reports_stage_and_progress(
    client: TestClient, settings: Settings, make_audio: AudioFactory
) -> None:
    with make_audio("plain.mp3", freq=330).open("rb") as f:
        plain_id = client.post("/tracks/upload", files={"file": ("plain.mp3", f)}).json()["track"][
            "id"
        ]
    track_id = _arranged_track(client, settings, make_audio)
    session = {
        "level": "beginner",
        "mode": "wait",
        "hands": "R",
        "speed": 1,
        "hits": 9,
        "wrongs": 1,
        "misses": 0,
        "duration_s": 60,
    }
    client.post(f"/tracks/{track_id}/practice", json=session)
    client.post(
        f"/tracks/{track_id}/practice",
        json={**session, "hits": 5, "wrongs": 5, "level": "advanced"},
    )

    items = {item["id"]: item for item in client.get("/library").json()}
    arranged, plain = items[track_id], items[plain_id]
    assert arranged["stage"] == "arranged"
    assert arranged["levels"] == ["beginner", "intermediate", "advanced"]
    assert (arranged["sessions"], arranged["best_accuracy"], arranged["practice_seconds"]) == (
        2,
        0.9,
        120.0,
    )
    assert arranged["last_level"] == "advanced"
    assert (plain["stage"], plain["sessions"], plain["best_accuracy"]) == ("imported", 0, None)
    assert plain["active_job"] is None
