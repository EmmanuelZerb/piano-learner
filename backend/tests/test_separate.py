import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.pipeline.separate as sep
from app.db import make_engine
from app.models import Track
from tests.conftest import AudioFactory, requires_ffmpeg

torch = pytest.importorskip("torch")
sf = pytest.importorskip("soundfile")


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Remplace Demucs par un modèle factice ; renvoie un compteur d'appels."""
    calls: list[int] = []

    def run(mix, device, on_progress):  # type: ignore[no-untyped-def]
        calls.append(mix.shape[-1])
        if on_progress:
            on_progress(0.5)
        out = torch.stack([mix * (i + 1) / 10 for i in range(len(sep.STEMS))])
        return list(sep.STEMS), out

    monkeypatch.setattr(sep, "_run_model", run)
    return calls


def _wav(tmp_path: Path, seconds: float = 0.5) -> Path:
    path = tmp_path / "audio.wav"
    t = torch.arange(int(44100 * seconds)) / 44100
    tone = 0.5 * torch.sin(2 * torch.pi * 440 * t)
    sf.write(path, torch.stack([tone, tone]).T.numpy(), 44100, subtype="PCM_16")
    return path


# --- Cache --------------------------------------------------------------------------------


def test_cached_stems_requires_manifest_and_all_files(tmp_path: Path) -> None:
    assert sep.cached_stems(tmp_path) is None
    (tmp_path / sep.MANIFEST).write_text(json.dumps({"stems": ["piano", "bass"]}))
    (tmp_path / "piano.flac").write_bytes(b"x")
    assert sep.cached_stems(tmp_path) is None  # bass manquant
    (tmp_path / "bass.flac").write_bytes(b"x")
    assert set(sep.cached_stems(tmp_path) or {}) == {"piano", "bass"}


def test_separate_writes_stems_then_uses_cache(tmp_path: Path, fake_model: list[int]) -> None:
    out_dir = tmp_path / "stems"
    progress: list[float] = []
    first = sep.separate(_wav(tmp_path), out_dir, "cpu", on_progress=progress.append)
    assert not first.cached
    assert set(first.stems) == set(sep.STEMS)
    data, rate = sf.read(first.stems["piano"])
    assert rate == 44100 and data.shape == (22050, 2)
    assert progress[-1] == 1.0

    second = sep.separate(_wav(tmp_path), out_dir, "cpu")
    assert second.cached
    assert len(fake_model) == 1


def test_separate_clips_out_of_range_samples(tmp_path: Path, monkeypatch) -> None:
    def loud(mix, device, on_progress):  # type: ignore[no-untyped-def]
        return list(sep.STEMS), torch.full((6, *mix.shape), 3.0)

    monkeypatch.setattr(sep, "_run_model", loud)
    result = sep.separate(_wav(tmp_path), tmp_path / "stems", "cpu")
    data, _ = sf.read(result.stems["vocals"])
    assert data.max() <= 1.0


# --- Migration ----------------------------------------------------------------------------


def test_missing_columns_are_added_to_existing_db(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:  # schéma de la phase 1, sans transcribe_stems
        conn.execute(
            "CREATE TABLE track (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL, artist VARCHAR,"
            " source VARCHAR NOT NULL, source_url VARCHAR, original_filename VARCHAR,"
            " duration_s FLOAT NOT NULL, wav_sha256 VARCHAR NOT NULL UNIQUE,"
            " has_thumbnail BOOLEAN NOT NULL, created_at DATETIME NOT NULL)"
        )
        conn.execute(
            "INSERT INTO track VALUES ('a', 'Ancien', NULL, 'UPLOAD', NULL, NULL, 1.0, 'h', 0,"
            " '2026-11-05 10:00:00')"
        )
    engine = make_engine(f"sqlite:///{db.as_posix()}")
    with Session(engine) as session:
        track = session.get(Track, "a")
        assert track is not None
        assert track.stems_to_transcribe == ["piano", "other", "bass"]


# --- API ----------------------------------------------------------------------------------


@requires_ffmpeg
def test_separation_api_flow(client: TestClient, make_audio: AudioFactory, fake_model: list[int]):
    with make_audio("s.mp3", seconds=1).open("rb") as f:
        track = client.post("/tracks/upload", files={"file": ("s.mp3", f)}).json()["track"]
    base = f"/tracks/{track['id']}"

    assert client.get(f"{base}/stems").json()["available"] is False
    assert client.get(f"{base}/stems/piano").status_code == 404

    res = client.post(f"{base}/separate").json()
    assert res["available"] is True and res["cached"] is False
    assert [s["name"] for s in res["stems"]] == list(sep.STEMS)

    audio = client.get(f"{base}/stems/piano")
    assert audio.status_code == 200
    assert audio.content[:4] == b"fLaC"

    assert client.post(f"{base}/separate").json()["cached"] is True
    assert len(fake_model) == 1


@requires_ffmpeg
def test_transcribe_selection(client: TestClient, make_audio: AudioFactory) -> None:
    with make_audio("s.mp3").open("rb") as f:
        track = client.post("/tracks/upload", files={"file": ("s.mp3", f)}).json()["track"]
    url = f"/tracks/{track['id']}"
    assert track["transcribe_stems"] == ["piano", "other", "bass"]

    res = client.patch(url, json={"transcribe_stems": ["piano", "vocals", "piano"]})
    assert res.status_code == 200
    assert res.json()["transcribe_stems"] == ["piano", "vocals"]
    assert client.get(url).json()["transcribe_stems"] == ["piano", "vocals"]

    assert client.patch(url, json={"transcribe_stems": ["drums"]}).status_code == 422
    assert client.patch(url, json={"transcribe_stems": []}).status_code == 422


@pytest.mark.ml
def test_real_demucs_separation(tmp_path: Path) -> None:
    from app.system import torch_device

    result = sep.separate(_wav(tmp_path, seconds=3), tmp_path / "stems", torch_device())
    assert set(result.stems) == set(sep.STEMS)
    data, rate = sf.read(result.stems["other"])
    assert rate == 44100 and data.shape[1] == 2
