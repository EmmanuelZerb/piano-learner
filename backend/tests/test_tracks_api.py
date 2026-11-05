import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.pipeline.ingest as ingest
from app.config import Settings
from tests.conftest import AudioFactory, requires_ffmpeg

pytestmark = requires_ffmpeg


def _upload(client: TestClient, path: Path, name: str | None = None):
    with path.open("rb") as f:
        return client.post("/tracks/upload", files={"file": (name or path.name, f)})


def test_upload_mp3_creates_track(client: TestClient, make_audio: AudioFactory, settings: Settings):
    res = _upload(client, make_audio("chanson.mp3", seconds=2))
    assert res.status_code == 201, res.text
    body = res.json()
    track = body["track"]
    assert body["duplicate"] is False
    assert track["title"] == "chanson"
    assert track["source"] == "upload"
    assert track["duration_s"] == pytest.approx(2, abs=0.1)
    assert (settings.tracks_dir / track["id"] / "audio.wav").exists()
    assert list(settings.tmp_dir.iterdir()) == []

    listed = client.get("/tracks").json()
    assert [t["id"] for t in listed] == [track["id"]]

    audio = client.get(track["audio_url"])
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"


def test_same_audio_twice_is_deduplicated(client: TestClient, make_audio: AudioFactory):
    path = make_audio("a.mp3")
    first = _upload(client, path).json()
    second = _upload(client, path, name="renamed.mp3").json()
    assert second["duplicate"] is True
    assert second["track"]["id"] == first["track"]["id"]
    assert len(client.get("/tracks").json()) == 1


def test_renamed_text_file_is_rejected(client: TestClient, tmp_path: Path, settings: Settings):
    fake = tmp_path / "fake.mp3"
    fake.write_text("ceci n'est pas un mp3" * 50)
    res = _upload(client, fake)
    assert res.status_code == 415
    assert res.json()["code"] == "unsupported_format"
    assert list(settings.tmp_dir.iterdir()) == []


def test_too_large_upload_is_rejected(client: TestClient, tmp_path: Path):
    big = tmp_path / "big.wav"
    big.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * (6 * 1024 * 1024))
    res = _upload(client, big)
    assert res.status_code == 413
    assert res.json()["code"] == "too_large"


def test_unknown_track_returns_404(client: TestClient):
    assert client.get("/tracks/nope").status_code == 404
    assert client.get("/tracks/nope/audio").status_code == 404


def test_youtube_import_with_mocked_download(
    client: TestClient, make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
):
    source = make_audio("yt.m4a", seconds=1)

    def fake_download(video_id: str, work_dir: Path, max_duration_s: float):
        shutil.copy(source, work_dir / "source.m4a")
        (work_dir / "source.jpg").write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        info = {"title": "Clip officiel", "artist": "Artiste", "uploader": "Chaîne"}
        return work_dir / "source.m4a", info

    monkeypatch.setattr(ingest, "download_youtube", fake_download)
    res = client.post("/tracks/youtube", json={"url": "https://youtu.be/BaW_jenozKc"})
    assert res.status_code == 201, res.text
    track = res.json()["track"]
    assert (track["title"], track["artist"]) == ("Clip officiel", "Artiste")
    assert track["source_url"] == "https://www.youtube.com/watch?v=BaW_jenozKc"
    assert client.get(track["thumbnail_url"]).status_code == 200


def test_youtube_errors_are_reported(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def private(*_: object) -> None:
        raise ingest.classify_youtube_error("ERROR: Private video")

    monkeypatch.setattr(ingest, "download_youtube", private)
    res = client.post("/tracks/youtube", json={"url": "https://youtu.be/BaW_jenozKc"})
    assert res.status_code == 422
    assert res.json()["code"] == "private"

    res = client.post("/tracks/youtube", json={"url": "https://youtube.com/playlist?list=PL1"})
    assert res.json()["code"] == "playlist"


@pytest.mark.network
def test_real_youtube_download(client: TestClient):
    """« Me at the zoo » (19 s), première vidéo YouTube : courte et stable dans le temps."""
    res = client.post(
        "/tracks/youtube", json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
    )
    assert res.status_code == 201, res.text
    track = res.json()["track"]
    assert track["title"] == "Me at the zoo"
    assert track["duration_s"] == pytest.approx(19, abs=1)
    assert client.get(track["thumbnail_url"]).status_code == 200
    assert client.get(track["audio_url"]).content[:4] == b"RIFF"


@pytest.mark.network
def test_real_youtube_unavailable_video(client: TestClient):
    res = client.post("/tracks/youtube", json={"url": "https://youtu.be/BaW_jenozKc"})
    assert res.json()["code"] == "unavailable"
