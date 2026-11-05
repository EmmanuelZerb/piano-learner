"""Logs structurés (une ligne JSON par événement) et mesure du temps des étapes.

`PIANO_LOG_FORMAT=text` donne des logs lisibles en console ; par défaut, JSON (exploitable
avec jq, ou relu en Python pour comparer les temps d'exécution).
"""

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

LOGGER_NAME = "piano"
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Champs passés via `extra={...}` : tout ce qui n'est pas un attribut standard.
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(fmt: str = "json", level: str = "INFO") -> None:
    """Idempotent : réappeler (tests, rechargement) ne duplique pas les handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    handler = next((h for h in logger.handlers if getattr(h, "_piano", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler._piano = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


log = get_logger("pipeline")


@contextmanager
def timed(step: str, **fields: object) -> Iterator[dict[str, float]]:
    """Mesure une étape et journalise `step_done` (ou `step_failed`) avec sa durée.

    Le dict produit reçoit `duration_s` à la sortie, pour qui veut le réutiliser.
    """
    result: dict[str, float] = {}
    start = time.perf_counter()
    try:
        yield result
    except BaseException:
        result["duration_s"] = round(time.perf_counter() - start, 3)
        log.warning("step_failed", extra={"step": step, **result, **fields})
        raise
    result["duration_s"] = round(time.perf_counter() - start, 3)
    log.info("step_done", extra={"step": step, **result, **fields})
