from fastapi.testclient import TestClient

from app.main import app
from app.system import ToolInfo


def test_health_returns_tool_and_device_info() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert set(body["ffmpeg"]) >= {"available", "path", "version"}
    assert body["device"]["device"] in {"cuda", "mps", "cpu"}


def test_health_degraded_without_ffmpeg(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "ffmpeg_info", lambda: ToolInfo(available=False))
    response = TestClient(main.create_app()).get("/health")
    assert response.json()["status"] == "degraded"
