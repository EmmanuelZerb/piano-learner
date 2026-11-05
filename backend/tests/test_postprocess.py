import random
from pathlib import Path

import mido
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.pipeline import postprocess as pp
from app.pipeline.cleanup import clean, fold_into_range, merge_duplicates
from app.pipeline.difficulty import build_levels, by_hand, cap_polyphony
from app.pipeline.hands import group_onsets, split_hands
from app.pipeline.harmony import Chord, Key, detect_chords, detect_key, name_chord
from app.pipeline.midi_io import PPQ, write_arrangement_midi
from app.pipeline.notes import Note, StemTranscription, max_polyphony
from app.pipeline.rhythm import (
    BeatGrid,
    beat_position,
    detect_beats,
    position_to_time,
    quantize,
    regular_grid,
    regularize,
)
from tests.conftest import AudioFactory, requires_ffmpeg
from tests.synth import SR, write_wav

GRID_120 = regular_grid(120, 20)  # un temps toutes les 0,5 s


def n(pitch: int, start: float, end: float, velocity: int = 80, hand=None) -> Note:
    return Note(pitch, start, end, velocity, hand)


def random_notes(seed: int, count: int = 300) -> list[Note]:
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        start = round(rng.uniform(0, 15), 2)
        out.append(
            n(rng.randint(36, 90), start, start + rng.uniform(0.1, 1.5), rng.randint(30, 110))
        )
    return out


# --- Nettoyage ------------------------------------------------------------------------------


def test_fold_into_range() -> None:
    folded = fold_into_range([n(110, 0, 1), n(15, 0, 1), n(60, 0, 1)])
    assert [x.pitch for x in folded] == [98, 27, 60]


def test_merge_duplicates() -> None:
    merged = merge_duplicates([n(60, 0.0, 0.5, 60), n(60, 0.02, 0.8, 90)], window=0.04)
    assert merged == [n(60, 0.0, 0.8, 90)]
    truncated = merge_duplicates([n(60, 0.0, 1.0), n(60, 0.5, 0.9)], window=0.04)
    assert [(x.start, x.end) for x in truncated] == [(0.0, 0.5), (0.5, 0.9)]


def test_clean_filters_velocity_and_short_notes() -> None:
    notes = [n(60, 0, 1, velocity=5), n(62, 0, 0.03), n(64, 0, 1)]
    assert [x.pitch for x in clean(notes, 0.06, 15, 0.04)] == [64]


# --- Rythme ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("division", "strength", "expected"),
    [
        ("sixteenth", 0.0, 0.13),
        ("sixteenth", 1.0, 0.125),
        ("sixteenth", 0.5, 0.1275),
        ("eighth", 1.0, 0.25),
        ("triplet", 1.0, 1 / 6),
        ("none", 1.0, 0.13),
    ],
)
def test_quantize_start(division, strength, expected) -> None:
    (q,) = quantize([n(60, 0.13, 0.6)], GRID_120, division, strength)
    assert q.start == pytest.approx(expected)


def test_quantize_keeps_notes_at_least_one_step() -> None:
    (q,) = quantize([n(60, 0.26, 0.27)], GRID_120, "eighth", 1.0)
    assert q.end - q.start == pytest.approx(0.25)


def test_beat_position_round_trip_with_tempo_change() -> None:
    grid = BeatGrid(100, [0.4, 1.0, 1.6, 2.1, 2.6])
    for t in (0.0, 0.7, 1.9, 3.5):
        assert position_to_time(grid, beat_position(grid, t)) == pytest.approx(t)


def test_regularize() -> None:
    rng = np.random.default_rng(0)
    jittered = BeatGrid(119, (0.3 + 0.5 * np.arange(40) + rng.normal(0, 0.01, 40)).tolist())
    steady = regularize(jittered)
    assert steady.tempo == pytest.approx(120, abs=0.5)
    accelerating = BeatGrid(100, np.cumsum(np.linspace(0.6, 0.4, 40)).tolist())
    assert regularize(accelerating) == accelerating


def test_detect_beats_on_click_track(tmp_path: Path) -> None:
    pytest.importorskip("librosa")
    click = np.zeros(SR * 12)
    for t in np.arange(0.25, 12, 0.5):  # 120 BPM
        i = int(t * SR)
        click[i : i + 400] += np.sin(2 * np.pi * 1000 * np.arange(400) / SR) * np.hanning(400)
    grid = detect_beats(write_wav(tmp_path / "click.wav", click.astype(np.float32)))
    assert grid.tempo == pytest.approx(120, rel=0.02)


# --- Mains ----------------------------------------------------------------------------------


def test_bass_and_melody_are_split() -> None:
    notes = [n(p, i * 0.5, i * 0.5 + 0.4) for i, p in enumerate([36, 40, 43, 36])]
    notes += [n(p, i * 0.5, i * 0.5 + 0.4) for i, p in enumerate([72, 76, 79, 84])]
    hands = split_hands(notes)
    assert all(x.hand == ("L" if x.pitch < 60 else "R") for x in hands)


def test_wide_chord_keeps_bass_in_left_hand() -> None:
    hands = {x.pitch: x.hand for x in split_hands([n(p, 0, 1) for p in (36, 60, 64, 67, 76)])}
    assert hands == {36: "L", 60: "R", 64: "R", 67: "R", 76: "R"}


def test_split_follows_register() -> None:
    notes = [n(p, i * 0.5, i * 0.5 + 0.4) for i, p in enumerate([62, 64, 65, 67] * 3)]
    notes += [n(p, i * 0.5, i * 0.5 + 0.4) for i, p in enumerate([79, 81, 83, 84] * 3)]
    hands = split_hands(notes)
    assert all(x.hand == ("L" if x.pitch < 70 else "R") for x in hands)


@pytest.mark.parametrize("seed", range(5))
def test_hands_never_cross_within_a_chord(seed: int) -> None:
    for cluster in group_onsets(split_hands(random_notes(seed))):
        left = [x.pitch for x in cluster if x.hand == "L"]
        right = [x.pitch for x in cluster if x.hand == "R"]
        if left and right:
            assert max(left) <= min(right)


# --- Harmonie -------------------------------------------------------------------------------


def test_detect_key() -> None:
    c_major = [n(p, i, i + 1) for i, p in enumerate([60, 62, 64, 65, 67, 69, 71, 72, 67, 60])]
    assert detect_key(c_major) == Key(0, "major")
    a_minor = [n(p, i, i + 1) for i, p in enumerate([57, 59, 60, 62, 64, 65, 68, 69, 64, 57])]
    assert detect_key(a_minor).name == "Am"


@pytest.mark.parametrize(
    ("pitches", "name"),
    [([60, 64, 67], "C"), ([57, 60, 64], "Am"), ([55, 59, 62, 65], "G7"), ([], "N")],
)
def test_name_chord(pitches: list[int], name: str) -> None:
    weights = np.zeros(12)
    for p in pitches:
        weights[p % 12] += 1
    assert name_chord(weights, min(pitches, default=None))[0] == name


def test_detect_chords_merges_beats() -> None:
    notes = [n(p, 0, 1.0) for p in (48, 60, 64, 67)] + [n(p, 1.0, 2.0) for p in (53, 60, 65, 69)]
    chords = detect_chords(notes, GRID_120, 2.0)
    assert [(c.start, c.end, c.name) for c in chords] == [(0, 1.0, "C"), (1.0, 2.0, "F")]


# --- Niveaux --------------------------------------------------------------------------------


def test_cap_polyphony_keeps_outer_voices() -> None:
    chord = [n(p, 0, 1, hand="R") for p in (60, 64, 67, 72)]
    assert sorted(x.pitch for x in cap_polyphony(chord, 3, keep_high=True)) == [60, 64, 72]
    assert sorted(x.pitch for x in cap_polyphony(chord, 1, keep_high=True)) == [72]


@pytest.mark.parametrize("seed", range(10))
def test_level_polyphony_limits(seed: int) -> None:
    notes = split_hands(random_notes(seed))
    chords = detect_chords(notes, GRID_120, 17)
    levels = build_levels(notes, GRID_120, chords, melody=None)
    for hand in ("L", "R"):
        assert max_polyphony(by_hand(levels["beginner"], hand)) <= 2  # critère : jamais plus de 2
        assert max_polyphony(by_hand(levels["beginner"], hand)) <= 1  # en pratique : 1
        assert max_polyphony(by_hand(levels["intermediate"], hand)) <= 3
    assert levels["advanced"] == notes
    assert by_hand(levels["beginner"], "R") and by_hand(levels["beginner"], "L")


def test_beginner_uses_vocal_melody_and_chord_roots() -> None:
    accompaniment = split_hands([n(p, 0, 2) for p in (48, 55, 64, 67, 72)])
    melody = [n(p, i * 0.5, i * 0.5 + 0.45) for i, p in enumerate([52, 55, 57, 59])]
    chords = [Chord(0, 2, "C", 0)]
    beginner = build_levels(accompaniment, GRID_120, chords, melody)["beginner"]
    assert [x.pitch for x in by_hand(beginner, "R")] == [64, 67, 69, 71]  # remontée d'une octave
    assert [(x.pitch, x.start, x.end) for x in by_hand(beginner, "L")] == [(48, 0, 2)]


# --- Export et orchestration ----------------------------------------------------------------


def _arrangement(grid: BeatGrid) -> pp.Arrangement:
    notes = [n(60, 0.3, 0.8, hand="R"), n(48, 0.3, 1.3, hand="L"), n(64, 0.8, 1.3, hand="R")]
    return pp.Arrangement("advanced", notes, [], grid, Key(0, "major"), [Chord(0.3, 1.3, "C", 0)])


def test_arrangement_midi_structure(tmp_path: Path) -> None:
    grid = BeatGrid(120, [0.3 + 0.5 * i for i in range(10)])
    write_arrangement_midi(_arrangement(grid), tmp_path / "a.mid")
    midi = mido.MidiFile(tmp_path / "a.mid")
    names = [next(m.name for m in t if m.type == "track_name") for t in midi.tracks]
    assert names == ["Tempo", "Main droite", "Main gauche"]
    tempos = [m.tempo for m in midi.tracks[0] if m.type == "set_tempo"]
    assert tempos == [500000]
    assert any(m.type == "key_signature" and m.key == "C" for m in midi.tracks[0])

    def note_ticks(track: mido.MidiTrack) -> list[tuple[int, int]]:
        tick, out = 0, []
        for m in track:
            tick += m.time
            if m.type == "note_on":
                out.append((m.note, tick))
        return out

    # Premier temps détecté (0,3 s) → tick d'un temps entier (un temps de levée ajouté).
    assert note_ticks(midi.tracks[1]) == [(60, PPQ), (64, 2 * PPQ)]
    assert {m.channel for m in midi.tracks[2] if m.type == "note_on"} == {1}


def test_arrange_produces_three_levels(tmp_path: Path) -> None:
    rng = random.Random(1)
    piano = StemTranscription("piano", "fake", {}, random_notes(1, 120))
    other = StemTranscription(
        "other", "fake", {}, [n(rng.randint(48, 80), i * 0.25, i * 0.25 + 0.2) for i in range(40)]
    )
    params = pp.PostprocessParams()
    arrangements = pp.arrange([piano, other], GRID_120, params)
    manifest = pp.write_arrangements(arrangements, params, tmp_path)
    assert [lvl["level"] for lvl in manifest["levels"]] == ["beginner", "intermediate", "advanced"]
    beginner = manifest["levels"][0]
    assert beginner["max_polyphony_right"] <= 2 and beginner["max_polyphony_left"] <= 2
    for level in pp.LEVELS:
        assert mido.MidiFile(tmp_path / f"{level}.mid").type == 1
        assert (tmp_path / f"{level}.json").exists()


@requires_ffmpeg
def test_arrangement_api_flow(
    client: TestClient, make_audio: AudioFactory, fake_model, monkeypatch: pytest.MonkeyPatch
):
    import app.pipeline.transcribe as tr

    def fake(stem, audio_path, params, device, models_dir):  # type: ignore[no-untyped-def]
        notes = random_notes(len(stem), 60)
        return StemTranscription(stem, params.engine_for(stem), params.params_for(stem), notes)

    monkeypatch.setattr(tr, "transcribe_stem", fake)
    with make_audio("s.mp3", seconds=3).open("rb") as f:
        track = client.post("/tracks/upload", files={"file": ("s.mp3", f)}).json()["track"]
    base = f"/tracks/{track['id']}"

    assert client.post(f"{base}/arrange", json={}).status_code == 409
    assert client.get(f"{base}/arrangement").json()["available"] is False

    client.post(f"{base}/transcribe", json={})  # génère aussi les niveaux
    auto = client.get(f"{base}/arrangement").json()
    assert auto["available"] and len(auto["levels"]) == 3

    res = client.post(f"{base}/arrange", json={"quantize": "none", "split_point": 55})
    assert res.status_code == 200
    body = res.json()
    assert body["params"]["split_point"] == 55
    beginner = body["levels"][0]
    assert beginner["max_polyphony_right"] <= 2 and beginner["max_polyphony_left"] <= 2

    notes = client.get(beginner["notes_url"]).json()
    assert notes["level"] == "beginner" and {x[4] for x in notes["notes"]} <= {"L", "R"}
    assert client.get(beginner["midi_url"]).content[:4] == b"MThd"
    assert client.get(f"{base}/arrangement/manifest.txt").status_code == 404
    assert client.get(f"{base}/arrangement/..%5C..%5Capp.db").status_code == 404

    # Retranscrire conserve les réglages de post-traitement choisis.
    client.post(f"{base}/transcribe", json={})
    assert client.get(f"{base}/arrangement").json()["params"]["split_point"] == 55
