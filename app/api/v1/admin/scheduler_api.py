"""
Scheduler Management API Endpoints

Admin endpoints for monitoring and controlling the notification scheduler.
"""
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_

from app.api.dependencies import get_db
from app.core.permission_checker import require_admin
from app.core.notification_log import NotificationLog, NotificationStatus, NotificationChannel
from app.models.user_model import User
from app.task.notification_scheduler import get_scheduler

router = APIRouter(prefix="/scheduler", tags=["Scheduler Management"])


@router.get("/status")
async def get_scheduler_status(
    current_user: User = Depends(require_admin())
):
    """
    Get current scheduler status and configuration.
    
    **Requires**: Admin role
    
    Returns scheduler running status, configuration, and basic statistics.
    """
    scheduler = get_scheduler()
    
    if not scheduler:
        return {
            "status": "not_initialized",
            "running": False,
            "message": "Scheduler has not been initialized"
        }
    
    return {
        "status": "active" if scheduler._running else "stopped",
        "running": scheduler._running,
        "config": {
            "check_interval_seconds": scheduler.check_interval,
            "max_concurrent_sends": scheduler.max_concurrent,
            "retry_attempts": scheduler.retry_attempts,
            "retry_delay_seconds": scheduler.retry_delay,
        },
        "current_batch_id": str(scheduler._current_batch_id) if scheduler._current_batch_id else None,
    }


@router.post("/trigger")
async def trigger_notification_batch(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    Manually trigger a notification batch immediately.
    
    **Requires**: Admin role
    
    Useful for:
    - Testing notification system
    - Sending urgent notifications
    - Manual intervention when needed
    
    **Warning**: This bypasses the normal interval checking.
    """
    scheduler = get_scheduler()
    
    if not scheduler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not initialized"
        )
    
    if not scheduler._running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running"
        )
    
    try:
        # Trigger notification check manually
        await scheduler._check_and_send_notifications()
        
        # Get statistics from the batch
        stats = await scheduler.get_stats(db, days=1)
        
        return {
            "success": True,
            "message": "Notification batch triggered successfully",
            "batch_id": str(scheduler._current_batch_id) if scheduler._current_batch_id else None,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger notifications: {str(e)}"
        )


@router.get("/stats")
async def get_scheduler_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze")
):
    """
    Get detailed scheduler statistics for the specified period.
    
    **Requires**: Admin role
    
    Returns:
    - Total notifications sent
    - Success/failure breakdown
    - Statistics by channel (email, SMS)
    - Statistics by status
    """
    scheduler = get_scheduler()
    
    if not scheduler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not initialized"
        )
    
    date_from = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Total sent
    total_result = await db.execute(
        select(func.count(NotificationLog.id))
        .where(NotificationLog.created_at >= date_from)
    )
    total_notifications = total_result.scalar() or 0
    
    # By status
    status_result = await db.execute(
        select(
            NotificationLog.status,
            func.count(NotificationLog.id)
        )
        .where(NotificationLog.created_at >= date_from)
        .group_by(NotificationLog.status)
    )
    by_status = dict(status_result.all())
    
    # By channel
    channel_result = await db.execute(
        select(
            NotificationLog.channel,
            func.count(NotificationLog.id)
        )
        .where(NotificationLog.created_at >= date_from)
        .group_by(NotificationLog.channel)
    )
    by_channel = dict(channel_result.all())
    
    # Calculate success rate
    sent_count = by_status.get(NotificationStatus.SENT.value, 0)
    delivered_count = by_status.get(NotificationStatus.DELIVERED.value, 0)
    failed_count = by_status.get(NotificationStatus.FAILED.value, 0)
    
    success_count = sent_count + delivered_count
    success_rate = (
        (success_count / total_notifications * 100) 
        if total_notifications > 0 else 0
    )
    
    return {
        "period": {
            "days": days,
            "from": date_from.isoformat(),
            "to": datetime.now(timezone.utc).isoformat()
        },
        "summary": {
            "total_notifications": total_notifications,
            "successful": success_count,
            "failed": failed_count,
            "success_rate": round(success_rate, 2)
        },
        "by_status": by_status,
        "by_channel": by_channel,
        "scheduler": {
            "running": scheduler._running,
            "check_interval_seconds": scheduler.check_interval
        }
    }


@router.get("/logs")
async def get_notification_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    channel: Optional[str] = Query(default=None, description="Filter by channel"),
    batch_id: Optional[str] = Query(default=None, description="Filter by batch ID"),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
):
    """
    Get paginated notification logs with filtering.
    
    **Requires**: Admin role
    
    Filters:
    - status: pending, sent, failed, delivered
    - channel: email, sms
    - batch_id: Specific batch UUID
    - date_from/date_to: Date range
    """
    # Build query
    query = select(NotificationLog)
    count_query = select(func.count(NotificationLog.id))
    
    # Apply filters
    conditions = []
    
    if status:
        conditions.append(NotificationLog.status == status)
    
    if channel:
        conditions.append(NotificationLog.channel == channel)
    
    if batch_id:
        try:
            import uuid
            batch_uuid = uuid.UUID(batch_id)
            conditions.append(NotificationLog.batch_id == batch_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid batch_id format"
            )
    
    if date_from:
        conditions.append(NotificationLog.created_at >= date_from)
    
    if date_to:
        conditions.append(NotificationLog.created_at <= date_to)
    
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Order and paginate
    query = query.order_by(desc(NotificationLog.created_at))
    query = query.offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "logs": [
            {
                "id": str(log.id),
                "recipient_name": log.recipient_name,
                "recipient_email": log.recipient_email,
                "recipient_phone": log.recipient_phone,
                "channel": log.channel,
                "status": log.status,
                "notification_type": log.notification_type,
                "subject": log.subject,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "failed_at": log.failed_at.isoformat() if log.failed_at else None,
                "error_message": log.error_message,
                "retry_count": log.retry_count,
                "batch_id": str(log.batch_id) if log.batch_id else None,
                "triggered_by": log.triggered_by,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "pagination": {
            "total": total,
            "skip": skip,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit > 0 else 0
        },
        "filters": {
            "status": status,
            "channel": channel,
            "batch_id": batch_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }
    }


@router.get("/batches")
async def get_recent_batches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Get recent notification batches with summary statistics.
    
    **Requires**: Admin role
    
    Returns the most recent batches with:
    - Batch ID
    - Total notifications
    - Success/failure counts
    - Timestamp
    """
    # Get distinct batch IDs with counts
    result = await db.execute(
        select(
            NotificationLog.batch_id,
            func.count(NotificationLog.id).label('total'),
            func.count(
                func.case(
                    (NotificationLog.status.in_([
                        NotificationStatus.SENT.value,
                        NotificationStatus.DELIVERED.value
                    ]), 1)
                )
            ).label('successful'),
            func.count(
                func.case(
                    (NotificationLog.status == NotificationStatus.FAILED.value, 1)
                )
            ).label('failed'),
            func.min(NotificationLog.created_at).label('created_at')
        )
        .where(NotificationLog.batch_id.isnot(None))
        .group_by(NotificationLog.batch_id)
        .order_by(desc('created_at'))
        .limit(limit)
    )
    
    batches = result.all()
    
    return {
        "batches": [
            {
                "batch_id": str(batch.batch_id),
                "total_notifications": batch.total,
                "successful": batch.successful,
                "failed": batch.failed,
                "success_rate": round((batch.successful / batch.total * 100) if batch.total > 0 else 0, 2),
                "created_at": batch.created_at.isoformat()
            }
            for batch in batches
        ],
        "count": len(batches)
    }


@router.get("/failed-notifications")
async def get_failed_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
    hours: int = Query(default=24, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(default=50, ge=1, le=100)
):
    """
    Get recent failed notifications for troubleshooting.
    
    **Requires**: Admin role
    
    Helps identify:
    - Common error patterns
    - Problematic recipients
    - System issues
    """
    date_from = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    result = await db.execute(
        select(NotificationLog)
        .where(
            and_(
                NotificationLog.status == NotificationStatus.FAILED.value,
                NotificationLog.created_at >= date_from
            )
        )
        .order_by(desc(NotificationLog.created_at))
        .limit(limit)
    )
    
    failed_logs = result.scalars().all()
    
    # Group errors
    error_counts = {}
    for log in failed_logs:
        error_msg = log.error_message or "Unknown error"
        error_counts[error_msg] = error_counts.get(error_msg, 0) + 1
    
    return {
        "period_hours": hours,
        "total_failed": len(failed_logs),
        "failed_notifications": [
            {
                "id": str(log.id),
                "recipient_name": log.recipient_name,
                "recipient_email": log.recipient_email,
                "recipient_phone": log.recipient_phone,
                "channel": log.channel,
                "error_message": log.error_message,
                "retry_count": log.retry_count,
                "failed_at": log.failed_at.isoformat() if log.failed_at else None,
            }
            for log in failed_logs
        ],
        "common_errors": [
            {"error": error, "count": count}
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        ]
    }


@router.get("/health")
async def scheduler_health_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    Health check for scheduler system.
    
    **Requires**: Admin role
    
    Returns:
    - Scheduler status
    - Recent activity
    - System health indicators
    """
    scheduler = get_scheduler()
    
    if not scheduler:
        return {
            "healthy": False,
            "status": "scheduler_not_initialized",
            "message": "Notification scheduler is not initialized"
        }
    
    # Check recent activity (last 1 hour)
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    
    recent_result = await db.execute(
        select(func.count(NotificationLog.id))
        .where(NotificationLog.created_at >= one_hour_ago)
    )
    recent_count = recent_result.scalar()
    
    # Check failure rate
    failed_result = await db.execute(
        select(func.count(NotificationLog.id))
        .where(
            and_(
                NotificationLog.created_at >= one_hour_ago,
                NotificationLog.status == NotificationStatus.FAILED.value
            )
        )
    )
    failed_count = failed_result.scalar()
    
    failure_rate = (failed_count / recent_count * 100) if recent_count > 0 else 0
    
    # Determine health status
    is_healthy = (
        scheduler._running and
        (recent_count == 0 or failure_rate < 50)  # Either no activity or low failure rate
    )
    
    health_status = "healthy" if is_healthy else "degraded"
    
    issues = []
    if not scheduler._running:
        issues.append("Scheduler is not running")
    if failure_rate >= 50 and recent_count > 0:
        issues.append(f"High failure rate: {failure_rate:.1f}%")
    
    return {
        "healthy": is_healthy,
        "status": health_status,
        "scheduler": {
            "running": scheduler._running,
            "check_interval_seconds": scheduler.check_interval,
        },
        "recent_activity": {
            "period_minutes": 60,
            "total_notifications": recent_count,
            "failed_notifications": failed_count,
            "failure_rate": round(failure_rate, 2)
        },
        "issues": issues if issues else None
    }