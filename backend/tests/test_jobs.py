import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.pipeline.ingest as ingest
import app.pipeline.separate as sep
import app.pipeline.transcribe as tr
from app.config import Settings
from app.db import make_engine
from app.main import create_app
from app.models import Job, JobStatus
from app.pipeline.errors import PipelineError
from app.pipeline.notes import Note, StemTranscription
from tests.conftest import AudioFactory, requires_ffmpeg

pytestmark = requires_ffmpeg
torch = pytest.importorskip("torch")


@pytest.fixture
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Demucs et transcription factices, lents juste ce qu'il faut pour observer et annuler.

    Renvoie un réglage modifiable : `delay` = pause entre deux rapports de progression.
    """
    knobs = {"delay": 0.01, "steps": 5}

    def run_model(mix, device, on_progress):  # type: ignore[no-untyped-def]
        for i in range(int(knobs["steps"])):
            time.sleep(knobs["delay"])
            if on_progress:
                on_progress(i / knobs["steps"])
        return list(sep.STEMS), torch.stack([mix * 0.1] * len(sep.STEMS))

    def transcribe_stem(stem, audio_path, params, device, models_dir):  # type: ignore[no-untyped-def]
        notes = [Note(60 + i % 12, i * 0.25, i * 0.25 + 0.2, 80) for i in range(16)]
        return StemTranscription(stem, params.engine_for(stem), params.params_for(stem), notes)

    monkeypatch.setattr(sep, "_run_model", run_model)
    monkeypatch.setattr(tr, "transcribe_stem", transcribe_stem)
    return knobs


def wait_for(client: TestClient, job_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"tâche {job_id} non terminée : {job}")


def wait_until(client: TestClient, job_id: str, predicate, timeout: float = 20) -> dict:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(0.02)
    raise AssertionError(f"condition jamais atteinte : {job}")


def upload_job(client: TestClient, path: Path, options: dict | None = None) -> dict:
    with path.open("rb") as f:
        data = {"options": json.dumps(options)} if options else None
        res = client.post("/jobs/upload", files={"file": (path.name, f)}, data=data)
    assert res.status_code == 202, res.text
    return res.json()


# --- Pipeline complet -----------------------------------------------------------------------


def test_upload_job_runs_full_pipeline(
    client: TestClient, make_audio: AudioFactory, settings: Settings, fake_pipeline
):
    job = upload_job(client, make_audio("morceau.mp3", seconds=2))
    assert job["status"] == "queued" and job["label"] == "morceau.mp3"

    done = wait_for(client, job["id"])
    assert done["status"] == "done", done
    assert done["progress"] == 1.0 and done["label"] == "morceau"
    track_id = done["track_id"]
    assert client.get(f"/tracks/{track_id}/arrangement").json()["available"] is True
    assert client.get(f"/tracks/{track_id}/stems").json()["available"] is True
    assert list(settings.tmp_dir.iterdir()) == []
    assert client.get(f"/jobs?track_id={track_id}").json()[0]["id"] == job["id"]


def test_events_stream_reports_progress_until_done(
    client: TestClient, make_audio: AudioFactory, fake_pipeline
):
    fake_pipeline["delay"] = 0.05
    job = upload_job(client, make_audio("a.mp3"))
    events = []
    with client.stream("GET", f"/jobs/{job['id']}/events") as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        for line in res.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress)
    assert {"separate", "transcribe", "arrange"} <= {e["step"] for e in events}
    assert events[-1]["status"] == "done"


def test_youtube_job_until_ingest(
    client: TestClient, make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
):
    source = make_audio("yt.m4a")

    def fake_download(video_id, work_dir, max_duration_s, on_progress=None):  # type: ignore[no-untyped-def]
        for fraction in (0.5, 1.0):
            on_progress(fraction)
        shutil.copy(source, work_dir / "source.m4a")
        return work_dir / "source.m4a", {"title": "Clip", "uploader": "Chaîne - Topic"}

    monkeypatch.setattr(ingest, "download_youtube", fake_download)
    res = client.post(
        "/jobs/youtube",
        json={"url": "https://youtu.be/BaW_jenozKc", "options": {"until": "ingest"}},
    )
    assert res.status_code == 202
    assert res.json()["label"] == "https://www.youtube.com/watch?v=BaW_jenozKc"
    done = wait_for(client, res.json()["id"])
    assert done["status"] == "done"
    track = client.get(f"/tracks/{done['track_id']}").json()
    assert (track["title"], track["artist"]) == ("Clip", "Chaîne")


def test_invalid_inputs_are_rejected_immediately(
    client: TestClient, tmp_path: Path, settings: Settings
):
    playlist = {"url": "https://youtube.com/playlist?list=PL1"}
    assert client.post("/jobs/youtube", json=playlist).json()["code"] == "playlist"
    fake = tmp_path / "fake.mp3"
    fake.write_text("pas de l'audio" * 20)
    with fake.open("rb") as f:
        assert client.post("/jobs/upload", files={"file": ("fake.mp3", f)}).status_code == 415
    assert list(settings.tmp_dir.iterdir()) == []
    assert (
        client.post("/jobs/youtube", json={**playlist, "options": {"until": "x"}}).status_code
        == 422
    )


# --- Annulation et erreurs ------------------------------------------------------------------


def test_cancel_running_job_stops_separation(
    client: TestClient, make_audio: AudioFactory, settings: Settings, fake_pipeline
):
    fake_pipeline.update(delay=0.05, steps=400)  # ~20 s si rien ne l'interrompt
    job = upload_job(client, make_audio("long.mp3"))
    wait_until(client, job["id"], lambda j: j["step"] == "separate" and j["progress"] > 0.15)

    assert client.post(f"/jobs/{job['id']}/cancel").status_code == 200
    started = time.monotonic()
    done = wait_for(client, job["id"])
    assert done["status"] == "cancelled"
    assert time.monotonic() - started < 2
    assert not list(settings.stems_cache_dir.rglob(sep.MANIFEST))


def test_cancel_queued_job(client: TestClient, make_audio: AudioFactory, fake_pipeline):
    fake_pipeline.update(delay=0.05, steps=40)
    first = upload_job(client, make_audio("a.mp3"))
    second = upload_job(client, make_audio("b.mp3", freq=880))
    assert client.post(f"/jobs/{second['id']}/cancel").json()["status"] == "cancelled"
    assert wait_for(client, first["id"])["status"] == "done"
    assert client.get(f"/jobs/{second['id']}").json()["status"] == "cancelled"


def test_pipeline_error_is_reported(
    client: TestClient, make_audio: AudioFactory, fake_pipeline, monkeypatch: pytest.MonkeyPatch
):
    def boom(*_: object) -> None:
        raise PipelineError("boom", "Le modèle a explosé.")

    monkeypatch.setattr(tr, "transcribe_stem", boom)
    done = wait_for(client, upload_job(client, make_audio("a.mp3"))["id"])
    assert (done["status"], done["error_code"], done["error_message"]) == (
        "error",
        "boom",
        "Le modèle a explosé.",
    )


# --- Morceaux existants et suppression ------------------------------------------------------


def test_track_job_and_delete(
    client: TestClient, make_audio: AudioFactory, settings: Settings, fake_pipeline
):
    done = wait_for(client, upload_job(client, make_audio("a.mp3"))["id"])
    track_id = done["track_id"]
    sha = next(settings.stems_cache_dir.iterdir()).name

    fake_pipeline.update(delay=0.05, steps=40)
    rerun = client.post(f"/tracks/{track_id}/jobs", json={"options": {"until": "transcribe"}})
    assert rerun.status_code == 202
    assert client.post(f"/tracks/{track_id}/jobs", json={}).status_code == 409
    assert client.delete(f"/tracks/{track_id}").status_code == 409
    assert wait_for(client, rerun.json()["id"])["status"] == "done"

    assert client.delete(f"/tracks/{track_id}").status_code == 204
    assert client.get(f"/tracks/{track_id}").status_code == 404
    assert not (settings.tracks_dir / track_id).exists()
    for cache in (settings.stems_cache_dir, settings.transcriptions_cache_dir):
        assert not (cache / sha).exists()
    assert client.get(f"/jobs?track_id={track_id}").json() == []


def test_unfinished_jobs_are_marked_interrupted_on_startup(settings: Settings) -> None:
    settings.storage_dir.mkdir(parents=True)
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        session.add(Job(id="stale", label="x", source="youtube", status=JobStatus.RUNNING))
        session.commit()
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        job = client.get("/jobs/stale").json()
    assert (job["status"], job["error_code"]) == ("error", "interrupted")
