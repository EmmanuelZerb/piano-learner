"""Tâches de fond : file asyncio + un worker qui exécute les étapes bloquantes dans un thread.

- Un seul traitement à la fois : le GPU ne se partage pas, et c'est plus simple à suivre.
- L'état courant vit en mémoire (diffusé aux abonnés SSE à chaque progression) et n'est
  écrit en base qu'aux changements d'étape ou de statut.
- Annulation coopérative : les callbacks de progression lèvent `Cancelled` dès que
  l'annulation est demandée (pendant le téléchargement, Demucs, entre deux stems…).
"""

import asyncio
import contextlib
import shutil
import threading
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app import workflow
from app.config import Settings
from app.library import register_track, work_dir
from app.models import TRANSCRIBABLE_STEMS, Job, JobStatus, Track, TrackSource
from app.pipeline import postprocess as pp
from app.pipeline import transcribe as tr
from app.pipeline.errors import Cancelled, PipelineError
from app.pipeline.ingest import ingest_saved_upload, ingest_youtube
from app.telemetry import get_logger

log = get_logger("jobs")

# Part de chaque étape dans la barre de progression globale.
STEP_RANGES: dict[str, tuple[float, float]] = {
    "download": (0.0, 0.15),
    "convert": (0.10, 0.15),
    "separate": (0.15, 0.55),
    "transcribe": (0.55, 0.95),
    "arrange": (0.95, 1.0),
}
HEARTBEAT_S = 15.0


class ProcessOptions(BaseModel):
    until: Literal["ingest", "separate", "transcribe"] = "transcribe"
    stems: list[str] | None = None  # None = sélection enregistrée sur le morceau
    transcribe: tr.TranscribeParams = tr.TranscribeParams()
    postprocess: pp.PostprocessParams | None = None  # None = derniers réglages utilisés

    @field_validator("stems")
    @classmethod
    def check_stems(cls, stems: list[str] | None) -> list[str] | None:
        if stems is not None and (not stems or set(stems) - TRANSCRIBABLE_STEMS):
            raise ValueError("Pistes invalides : piano, other, bass, guitar ou vocals.")
        return stems


class JobRead(BaseModel):
    id: str
    label: str
    source: str
    track_id: str | None
    status: JobStatus
    step: str
    progress: float
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    timings: dict[str, float] | None = None  # secondes passées dans chaque étape

    @classmethod
    def from_job(cls, job: Job) -> "JobRead":
        return cls(**job.model_dump(exclude={"payload"}))


class JobContext:
    """Passé au code du pipeline (thread du worker) pour publier l'avancement."""

    def __init__(self, manager: "JobManager", job_id: str, cancel: threading.Event) -> None:
        self.manager, self.job_id, self._cancel = manager, job_id, cancel
        self.timings: dict[str, float] = {}
        self._current: tuple[str, float] | None = None

    def check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def _enter(self, name: str) -> None:
        """Chronomètre : clôt l'étape précédente quand une nouvelle commence."""
        if self._current and self._current[0] == name:
            return
        self.close()
        self._current = (name, time.perf_counter())

    def close(self) -> None:
        if self._current:
            name, start = self._current
            elapsed = time.perf_counter() - start
            self.timings[name] = round(self.timings.get(name, 0.0) + elapsed, 2)
            self._current = None

    def step(self, name: str) -> Callable[[float], None]:
        self._enter(name)
        low, high = STEP_RANGES[name]
        self.manager.update(self.job_id, step=name, progress=low)

        def report(fraction: float) -> None:
            self.check()
            self.manager.update(self.job_id, step=name, progress=low + (high - low) * fraction)

        return report

    def on_step(self, name: str, fraction: float) -> None:
        current = self.manager.get(self.job_id)
        if current is None or current.step != name:
            self.step(name)
        low, high = STEP_RANGES[name]
        self.check()
        self.manager.update(self.job_id, progress=low + (high - low) * fraction)

    def set_track(self, track: Track) -> None:
        self.manager.update(self.job_id, persist=True, track_id=track.id, label=track.title)


class JobManager:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self.settings, self.engine = settings, engine
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._live: dict[str, JobRead] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._subscribers: dict[str, set[asyncio.Queue[JobRead]]] = defaultdict(set)
        self._lock = threading.Lock()

    # --- Cycle de vie -----------------------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._recover()
        self._worker = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        for event in self._cancel.values():
            event.set()
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker

    def _recover(self) -> None:
        """Après un redémarrage : les tâches non terminées ne reprendront pas."""
        shutil.rmtree(self.settings.tmp_dir, ignore_errors=True)
        with Session(self.engine) as session:
            stale = session.exec(
                select(Job).where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            ).all()
            for job in stale:
                job.status = JobStatus.ERROR
                job.error_code = "interrupted"
                job.error_message = "Interrompu par un redémarrage du serveur."
                job.finished_at = datetime.now(UTC)
                session.add(job)
            session.commit()

    # --- API publique -------------------------------------------------------------------------

    def submit(
        self, label: str, source: str, payload: dict, track_id: str | None = None
    ) -> JobRead:
        assert self._queue is not None, "JobManager.start() n'a pas été appelé"
        job = Job(label=label, source=source, payload=payload, track_id=track_id)
        with Session(self.engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        state = JobRead.from_job(job)
        with self._lock:
            self._live[job.id] = state
            self._cancel[job.id] = threading.Event()
        self._queue.put_nowait(job.id)
        return state

    def get(self, job_id: str) -> JobRead | None:
        with self._lock:
            if job_id in self._live:
                return self._live[job_id]
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            return JobRead.from_job(job) if job else None

    def list(self, track_id: str | None = None, active: bool = False) -> list[JobRead]:
        query = select(Job).order_by(col(Job.created_at).desc()).limit(50)
        if track_id:
            query = query.where(Job.track_id == track_id)
        if active:
            query = query.where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        with Session(self.engine) as session:
            jobs = session.exec(query).all()
        states = [self.get(j.id) or JobRead.from_job(j) for j in jobs]
        # L'état en mémoire peut être en avance sur la base (fin de tâche en cours d'écriture) :
        # c'est lui qui fait foi pour décider si une tâche est encore active.
        return [s for s in states if not (active and s.status.finished)]

    def has_active(self, track_id: str) -> bool:
        return bool(self.list(track_id=track_id, active=True))

    def cancel(self, job_id: str) -> JobRead | None:
        state = self.get(job_id)
        if state is None or state.status.finished:
            return state
        event = self._cancel.get(job_id)
        if event:
            event.set()
        if state.status == JobStatus.QUEUED:  # le worker l'ignorera
            self._finish(job_id, JobStatus.CANCELLED)
        return self.get(job_id)

    async def subscribe(self, job_id: str) -> AsyncIterator[JobRead | None]:
        """État courant, puis chaque mise à jour jusqu'à la fin. None = battement de cœur."""
        queue: asyncio.Queue[JobRead] = asyncio.Queue()
        self._subscribers[job_id].add(queue)
        try:
            state = self.get(job_id)
            if state is None:
                return
            yield state
            while not state.status.finished:
                try:
                    state = await asyncio.wait_for(queue.get(), HEARTBEAT_S)
                except TimeoutError:
                    yield None
                    continue
                yield state
        finally:
            self._subscribers[job_id].discard(queue)

    # --- Mises à jour (appelables depuis n'importe quel thread) ------------------------------

    def update(self, job_id: str, persist: bool = False, **changes: object) -> None:
        with self._lock:
            previous = self._live.get(job_id)
            if previous is None:
                return
            state = previous.model_copy(update=changes)
            self._live[job_id] = state
        if persist or state.step != previous.step or state.status != previous.status:
            self._persist(state)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._publish, state)

    def _persist(self, state: JobRead) -> None:
        with Session(self.engine) as session:
            job = session.get(Job, state.id)
            if job is None:
                return
            for field, value in state.model_dump(exclude={"id", "created_at", "source"}).items():
                setattr(job, field, value)
            session.add(job)
            session.commit()

    def _publish(self, state: JobRead) -> None:
        for queue in list(self._subscribers.get(state.id, ())):
            queue.put_nowait(state)

    def _finish(self, job_id: str, status: JobStatus, **fields: object) -> None:
        self.update(job_id, persist=True, status=status, finished_at=datetime.now(UTC), **fields)
        with self._lock:
            self._live.pop(job_id, None)
            self._cancel.pop(job_id, None)

    # --- Worker -------------------------------------------------------------------------------

    async def _run_forever(self) -> None:
        assert self._queue is not None
        while True:
            job_id = await self._queue.get()
            state = self.get(job_id)
            if state is None or state.status.finished:
                continue
            await asyncio.to_thread(self._execute, job_id)

    def _execute(self, job_id: str) -> None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            payload, source, track_id = dict(job.payload), job.source, job.track_id  # type: ignore[union-attr]
        cancel = self._cancel.get(job_id, threading.Event())
        ctx = JobContext(self, job_id, cancel)
        self.update(job_id, status=JobStatus.RUNNING, step="starting")
        log.info("job_started", extra={"job_id": job_id, "source": source})
        start = time.perf_counter()
        outcome: dict[str, object] = {"status": JobStatus.DONE, "step": "done", "progress": 1.0}
        try:
            ctx.check()
            run_process(self.settings, self.engine, ctx, source, payload, track_id)
        except Cancelled:
            outcome = {"status": JobStatus.CANCELLED}
        except PipelineError as exc:
            outcome = {
                "status": JobStatus.ERROR,
                "error_code": exc.code,
                "error_message": exc.message,
            }
        except Exception as exc:
            log.exception("job_crashed", extra={"job_id": job_id})
            outcome = {
                "status": JobStatus.ERROR,
                "error_code": "internal",
                "error_message": f"Erreur inattendue : {exc}",
            }
        finally:
            if "upload_dir" in payload:
                shutil.rmtree(payload["upload_dir"], ignore_errors=True)
        ctx.close()
        state = self.get(job_id)
        log.info(
            "job_finished",
            extra={
                "job_id": job_id,
                "track_id": state.track_id if state else track_id,
                "status": str(outcome["status"]),
                "error_code": outcome.get("error_code"),
                "total_s": round(time.perf_counter() - start, 2),
                "timings": ctx.timings,
            },
        )
        self._finish(job_id, timings=ctx.timings, **outcome)  # type: ignore[arg-type]


def run_process(
    settings: Settings,
    engine: Engine,
    ctx: JobContext,
    source: str,
    payload: dict,
    track_id: str | None,
) -> None:
    """Import éventuel, puis séparation → transcription → niveaux selon `options.until`."""
    options = ProcessOptions(**payload.get("options", {}))
    with Session(engine) as session:
        if source == "youtube":
            with work_dir(settings) as work:
                audio = ingest_youtube(
                    payload["url"], work, settings.max_duration_s, ctx.step("download")
                )
                ctx.check()
                track, _ = register_track(session, settings, work, audio, TrackSource.YOUTUBE)
        elif source == "upload":
            ctx.step("convert")
            work = Path(payload["upload_dir"])
            audio = ingest_saved_upload(
                Path(payload["source_path"]), payload["filename"], work, settings.max_duration_s
            )
            track, _ = register_track(session, settings, work, audio, TrackSource.UPLOAD)
        else:
            found = session.get(Track, track_id)
            if found is None:
                raise PipelineError("not_found", "Morceau introuvable (supprimé ?).", 404)
            track = found
        ctx.set_track(track)

        if options.until == "ingest":
            return
        if options.until == "separate":
            workflow.separate(settings, track, ctx.step("separate"))
            return
        workflow.transcribe(
            settings,
            track,
            options.stems or track.stems_to_transcribe,
            options.transcribe,
            options.postprocess,
            on_step=ctx.on_step,
        )
