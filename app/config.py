import os

from pydantic import BaseModel


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0


class PostgresSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "warden"
    user: str = "postgres"
    password: str = "postgres"


class AppSettings(BaseModel):
    redis: RedisSettings
    postgres: PostgresSettings

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            redis=RedisSettings(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
            ),
            postgres=PostgresSettings(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DB", "warden"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            ),
        )


settings = AppSettings.from_env()
