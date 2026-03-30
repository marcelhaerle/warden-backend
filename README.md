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

## Project Structure

The application follows a conventional FastAPI layered structure:

- `main.py` - thin entrypoint that exposes `app`
- `app/app.py` - FastAPI app factory and router registration
- `app/api/` - route handlers
- `app/services/` - business logic
- `app/db/` - SQL/query functions
- `app/core/` - infrastructure concerns (database/redis)
- `app/models/` - request/response Pydantic models
- `app/events.py` - lifespan and background worker orchestration
- `tests/` - unit and integration tests

## Development

Start the development server with:

```bash
uvicorn main:app --reload
```

## Testing

Install dependencies:

```bash
pip install -r requirements.txt
```

Run lint:

```bash
python -m ruff check .
```

Run tests:

```bash
python -m pytest -q
```

## Dev Container

The dev container runs the application in one container and provisions Redis and PostgreSQL as sidecar services through Docker Compose.

- The application container connects to Redis at `redis:6379`
- The application container connects to PostgreSQL at `postgres:5432`
- The default PostgreSQL database is `warden`
- The default PostgreSQL user is `postgres`
- The default PostgreSQL password is `postgres`

Rebuild the container after changing [.devcontainer/devcontainer.json](/workspaces/warden-backend/.devcontainer/devcontainer.json) or [.devcontainer/docker-compose.yml](/workspaces/warden-backend/.devcontainer/docker-compose.yml) so the sidecar services are recreated with the updated configuration.

Inside the dev container, `REDIS_HOST` is preconfigured to `redis`.

Inside the dev container, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` are preconfigured to match the PostgreSQL sidecar.

## REST API

### Health

`GET /`

Returns service and worker status.

### List scan results

`GET /api/scans`

Supported query parameters:

- `hostname` (partial match, case-insensitive)
- `success` (`true` or `false`)
- `agent_version` (exact match)
- `reported_from` (ISO 8601 datetime)
- `reported_to` (ISO 8601 datetime)
- `limit` (default `50`, max `500`)
- `offset` (default `0`)

Example:

`/api/scans?hostname=web&success=true&limit=25&offset=0`

### Scan detail

`GET /api/scans/{scan_id}`

Returns the full scan payload for a single scan id, or `404` if not found.

### Search scan results

`GET /api/scans/search`

This endpoint supports all list filters plus JSON content filters on `raw_scan_data`:

- `json_key` and `json_value` (must be provided together)
- `json_contains` (JSON object string used with PostgreSQL JSONB containment)

Example key/value search:

`/api/scans/search?json_key=warning_count&json_value=0`

Example JSON containment search:

`/api/scans/search?json_contains={"warning_count":"0"}`

The search endpoint returns `400` if no JSON filter is provided, if only one of `json_key` or `json_value` is set, or if `json_contains` is not a valid JSON object.

### Dashboard statistics

`GET /api/dashboard/stats`

Returns host-level summary data including:

- `total_hosts`
- `failed_scans_24h`
- hardening score buckets (`danger`, `medium`, `secure`)
- up to 10 hosts in `needs_attention`
