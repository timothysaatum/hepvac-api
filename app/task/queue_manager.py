"""
Queue Manager
Provides enqueue / dequeue primitives built on PostgreSQL.

Why SELECT FOR UPDATE SKIP LOCKED?
- Multiple worker coroutines (or processes) can poll simultaneously
- The DB engine ensures only ONE worker claims each row
- No Redis, no Celery broker — your existing Postgres does everything
- Crashed workers: `locked_until` acts as a lease; jobs are reclaimed
  after the lease expires (see `reclaim_stale_jobs`)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_queue_model import JobQueue, JobStatus, JobType

logger = logging.getLogger(__name__)

# How long a worker may hold a job before it's considered stale / crashed
JOB_LEASE_SECONDS = 300  # 5 minutes


class QueueManager:
    """
    Thin async wrapper around the job_queue table.
    All methods accept an AsyncSession so they compose naturally
    with the existing get_async_db() dependency.
    """

    # ------------------------------------------------------------------ #
    #  Enqueue                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def enqueue(
        db: AsyncSession,
        job_type: JobType,
        payload: Dict[str, Any],
        *,
        max_retries: int = 3,
        delay_seconds: int = 0,
    ) -> JobQueue:
        """
        Insert a new job into the queue.

        Args:
            db:            Active async session (caller must commit).
            job_type:      Which task to run.
            payload:       Keyword arguments forwarded to the task function.
            max_retries:   How many times to retry on failure.
            delay_seconds: Schedule job N seconds from now (default: immediate).

        Returns:
            The newly created JobQueue row (not yet committed).
        """
        scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        job = JobQueue(
            job_type=job_type,
            payload=payload,
            max_retries=max_retries,
            scheduled_at=scheduled_at,
            status=JobStatus.PENDING,
        )
        db.add(job)
        await db.flush()  # Assign PK without committing — caller commits
        logger.debug(f"Enqueued job {job.id} ({job_type}) scheduled_at={scheduled_at}")
        return job

    # ------------------------------------------------------------------ #
    #  Claim (dequeue)                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def claim_next(
        db: AsyncSession,
        batch_size: int = 1,
    ) -> List[JobQueue]:
        """
        Atomically claim up to `batch_size` pending jobs.

        Uses SELECT FOR UPDATE SKIP LOCKED so concurrent workers never
        pick the same job.  The caller is responsible for committing after
        processing so the status update is durable.

        Returns a list (possibly empty) of claimed JobQueue rows.
        """
        now = datetime.now(timezone.utc)
        lease_expiry = now + timedelta(seconds=JOB_LEASE_SECONDS)

        # Find pending jobs whose schedule time has arrived
        stmt = (
            select(JobQueue)
            .where(
                JobQueue.status == JobStatus.PENDING,
                JobQueue.scheduled_at <= now,
            )
            .order_by(JobQueue.scheduled_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result = await db.execute(stmt)
        jobs: List[JobQueue] = list(result.scalars().all())

        for job in jobs:
            job.status = JobStatus.RUNNING
            job.started_at = now
            job.locked_until = lease_expiry

        if jobs:
            await db.flush()

        return jobs

    # ------------------------------------------------------------------ #
    #  Finalize                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def mark_completed(
        db: AsyncSession,
        job: JobQueue,
        result: Dict[str, Any],
    ) -> None:
        """Mark a job as successfully completed and store its result."""
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.locked_until = None
        job.result = result
        job.error_message = None
        await db.flush()

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        job: JobQueue,
        error: str,
        *,
        retry_delay_seconds: int = 5,
    ) -> None:
        """
        Mark a job as failed.
        If retries remain, requeue it with exponential back-off.
        """
        job.locked_until = None

        if job.retry_count < job.max_retries:
            # Increment AFTER the comparison so max_retries=3 means 3 total
            # attempts (not 2).  Incrementing before would make the check
            # `3 < 3` → False on the third attempt, silently dropping a retry.
            job.retry_count += 1
            backoff = retry_delay_seconds * (2 ** (job.retry_count - 1))
            job.status = JobStatus.PENDING
            job.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            job.error_message = f"[attempt {job.retry_count}] {error}"
            logger.warning(
                f"Job {job.id} ({job.job_type}) failed "
                f"(attempt {job.retry_count}/{job.max_retries}), "
                f"retrying in {backoff}s"
            )
        else:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = error
            logger.error(
                f"Job {job.id} ({job.job_type}) permanently failed "
                f"after {job.retry_count} attempts: {error}"
            )

        await db.flush()

    # ------------------------------------------------------------------ #
    #  Stale job recovery                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def reclaim_stale_jobs(db: AsyncSession) -> int:
        """
        Reset jobs that were claimed but never finished (e.g. worker crash).
        Called periodically by the worker loop.

        Returns the number of jobs reclaimed.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(JobQueue)
            .where(
                JobQueue.status == JobStatus.RUNNING,
                JobQueue.locked_until < now,
            )
            .values(
                status=JobStatus.PENDING,
                locked_until=None,
                started_at=None,
            )
            .returning(JobQueue.id)
        )
        result = await db.execute(stmt)
        reclaimed = len(result.fetchall())
        if reclaimed:
            logger.warning(f"Reclaimed {reclaimed} stale jobs")
        # No flush() needed — the UPDATE was already sent to the DB by execute().
        # The caller (worker._poll_once) commits the transaction.
        return reclaimed

    # ------------------------------------------------------------------ #
    #  Convenience helpers                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def enqueue_send_single_sms(
        db: AsyncSession,
        message_id: int,
        *,
        max_retries: int = 3,
        delay_seconds: int = 0,
    ) -> JobQueue:
        return await QueueManager.enqueue(
            db,
            JobType.SEND_SINGLE_SMS,
            {"message_id": message_id},
            max_retries=max_retries,
            delay_seconds=delay_seconds,
        )

    @staticmethod
    async def enqueue_send_bulk_sms(
        db: AsyncSession,
        campaign_id: int,
        batch_size: Optional[int] = None,
    ) -> JobQueue:
        payload: Dict[str, Any] = {"campaign_id": campaign_id}
        if batch_size is not None:
            payload["batch_size"] = batch_size
        return await QueueManager.enqueue(
            db, JobType.SEND_BULK_SMS, payload, max_retries=1
        )

    @staticmethod
    async def enqueue_update_campaign_stats(
        db: AsyncSession,
        campaign_id: int,
    ) -> JobQueue:
        return await QueueManager.enqueue(
            db,
            JobType.UPDATE_CAMPAIGN_STATS,
            {"campaign_id": campaign_id},
            max_retries=3,
        )

    @staticmethod
    async def enqueue_retry_failed_messages(
        db: AsyncSession,
        campaign_id: int,
    ) -> JobQueue:
        return await QueueManager.enqueue(
            db,
            JobType.RETRY_FAILED_MESSAGES,
            {"campaign_id": campaign_id},
            max_retries=1,
        )


    @staticmethod
    async def enqueue_reminder_sms(
        db: AsyncSession,
        reminder_id: str,
        *,
        delay_seconds: int = 0,
    ) -> "JobQueue":
        """Enqueue a single SMS reminder send job."""
        return await QueueManager.enqueue(
            db,
            JobType.SEND_REMINDER_SMS,
            {"reminder_id": reminder_id},
            max_retries=3,
            delay_seconds=delay_seconds,
        )

    @staticmethod
    async def enqueue_reminder_email(
        db: AsyncSession,
        reminder_id: str,
        *,
        delay_seconds: int = 0,
    ) -> "JobQueue":
        """Enqueue a single email reminder send job."""
        return await QueueManager.enqueue(
            db,
            JobType.SEND_REMINDER_EMAIL,
            {"reminder_id": reminder_id},
            max_retries=3,
            delay_seconds=delay_seconds,
        )

    @staticmethod
    async def enqueue_scan_due_reminders(
        db: AsyncSession,
        advance_days: Optional[int] = None,
    ) -> "JobQueue":
        """
        Enqueue a reminder scan job.
        Called by the worker heartbeat — not by HTTP endpoints.
        max_retries=1: if the scan itself fails, log it and let the next
        heartbeat retry rather than hammering the queue.
        """
        payload: Dict[str, Any] = {}
        if advance_days is not None:
            payload["advance_days"] = advance_days
        return await QueueManager.enqueue(
            db,
            JobType.SCAN_DUE_REMINDERS,
            payload,
            max_retries=1,
        )

    @staticmethod
    async def enqueue_cleanup_old_campaigns(
        db: AsyncSession,
        days: int = 90,
    ) -> JobQueue:
        return await QueueManager.enqueue(
            db,
            JobType.CLEANUP_OLD_CAMPAIGNS,
            {"days": days},
            max_retries=2,
        )