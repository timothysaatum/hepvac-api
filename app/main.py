import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config.config import settings
from app.db.session import engine, AsyncSessionLocal
from app.api.v1 import router as api_router
from app.core.rbac_init import initialize_rbac
from app.middlewares.settings import (
    get_system_status_for_config, 
    initialize_settings, 
    settings_middleware
)
from app.task.notification_scheduler import (
    get_scheduler, 
    start_scheduler, 
    stop_scheduler
)

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & Shutdown lifespan events."""
    # -------- STARTUP --------
    logger.info("Starting FastAPI application...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Test database connection
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
            
        logger.info("Database connection established successfully.")

        # Initialize RBAC
        async with AsyncSessionLocal() as db:
            await initialize_rbac(db)
        
        logger.info("RBAC initialized successfully.")
        
        # Initialize Settings
        async with AsyncSessionLocal() as db:
            await initialize_settings(db)
        
        logger.info("Settings initialized successfully.")

        # Initialize Notification Scheduler
        try:
            scheduler = await start_scheduler(
                check_interval_seconds=300,  # Check every 5 minutes
                max_concurrent_sends=10,     # Max 10 concurrent notifications
                retry_attempts=3,            # Retry failed sends 3 times
                retry_delay_seconds=5,       # Wait 5 seconds between retries
                deduplication_hours=72       # Don't send to same person within 24 hours
            )
            logger.info("=" * 60)
            logger.info("NOTIFICATION SCHEDULER STARTED")
            logger.info(f"   - Check interval: every 5 minutes")
            logger.info(f"   - Max concurrent sends: 10")
            logger.info(f"   - Retry attempts: 3")
            logger.info(f"   - Deduplication: 72 hours")
            logger.info(f"   - Status: RUNNING")
            logger.info("=" * 60)
        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"FAILED TO START NOTIFICATION SCHEDULER: {e}")
            logger.error("=" * 60)
            logger.error(traceback.format_exc())
            logger.warning("Application will continue without notification scheduler")

        logger.info("=" * 60)
        logger.info("Application startup complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        logger.error(traceback.format_exc())
        logger.error("Application may not function correctly")

    yield

    # -------- SHUTDOWN --------
    logger.info("=" * 60)
    logger.info("Shutting down application...")
    logger.info("=" * 60)
    
    # Stop notification scheduler gracefully
    try:
        scheduler = get_scheduler()
        if scheduler:
            logger.info("Stopping notification scheduler...")
            await stop_scheduler()
            logger.info("Notification scheduler stopped successfully")
        else:
            logger.info("No scheduler to stop")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        logger.error(traceback.format_exc())
    
    # Dispose database engine
    await engine.dispose()
    logger.info("Database engine disposed")
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # ---------------------- EXCEPTION HANDLER ----------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.error(f"Unhandled Error: {trace}")

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error": (
                    str(exc) if settings.ENVIRONMENT != "production" else "Server error"
                ),
            },
        )

    # ---------------------- HTTPS REDIRECT ----------------------
    @app.middleware("http")
    async def https_redirect(request: Request, call_next):
        if settings.ENVIRONMENT == "production":
            if request.headers.get("x-forwarded-proto") == "http":
                return RedirectResponse(str(request.url.replace(scheme="https")))
        return await call_next(request)

    # ---------------------- SETTINGS MIDDLEWARE ----------------------
    @app.middleware("http")
    async def system_status_middleware(request: Request, call_next):
        """Check system status before processing requests"""
        return await settings_middleware(request, call_next)

    # ---------------------- CORS ----------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    
    # ---------------------- ROUTES ----------------------
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # ---------------------- HEALTH CHECK ----------------------
    @app.get("/health")
    async def health_check(db: AsyncSession = Depends(get_db)):
        try:
            await db.execute(text("SELECT 1"))
            system_status = get_system_status_for_config()
            
            # Check scheduler status
            scheduler = get_scheduler()
            scheduler_status = {
                "running": scheduler._running if scheduler else False,
                "initialized": scheduler is not None,
                "check_interval": scheduler.check_interval if scheduler else None,
                "current_batch_id": str(scheduler._current_batch_id) if scheduler and scheduler._current_batch_id else None,
            }
            
            return {
                "status": "healthy",
                "system_status": system_status,
                "environment": settings.ENVIRONMENT,
                "database": "connected",
                "scheduler": scheduler_status
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy", 
                    "database": "disconnected",
                    "error": str(e)
                }
            )

    @app.get("/")
    async def root():
        system_status = get_system_status_for_config()
        scheduler = get_scheduler()
        
        return {
            "status": system_status,
            "environment": settings.ENVIRONMENT,
            "version": settings.VERSION,
            "scheduler": {
                "active": scheduler._running if scheduler else False,
                "initialized": scheduler is not None
            }
        }

    # ---------------------- SCHEDULER STATS ENDPOINT ----------------------
    @app.get("/api/v1/scheduler/stats")
    async def get_scheduler_stats(
        days: int = 7,
        db: AsyncSession = Depends(get_db)
    ):
        """Get notification scheduler statistics"""
        scheduler = get_scheduler()
        
        if not scheduler:
            return JSONResponse(
                status_code=503,
                content={"error": "Scheduler not initialized"}
            )
        
        try:
            stats = await scheduler.get_stats(db, days=days)
            return {
                "success": True,
                "stats": stats
            }
        except Exception as e:
            logger.error(f"Error getting scheduler stats: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )

    return app


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


app = create_app()