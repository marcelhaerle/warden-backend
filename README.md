# warden-backend

Warden Backend Application

## Configuration

The backend reads Redis connection settings from environment variables and falls back to local defaults when they are not set.

- `REDIS_HOST` defaults to `localhost`
- `REDIS_PORT` defaults to `6379`
- `REDIS_DB` defaults to `0`

The backend also reads PostgreSQL connection settings from environment variables and creates the required tables on startup if they do not exist.

- `POSTGRES_HOST` defaults to `localhost`
- `POSTGRES_PORT` defaults to `5432`
- `POSTGRES_DB` defaults to `warden`
- `POSTGRES_USER` defaults to `postgres`
- `POSTGRES_PASSWORD` defaults to `postgres`