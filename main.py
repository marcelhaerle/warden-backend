import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("warden-backend")


class AgentPayload(BaseModel):
    agent_version: str
    hostname: str
    timestamp: str
    success: bool
    error: str | None = None
    scan_data: dict[str, str]


# Initialize Redis connection (asynchronous) from environment variables
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)


async def redis_worker():
    """Background task: continuously listens to the Redis queue."""
    logger.info("Redis worker started. Waiting for data in 'warden_queue'...")
    try:
        while True:
            # brpop blocks without CPU load until an item arrives in the list
            # (timeout=0 means wait indefinitely)
            result = await redis_client.brpop("warden_queue", timeout=0)
            if result:
                queue_name, raw_data = result
                try:
                    # Parse JSON and validate it directly with Pydantic
                    parsed_json = json.loads(raw_data)
                    payload = AgentPayload(**parsed_json)

                    logger.info(
                        f"Received new agent package from: {payload.hostname}")
                    logger.info(
                        f"Timestamp: {payload.timestamp} | Successful: {payload.success}")
                    logger.info(
                        f"Found scan metrics: {len(payload.scan_data)}")

                    # TODO: Insert into PostgreSQL here later

                except Exception as e:
                    logger.error(f"Error while processing payload: {e}")

    except asyncio.CancelledError:
        logger.info("Redis worker is shutting down cleanly.")

# 2. Lifespan manager for clean startup and shutdown


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs when Uvicorn starts
    task = asyncio.create_task(redis_worker())
    yield
    # Runs during shutdown (Ctrl+C)
    task.cancel()
    await redis_client.close()

# 3. The actual FastAPI application
app = FastAPI(title="Warden API", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "Warden backend is running", "worker": "active"}
