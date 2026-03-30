import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.core.database import create_postgres_pool, ensure_schema
from app.core.redis_client import create_redis_client
from app.db.scan_runs import save_scan_results
from app.models import AgentPayload

logger = logging.getLogger("warden-backend")


async def redis_worker(app: FastAPI) -> None:
    logger.info("Redis worker started. Waiting for data in 'warden_queue'...")
    redis_client = app.state.redis_client

    try:
        while True:
            result = await redis_client.brpop("warden_queue", timeout=0)
            if result:
                _, raw_data = result
                try:
                    parsed_json = json.loads(raw_data)
                    payload = AgentPayload(**parsed_json)
                    scan_run_id = await save_scan_results(app.state.pool, payload)
                    logger.info("Scan Run %s from %s saved.", scan_run_id, payload.hostname)
                except Exception as exc:
                    logger.error("Error processing payload: %s", exc)
                    logger.warning("Putting payload back into Redis queue (Retry).")
                    await redis_client.lpush("warden_queue", raw_data)
                    await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info("Redis worker is shutting down cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_postgres_pool()
    await ensure_schema(app.state.pool)
    logger.info("PostgreSQL connected and schema initialized.")

    app.state.redis_client = create_redis_client()
    task = asyncio.create_task(redis_worker(app))
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    await app.state.redis_client.aclose()
    await app.state.pool.close()
