import asyncio
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
from app.task.worker import Worker
from app.middlewares.settings import (
    get_system_status_for_config,
    initialize_settings,
    settings_middleware
)


logger = logging.getLogger("uvicorn")

_worker = Worker()


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


    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        logger.error(traceback.format_exc())
        logger.error("Application may not function correctly")

    # Start background worker (fires first scan immediately on startup)
    worker_task = asyncio.create_task(_worker.run())
    logger.info("Background worker started.")

    yield

    # -------- SHUTDOWN --------
    logger.info("=" * 60)
    logger.info("Shutting down application...")
    logger.info("=" * 60)

    # Stop worker and wait for in-flight jobs to drain
    _worker.stop()
    await worker_task
    logger.info("Background worker stopped.")

    # Dispose database engine
    await engine.dispose()
    logger.info("Database engine disposed")
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
        openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
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



            return {
                "status": "healthy",
                "system_status": system_status,
                "environment": settings.ENVIRONMENT,
                "database": "connected",
                # "scheduler": scheduler_status
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
        # scheduler = get_scheduler()

        return {
            "status": system_status,
            "environment": settings.ENVIRONMENT,
            "version": settings.VERSION,
            # "scheduler": {
            #     "active": scheduler._running if scheduler else False,
            #     "initialized": scheduler is not None
            # }
        }

    # ---------------------- SCHEDULER STATS ENDPOINT ----------------------
    @app.get("/api/v1/scheduler/stats")
    async def get_scheduler_stats(
        days: int = 7,
        db: AsyncSession = Depends(get_db)
    ):
        """Get notification scheduler statistics"""
        #
    return app


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


app = create_app()