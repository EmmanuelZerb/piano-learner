from pathlib import Path

import mido
import pretty_midi
import pytest
from fastapi.testclient import TestClient

import app.pipeline.transcribe as tr
from app.pipeline.midi_io import write_midi
from app.pipeline.notes import Note, Pedal, StemTranscription
from tests.conftest import AudioFactory, requires_ffmpeg
from tests.synth import (
    C_MAJOR_SCALE,
    download_salamander,
    note_f1,
    render_notes,
    render_with_samples,
    scale_notes,
    write_wav,
)


def _transcription(stem: str, pitches: list[int], pedals: bool = False) -> StemTranscription:
    notes = [Note(p, i * 0.5, i * 0.5 + 0.4, 80) for i, p in enumerate(pitches)]
    return StemTranscription(stem, "fake", {}, notes, [Pedal(0.0, 1.0)] if pedals else [])


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Remplace les modèles de transcription ; renvoie la liste des stems transcrits."""
    calls: list[str] = []

    def fake(stem, audio_path, params, device, models_dir):  # type: ignore[no-untyped-def]
        calls.append(stem)
        t = _transcription(stem, [60, 64, 67], pedals=stem == "piano")
        return StemTranscription(
            stem, params.engine_for(stem), params.params_for(stem), t.notes, t.pedals
        )

    monkeypatch.setattr(tr, "transcribe_stem", fake)
    return calls


# --- Format pivot et export MIDI ------------------------------------------------------------


def test_notes_json_round_trip(tmp_path: Path) -> None:
    original = _transcription("piano", [60, 62], pedals=True)
    original.save(tmp_path / "t.json")
    assert StemTranscription.load(tmp_path / "t.json") == original


def test_merged_midi_has_one_channel_per_stem_and_sustain(tmp_path: Path) -> None:
    path = tmp_path / "merged.mid"
    stems = ["piano", "other", "bass"]
    write_midi([_transcription(s, [60, 64], pedals=s == "piano") for s in stems], path)

    channels: dict[str, set[int]] = {}
    sustain = False
    for track in mido.MidiFile(path).tracks:
        name = next((m.name for m in track if m.type == "track_name"), None)
        for msg in track:
            if msg.type == "note_on":
                channels.setdefault(name, set()).add(msg.channel)
            if msg.type == "control_change" and msg.control == 64:
                sustain = True
    assert set(channels) == set(stems)
    assert all(len(c) == 1 for c in channels.values())
    assert len(set().union(*channels.values())) == 3
    assert sustain

    reloaded = pretty_midi.PrettyMIDI(str(path))
    assert [i.program for i in reloaded.instruments] == [0, 4, 32]
    assert sum(len(i.notes) for i in reloaded.instruments) == 6


# --- Paramètres et cache --------------------------------------------------------------------


def test_params_per_stem() -> None:
    params = tr.TranscribeParams()
    assert params.engine_for("piano") == "bytedance"
    assert params.engine_for("vocals") == "basic_pitch"
    assert params.params_for("bass")["max_freq"] == 500.0
    assert params.params_for("other")["max_freq"] is None
    assert tr.TranscribeParams(piano_engine="basic_pitch").engine_for("piano") == "basic_pitch"


def test_cache_key_depends_on_params() -> None:
    a = tr.TranscribeParams()
    b = tr.TranscribeParams(basic_pitch=tr.BasicPitchParams(onset_threshold=0.6))
    key = tr.cache_key
    assert key("other", "basic_pitch", a.params_for("other")) != key(
        "other", "basic_pitch", b.params_for("other")
    )
    # Changer un seuil Basic Pitch ne doit pas invalider le piano (ByteDance).
    assert key("piano", "bytedance", a.params_for("piano")) == key(
        "piano", "bytedance", b.params_for("piano")
    )


def test_transcribe_stems_caches_and_writes_midi(tmp_path: Path, fake_engine: list[str]) -> None:
    stems = {s: tmp_path / f"{s}.flac" for s in ("piano", "other", "bass")}
    out, cache = tmp_path / "midi", tmp_path / "cache"
    params = tr.TranscribeParams()

    first = tr.transcribe_stems(
        stems, ["piano", "other", "bass"], params, cache, out, "cpu", tmp_path
    )
    assert fake_engine == ["piano", "other", "bass"]
    assert first.cached == []
    assert {p.name for p in out.glob("*.mid")} == {
        "piano.mid",
        "other.mid",
        "bass.mid",
        "merged.mid",
    }

    tweaked = tr.TranscribeParams(basic_pitch=tr.BasicPitchParams(frame_threshold=0.4))
    second = tr.transcribe_stems(stems, ["piano", "bass"], tweaked, cache, out, "cpu", tmp_path)
    assert fake_engine[3:] == ["bass"]  # piano relu du cache
    assert second.cached == ["piano"]
    assert {p.name for p in out.glob("*.mid")} == {"piano.mid", "bass.mid", "merged.mid"}
    assert tr.read_manifest(out) == second.manifest


# --- API ------------------------------------------------------------------------------------


@requires_ffmpeg
def test_transcription_api_flow(
    client: TestClient, make_audio: AudioFactory, fake_model: list[int], fake_engine: list[str]
):
    with make_audio("s.mp3").open("rb") as f:
        track = client.post("/tracks/upload", files={"file": ("s.mp3", f)}).json()["track"]
    base = f"/tracks/{track['id']}"

    assert client.get(f"{base}/transcription").json()["available"] is False
    res = client.post(f"{base}/transcribe", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert [s["stem"] for s in body["stems"]] == ["piano", "other", "bass"]
    assert body["stems"][0]["engine"] == "bytedance" and body["stems"][0]["pedals"] == 1
    assert len(fake_model) == 1  # séparation lancée automatiquement

    merged = client.get(body["merged_url"])
    assert merged.status_code == 200 and merged.content[:4] == b"MThd"
    assert client.get(body["stems"][2]["midi_url"]).content[:4] == b"MThd"
    assert client.get(f"{base}/transcription").json() == body

    vocals = client.post(f"{base}/transcribe", json={"stems": ["vocals"]}).json()
    assert [s["stem"] for s in vocals["stems"]] == ["vocals"]
    assert len(fake_model) == 1  # stems repris du cache


@requires_ffmpeg
def test_transcription_api_rejects_bad_input(client: TestClient, make_audio: AudioFactory):
    with make_audio("s.mp3").open("rb") as f:
        track = client.post("/tracks/upload", files={"file": ("s.mp3", f)}).json()["track"]
    base = f"/tracks/{track['id']}"
    assert client.post(f"{base}/transcribe", json={"stems": ["drums"]}).status_code == 422
    bad_params = {"params": {"basic_pitch": {"onset_threshold": 2}}}
    assert client.post(f"{base}/transcribe", json=bad_params).status_code == 422
    assert client.get(f"{base}/midi/..%5C..%5Capp.db").status_code == 404
    assert client.get(f"{base}/midi/piano.mid").status_code == 404


def test_defaults_endpoint(client: TestClient) -> None:
    assert client.get("/transcription/defaults").json() == tr.TranscribeParams().model_dump()


# --- Précision réelle (critère de la phase 3) -------------------------------------------------


def _pitches(notes: list[Note]) -> list[tuple[int, float, float]]:
    return [(n.pitch, n.start, n.end) for n in notes]


@pytest.mark.ml
def test_basic_pitch_transcribes_synthetic_scale(tmp_path: Path) -> None:
    reference = scale_notes(C_MAJOR_SCALE)
    wav = write_wav(tmp_path / "scale.wav", render_notes(reference))
    estimated = tr.run_basic_pitch(wav, tr.TranscribeParams().params_for("other"))
    precision, recall, _ = note_f1(reference, _pitches(estimated))
    assert recall >= 0.9 and precision >= 0.9


@pytest.mark.ml
@pytest.mark.network
def test_bytedance_transcribes_piano_scale(tmp_path: Path) -> None:
    """Gamme rendue avec de vrais échantillons : ByteDance est entraîné sur du piano réel."""
    from app.config import get_settings
    from app.system import torch_device

    reference = scale_notes(C_MAJOR_SCALE)
    samples = download_salamander(get_settings().models_dir / "salamander-test")
    wav = write_wav(tmp_path / "scale.wav", render_with_samples(reference, samples))
    notes, _ = tr.run_bytedance(wav, tr.PianoParams(), torch_device(), get_settings().models_dir)
    precision, recall, _ = note_f1(reference, _pitches(notes))
    assert recall >= 0.9 and precision >= 0.9
