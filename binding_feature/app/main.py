import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from database import db_manager
from routes import router
from websocket_handler import websocket_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Schnell Storage Add-on...")

    try:
        # Initialize database
        await db_manager.init_database()
        logger.info("Database initialized successfully")

        # Start WebSocket client in background if token is provided
        if os.getenv("HA_TOKEN"):
            asyncio.create_task(websocket_manager.start())
            logger.info("WebSocket manager started")
        else:
            logger.warning(
                "No HA_TOKEN provided, WebSocket integration disabled")

        # Schedule automatic backups if enabled
        if os.getenv("AUTO_BACKUP", "true").lower() == "true":
            asyncio.create_task(schedule_backups())
            logger.info("Automatic backup scheduler started")

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Schnell Storage Add-on...")
    await websocket_manager.stop()


async def schedule_backups():
    """Schedule automatic database backups"""
    backup_interval_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    backup_interval_seconds = backup_interval_hours * 3600

    while True:
        try:
            await asyncio.sleep(backup_interval_seconds)
            await db_manager.backup_database()
            logger.info("Automatic backup completed")
        except Exception as e:
            logger.error(f"Automatic backup failed: {e}")

# Create FastAPI application
app = FastAPI(
    title="Schnell Storage API",
    description="Custom data storage for Schnell Home Automation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Flutter app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Root endpoint


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Schnell Storage API",
        "version": "1.0.0",
        "description": "Custom data storage for Schnell Home Automation",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "api": "/api/v1"
        }
    }

# Global health endpoint (also available at /api/v1/health)


@app.get("/health")
async def health():
    """Global health check endpoint"""
    try:
        async with db_manager.get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM device_analytics")
            total_records = (await cursor.fetchone())[0]

        return {
            "status": "healthy",
            "database_status": "connected",
            "websocket_status": "connected" if websocket_manager.client.is_connected else "disconnected",
            "version": "1.0.0",
            "total_records": total_records
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database_status": "disconnected",
                "error": str(e)
            }
        )

# Exception handlers


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found",
                 "message": "The requested endpoint does not exist"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error",
                 "message": "An unexpected error occurred"}
    )

if __name__ == "__main__":
    # This is for development only
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=False
    )
