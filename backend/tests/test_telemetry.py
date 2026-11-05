import json
import logging

import pytest

from app.telemetry import JsonFormatter, configure_logging, timed


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "piano.test", "levelname": "INFO", "msg": message})
    record.__dict__.update(extra)
    return record


def test_json_formatter_includes_extra_fields() -> None:
    line = JsonFormatter().format(_record("step_done", step="separate", duration_s=1.5))
    data = json.loads(line)
    assert data["event"] == "step_done"
    assert data["level"] == "info"
    assert (data["step"], data["duration_s"]) == ("separate", 1.5)
    assert data["ts"].endswith("+00:00")


def test_timed_logs_duration_and_failures() -> None:
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Collect()
    logging.getLogger("piano").addHandler(handler)
    try:
        with timed("demo", track_id="t1") as info:
            info["cached"] = True
        with pytest.raises(ValueError), timed("boom"):
            raise ValueError("x")
    finally:
        logging.getLogger("piano").removeHandler(handler)
    done, failed = records
    assert (done.getMessage(), done.step, done.cached, done.track_id) == (
        "step_done",
        "demo",
        True,
        "t1",
    )
    assert done.duration_s >= 0
    assert (failed.getMessage(), failed.step) == ("step_failed", "boom")


def test_configure_logging_is_idempotent() -> None:
    configure_logging("json")
    configure_logging("text")
    handlers = [h for h in logging.getLogger("piano").handlers if getattr(h, "_piano", False)]
    assert len(handlers) == 1
    configure_logging("json")
