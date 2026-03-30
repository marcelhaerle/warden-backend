import asyncpg
from fastapi import Request


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool
