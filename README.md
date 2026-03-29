# warden-backend

Warden Backend Application

## Configuration

## Dev Container

The dev container runs the application in one container and provisions Redis and PostgreSQL as sidecar services through Docker Compose.

- The application container connects to Redis at `redis:6379`
- The application container connects to PostgreSQL at `postgres:5432`
- The default PostgreSQL database is `warden`
- The default PostgreSQL user is `postgres`
- The default PostgreSQL password is `postgres`

Rebuild the container after changing [.devcontainer/devcontainer.json](/workspaces/warden-backend/.devcontainer/devcontainer.json) or [.devcontainer/docker-compose.yml](/workspaces/warden-backend/.devcontainer/docker-compose.yml) so the sidecar services are recreated with the updated configuration.

The backend reads Redis connection settings from environment variables and falls back to local defaults when they are not set.

- `REDIS_HOST` defaults to `localhost`
- `REDIS_PORT` defaults to `6379`
- `REDIS_DB` defaults to `0`

Inside the dev container, `REDIS_HOST` is preconfigured to `redis`.

The backend also reads PostgreSQL connection settings from environment variables and creates the required tables on startup if they do not exist.

- `POSTGRES_HOST` defaults to `localhost`
- `POSTGRES_PORT` defaults to `5432`
- `POSTGRES_DB` defaults to `warden`
- `POSTGRES_USER` defaults to `postgres`
- `POSTGRES_PASSWORD` defaults to `postgres`

Inside the dev container, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` are preconfigured to match the PostgreSQL sidecar.
