# Task API

A simple Task management REST API built with **FastAPI**, backed by **PostgreSQL** and fully containerized with **Docker Compose**.

## Stack

- **Python 3.14** + **FastAPI**
- **PostgreSQL 16** (containerized, persistent volume)
- **psycopg2** as the Postgres driver
- **Docker Compose** for one-command startup

## Running the project

Requirements: Docker Desktop installed and running.

```bash
docker compose up -d --build
```

This starts two services:

- `db` — a Postgres 16 container, with a named volume (`task-pgdata-v2`) for persistent storage, and `init/init.sql` mounted so the `tasks` table is created automatically on first boot.
- `app` — the FastAPI application, built from the project's `Dockerfile`, listening on port `8000`.

Once both containers are up, the API is available at `http://localhost:8000`.

## Endpoints

| Method | Path          | Description                          |
|--------|---------------|---------------------------------------|
| GET    | `/`           | API info                              |
| GET    | `/Health`     | Health check                          |
| GET    | `/tasks`      | List all tasks                        |
| GET    | `/tasks/{id}` | Get a single task by id                |
| POST   | `/tasks`      | Create a task (`{"title": "..."}`)     |
| PUT    | `/tasks/{id}` | Update a task's `title` and/or `done`  |
| DELETE | `/tasks/{id}` | Delete a task                          |

Example:

```bash
curl -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d "{\"title\":\"Buy groceries\"}"
```

## Architecture: repository pattern

Routes in `main.py` never touch the database directly. All storage access goes through a repository class exposing five methods: `get_all`, `get`, `create`, `update`, `delete`.

This project was originally built with SQLite, using a `TaskRepository` class. Migrating to Postgres meant writing a `PostgresTaskRepository` class implementing the same five methods with `psycopg2` instead of `sqlite3`, and reading the connection string from the `DATABASE_URL` environment variable. **The route handlers themselves did not change at all** — only which repository class is instantiated (`repo = PostgresTaskRepository()`). This is the payoff of keeping storage logic behind a single interface: swapping databases became a change isolated to one class.

Each of the five repository methods was individually tested against a live Postgres container (not just verified by reading the code) — creating a real row, reading it back, updating it, and deleting it, each confirmed through the actual HTTP responses.

## Environment variables

A `.env` file (not committed — see `.gitignore`) holds the real connection string for running the app **directly on your host** against the Dockerized Postgres:

```
DATABASE_URL=postgresql://taskuser:taskpass@localhost:5432/tasks
```

`.env.example` (committed) documents the required shape with placeholders only:

```
DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<database_name>
```

Note that `docker-compose.yaml` sets a **different** `DATABASE_URL` for the `app` container itself (`@db:5432` instead of `@localhost:5432`). This isn't an inconsistency — inside Docker Compose's network, containers reach each other by service name (`db`), not `localhost`. `localhost` inside a container refers only to that container itself.

## Persistence

Postgres data lives in a named Docker volume (`task-pgdata-v2`), independent of the container's own lifecycle. This was verified concretely, not assumed:

1. A task was created via the running API.
2. The entire stack was torn down with `docker compose down` (which removes the containers and network, but not named volumes).
3. The stack was brought back up with `docker compose up -d`, recreating both containers from scratch.
4. The previously created task was still returned by `GET /tasks` — read back through the live API, not by inspecting the database directly.

This confirms data survives a full container/network rebuild, not just a container stop/start.

## Docker specifics

- **`Dockerfile`** — builds the FastAPI app image on `python:3.14-slim`. Dependencies are copied and installed (`requirements.txt`) before the rest of the source is copied in, so Docker's layer cache avoids re-running `pip install` when only application code changes.
- **`.dockerignore`** — excludes `.env`, `.git`, `__pycache__/`, and the old SQLite `tasks.db` file from the image build context. Without this, the real Postgres credentials in `.env` would be baked directly into the built image.
- **`init/init.sql`** — creates the `tasks` table. Postgres only runs files in `docker-entrypoint-initdb.d/` on a container's first boot with an empty data directory — mounting this against a volume that already has data silently does nothing, which is expected Postgres behavior, not a bug.

## Known, deliberate inconsistency

`POST` and `PUT` responses include an extra `"message"` key that `GET` responses do not. This was identified during the SQLite phase and carried forward intentionally rather than fixed, since it wasn't part of a stated requirement.

## What's next

- Plain HTML/CSS/JS frontend (no framework) consuming this API — will require CORS middleware to be added to FastAPI, since the frontend will be served from a different origin.