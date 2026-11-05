"""Bout en bout avec les vrais modèles : un morceau court de piano traverse tout le pipeline
(tâche de fond → Demucs → ByteDance/Basic Pitch → niveaux → MusicXML).

Lancé par `npm run test:full` (marqueurs ml + network : échantillons Salamander à télécharger).
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from tests.synth import download_salamander, render_with_samples, write_wav

pytestmark = [pytest.mark.ml, pytest.mark.network]

BEAT = 0.6  # 100 BPM
MELODY = [72, 74, 76, 77, 79, 77, 76, 74, 72, 76, 79, 84]  # main droite, une note par temps
BASS = [48, 48, 53, 53, 55, 55, 48, 48, 53, 55, 48, 48]  # main gauche


def _piece() -> list[tuple[int, float, float]]:
    notes = []
    for i, (melody, bass) in enumerate(zip(MELODY, BASS, strict=True)):
        start = 0.5 + i * BEAT
        notes.append((melody, start, start + BEAT * 0.9))
        notes.append((bass, start, start + BEAT * 0.95))
    return notes


def _wait(client: TestClient, job_id: str, timeout: float = 300) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.5)
    raise AssertionError("pipeline trop long")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """Stockage isolé, mais modèles partagés avec l'application : pas de re-téléchargement."""
    shared = settings.model_copy(update={"models_path": get_settings().models_dir})
    with TestClient(create_app(shared)) as test_client:
        yield test_client


def test_full_pipeline_on_short_piano_piece(client: TestClient, tmp_path: Path) -> None:
    samples = download_salamander(get_settings().models_dir / "salamander-test")
    wav = write_wav(tmp_path / "piece.wav", render_with_samples(_piece(), samples))

    with wav.open("rb") as f:
        job = client.post("/jobs/upload", files={"file": ("piece.wav", f)}).json()
    done = _wait(client, job["id"])
    assert done["status"] == "done", done
    assert {"separate", "transcribe", "arrange"} <= set(done["timings"])
    track_id = done["track_id"]

    transcription = client.get(f"/tracks/{track_id}/transcription").json()
    assert sum(s["notes"] for s in transcription["stems"]) > 0

    arrangement = client.get(f"/tracks/{track_id}/arrangement").json()
    levels = {lvl["level"]: lvl for lvl in arrangement["levels"]}
    beginner, advanced = levels["beginner"], levels["advanced"]
    assert beginner["max_polyphony_right"] <= 2 and beginner["max_polyphony_left"] <= 2
    assert advanced["right_notes"] > 0 and advanced["left_notes"] > 0

    # La mélodie doit être largement retrouvée dans le niveau avancé (classes de hauteur).
    notes = client.get(advanced["notes_url"]).json()["notes"]
    found = {n[0] % 12 for n in notes}
    assert len({p % 12 for p in MELODY} & found) >= 5

    score = client.get(advanced["musicxml_url"])
    assert score.status_code == 200 and b"<score-partwise" in score.content
