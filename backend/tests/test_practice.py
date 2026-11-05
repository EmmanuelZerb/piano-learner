from fastapi.testclient import TestClient

from tests.conftest import AudioFactory, requires_ffmpeg

pytestmark = requires_ffmpeg

SESSION = {
    "level": "beginner",
    "mode": "wait",
    "hands": "R",
    "speed": 0.75,
    "hits": 30,
    "wrongs": 5,
    "misses": 5,
    "duration_s": 120.5,
}


def _track(client: TestClient, make_audio: AudioFactory) -> str:
    with make_audio("a.mp3").open("rb") as f:
        return client.post("/tracks/upload", files={"file": ("a.mp3", f)}).json()["track"]["id"]


def test_record_and_list_sessions(client: TestClient, make_audio: AudioFactory) -> None:
    track_id = _track(client, make_audio)
    empty = client.get(f"/tracks/{track_id}/practice").json()
    assert empty == {"sessions": [], "best_accuracy": None, "total_duration_s": 0.0}

    first = client.post(f"/tracks/{track_id}/practice", json=SESSION)
    assert first.status_code == 201
    assert first.json()["accuracy"] == 0.75
    client.post(
        f"/tracks/{track_id}/practice", json={**SESSION, "hits": 40, "misses": 0, "wrongs": 0}
    )

    history = client.get(f"/tracks/{track_id}/practice").json()
    assert [s["accuracy"] for s in history["sessions"]] == [1.0, 0.75]  # plus récente d'abord
    assert history["best_accuracy"] == 1.0
    assert history["total_duration_s"] == 241.0


def test_invalid_session_rejected(client: TestClient, make_audio: AudioFactory) -> None:
    track_id = _track(client, make_audio)
    for patch in ({"mode": "x"}, {"hits": -1}, {"speed": 3}, {"hands": "RL"}):
        assert (
            client.post(f"/tracks/{track_id}/practice", json={**SESSION, **patch}).status_code
            == 422
        )
    assert client.post("/tracks/nope/practice", json=SESSION).status_code == 404


def test_empty_session_has_zero_accuracy(client: TestClient, make_audio: AudioFactory) -> None:
    track_id = _track(client, make_audio)
    body = {**SESSION, "hits": 0, "wrongs": 0, "misses": 0}
    assert client.post(f"/tracks/{track_id}/practice", json=body).json()["accuracy"] == 0.0


def test_history_deleted_with_track(client: TestClient, make_audio: AudioFactory) -> None:
    track_id = _track(client, make_audio)
    client.post(f"/tracks/{track_id}/practice", json=SESSION)
    assert client.delete(f"/tracks/{track_id}").status_code == 204
    other = _track(client, make_audio)  # même audio : nouvel id, historique vierge
    assert client.get(f"/tracks/{other}/practice").json()["sessions"] == []
