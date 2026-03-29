# warden-backend

Warden Backend Application

## Configuration

The backend reads Redis connection settings from environment variables and falls back to local defaults when they are not set.

- `REDIS_HOST` defaults to `localhost`
- `REDIS_PORT` defaults to `6379`
- `REDIS_DB` defaults to `0`