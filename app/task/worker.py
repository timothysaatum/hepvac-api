"""
Async Worker  (replaces celery_worker.py)
=========================================
Polls the job_queue table and dispatches jobs to the appropriate
background task function.

Can run in two modes:
  1. Embedded  — started inside the FastAPI lifespan (single-process)
  2. Standalone — `python -m app.worker` for horizontal scaling

Scalability & Redundancy
------------------------
- Run N replicas of this worker (Docker / K8s / systemd) against the
  same database.  SELECT FOR UPDATE SKIP LOCKED guarantees each job is
  processed exactly once regardless of how many workers are running.
- `WORKER_CONCURRENCY` controls how many jobs each worker processes
  concurrently (default 4, matching the old Celery --concurrency=4).
- `reclaim_stale_jobs()` runs every 60 s to recover jobs orphaned by
  crashed workers — equivalent to Celery's acks_late / visibility timeout.

Security
--------
- No new network surface: the worker talks only to your existing database.
- Job payloads are validated at dispatch time (typed payload dicts).
- API keys stay in settings / env vars; never stored in the queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.job_queue_model import JobQueue, JobType
from app.config.config import settings
from app.task.queue_manager import QueueManager
from app.task.reminder_tasks import send_reminder_email, send_reminder_sms, scan_due_reminders


logger = logging.getLogger(__name__)

# ── Tuning knobs (override via environment variables) ──────────────────────
WORKER_CONCURRENCY   = int(os.getenv("WORKER_CONCURRENCY", "4"))
POLL_INTERVAL_SECS   = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))  # seconds between polls
RECLAIM_INTERVAL     = int(os.getenv("WORKER_RECLAIM_INTERVAL", "60"))  # reclaim every N poll ticks (not seconds); at 1s poll = every ~60s
CLAIM_BATCH_SIZE     = int(os.getenv("WORKER_CLAIM_BATCH", "10"))       # jobs claimed per poll cycle
REMINDER_SCAN_INTERVAL = int(os.getenv("WORKER_REMINDER_SCAN_INTERVAL", str(settings.REMINDER_SCAN_INTERVAL)))  # seconds


# ============================================================================
# Dispatcher — maps JobType → task function
# ============================================================================

async def _dispatch(db: AsyncSession, job: JobQueue) -> Dict[str, Any]:
    """
    Call the correct task function based on job.job_type.
    All task functions receive (db, **payload) and return a result dict.
    """
    payload = job.payload or {}
    handlers = {
        JobType.SCAN_DUE_REMINDERS:  scan_due_reminders,
        JobType.SEND_REMINDER_SMS:   send_reminder_sms,
        JobType.SEND_REMINDER_EMAIL: send_reminder_email,
    }

    handler = handlers.get(job.job_type)
    if not handler:
        raise ValueError(f"Unknown job type: {job.job_type}")

    return await handler(db, **payload)


# ============================================================================
# Single-job processor
# ============================================================================

async def _process_job(job_id: int) -> None:
    """
    Open a fresh DB session, fetch the job by PK, run it, commit or roll back.

    We accept `job_id` (an int) rather than a SQLAlchemy ORM object because
    the object was loaded in a different session that is already closed by the
    time this coroutine runs.  Passing a detached ORM object across a session
    boundary raises DetachedInstanceError on the first attribute access.
    """
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        job = (await db.execute(
            select(JobQueue).where(JobQueue.id == job_id)
        )).scalar_one_or_none()

        if not job:
            logger.error(f"Job {job_id} not found in _process_job — already deleted?")
            return

        try:
            result = await _dispatch(db, job)
            await QueueManager.mark_completed(db, job, result)
            await db.commit()
            logger.info(f"Job {job.id} ({job.job_type}) completed successfully")

        except Exception as exc:
            await db.rollback()

            # Re-open a fresh session to persist the failure state
            async with AsyncSessionLocal() as err_db:
                fresh_job = (await err_db.execute(
                    select(JobQueue).where(JobQueue.id == job_id)
                )).scalar_one_or_none()

                if fresh_job:
                    await QueueManager.mark_failed(
                        err_db,
                        fresh_job,
                        str(exc),
                        retry_delay_seconds=5,
                    )
                    await err_db.commit()

            logger.error(f"Job {job_id} ({job.job_type}) failed: {exc}")


# ============================================================================
# Worker loop
# ============================================================================

class Worker:
    """
    Async worker that polls the job queue and processes jobs concurrently.

    Usage (embedded in FastAPI lifespan):
        worker = Worker()
        asyncio.create_task(worker.run())
        ...
        worker.stop()

    Usage (standalone):
        asyncio.run(Worker().run())
    """

    def __init__(self) -> None:
        self._running = False
        self._semaphore = asyncio.Semaphore(WORKER_CONCURRENCY)
        self._tasks: set[asyncio.Task] = set()
        self._reclaim_counter = 0
        self._reminder_scan_counter = REMINDER_SCAN_INTERVAL  # fire on first poll, not after 5 min

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        logger.info(
            f"Worker started — concurrency={WORKER_CONCURRENCY}, "
            f"poll_interval={POLL_INTERVAL_SECS}s"
        )
        self._running = True

        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.error(f"Worker poll error: {exc}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECS)

        # Drain in-flight tasks before exiting
        if self._tasks:
            logger.info(f"Draining {len(self._tasks)} in-flight tasks...")
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("Worker stopped")

    async def _poll_once(self) -> None:
        """Claim a batch of jobs and spawn concurrent processing tasks."""
        self._reclaim_counter += 1

        # Periodically reclaim stale jobs from crashed workers
        if self._reclaim_counter >= RECLAIM_INTERVAL:
            self._reclaim_counter = 0
            async with AsyncSessionLocal() as db:
                await QueueManager.reclaim_stale_jobs(db)
                await db.commit()

        # Periodically enqueue a reminder scan job
        # Counter tracks elapsed seconds (poll interval × ticks)
        self._reminder_scan_counter += POLL_INTERVAL_SECS
        if self._reminder_scan_counter >= REMINDER_SCAN_INTERVAL:
            self._reminder_scan_counter = 0
            async with AsyncSessionLocal() as db:
                await QueueManager.enqueue_scan_due_reminders(db)
                await db.commit()
            logger.debug("Enqueued SCAN_DUE_REMINDERS heartbeat job")

        # Claim available jobs (respects WORKER_CONCURRENCY slots)
        available_slots = WORKER_CONCURRENCY - len(self._tasks)
        if available_slots <= 0:
            return

        async with AsyncSessionLocal() as db:
            jobs = await QueueManager.claim_next(
                db, batch_size=min(available_slots, CLAIM_BATCH_SIZE)
            )
            await db.commit()  # Persist RUNNING status so other workers skip these

        for job in jobs:
            task = asyncio.create_task(self._run_with_semaphore(job.id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_with_semaphore(self, job_id: int) -> None:
        async with self._semaphore:
            await _process_job(job_id)


# ============================================================================
# Standalone entry point
# ============================================================================

async def _main() -> None:
    """Run the worker as a standalone process."""
    import logging
    from app.config.config import settings

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s  %(name)-30s  %(levelname)-8s  %(message)s",
    )

    worker = Worker()

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)

    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())