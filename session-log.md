# Session Log — Postgres/Docker Migration + Frontend

A chronological record of what was done, what broke, and how it was actually fixed — kept as a real reference, not a cleaned-up summary.

---

## 1. GitHub verification (carried over from prior session)

**Checked:** whether `.env.example` showed placeholder values and `.env` was absent from the repo.

**Result:** confirmed directly by fetching the live repo — `.env.example` contained `DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<database_name>`, and `.env` did not appear in the file listing.

**Gap found and closed:** the repo's file listing at that point also didn't show `init.sql` or the `init/` folder, even though it had supposedly been created locally in a prior session. This turned out to be real — `init.sql` had not yet been pushed. It was committed and pushed during this session (confirmed via a screenshot showing commit `bb10e6c — add sql file`).

---

## 2. `requirements.txt`

**Started:** empty file — meant a Dockerfile's `pip install` step would have been a no-op.

**Populated with real, installed versions** (checked via `pip show`, not guessed):
```
fastapi==0.137.1
uvicorn==0.49.0
pydantic==2.13.4
```
(`psycopg2-binary==2.9.12` added later, once the Postgres repository class was being planned.)

**Bug found:** two files existed — `requirements.txt` (correct spelling) and `requirments.txt` (typo, missing an "e"). The typo'd file was created accidentally, most likely by a `type requirments.txt` command that referenced a file that didn't yet exist under that name — the exact mechanism was never fully confirmed, similar to an earlier unexplained "duplicate `docker run`" incident in the project's history. **Fixed** by deleting the typo'd duplicate (`Remove-Item "requirments.txt"`), leaving exactly one correctly-named file.

---

## 3. Dockerfile

Created to build the FastAPI app image:
```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Minor cosmetic issue:** the file was written via a single-line PowerShell command using `` `n`n `` for blank lines between sections; the blank lines didn't survive (likely PowerShell string-escaping behavior), producing a version with no blank lines between instructions. **Not fixed** — purely cosmetic, doesn't affect how Docker parses or builds the file. Left as-is by choice.

**Verified working** via a standalone build and run, independent of Postgres/Compose:
```powershell
docker build -t task-api .
docker run -d -p 8000:8000 --name task-api-test task-api
curl http://localhost:8000/tasks
```
Returned the SQLite seed data correctly (`Fold laundry`, `Walk the dog`, `Do assignments`) — confirming the image builds and serves the API correctly on its own, before any Postgres wiring was attempted.

---

## 4. `.dockerignore`

Created to prevent `.env` (real Postgres credentials) and other unnecessary files from being copied into the Docker image:
```
.env
.git
.gitignore
__pycache__/
*.pyc
tasks.db
```
Verified via `type .dockerignore` — matched exactly on the first attempt, no issues.

---

## 5. `docker-compose.yaml`

Wired two services — `db` (Postgres 16) and `app` (the FastAPI image) — into one file, so `docker compose up` starts both.

**Decision point:** the existing `task-postgres` container (created earlier via plain `docker run`) already had data in its volume (`task-pgdata`), including a `persistence_check` test row. Postgres only runs `init.sql`-style scripts on a container's genuine **first boot** with an empty data directory — pointing compose at the existing volume would have silently skipped testing whether `init.sql` actually worked.

**Resolved by:** pointing the new compose file at a fresh volume name, `task-pgdata-v2`, rather than reusing or destroying the old one. Non-destructive, and it directly tested the thing that needed proving.

**Mechanism worth remembering:** inside the Docker Compose network, the `app` service must reach Postgres via the service name `db`, not `localhost` — `localhost` inside a container refers only to that container itself. This is why the `DATABASE_URL` used inside compose (`@db:5432`) is deliberately different from the one in `.env` (`@localhost:5432`), which is for running the app directly on the host machine.

---

## 6. First `docker compose up` — port conflict

**Bug:** `app-1` failed to start with:
```
Bind for 0.0.0.0:8000 failed: port is already allocated
```
**Cause:** the earlier standalone test container (`task-api-test`, from Dockerfile verification) was still running and holding port 8000.

**Fixed:** `docker rm -f task-api-test`, then re-ran `docker compose up -d`. `db-1` and `app-1` both started.

**Follow-up bug, subtler:** even after removing the conflicting container, `curl http://localhost:8000/tasks` failed with "Unable to connect to the remote server" — even though `docker ps` showed `app-1` as running.

**Diagnosis:** `docker ps -a`'s `PORTS` column showed `app-1` with just `8000/tcp` (internal only), not a real host mapping like `db-1` had (`0.0.0.0:5432->5432/tcp`). **Root cause:** the first `docker compose up` attempt had failed *during* `app-1`'s creation (the port conflict above) — after the container object existed but before the port binding succeeded. The second `docker compose up -d` saw the container already existed and just *started* it, inheriting the broken, port-less state, rather than recreating it fresh.

**Fixed by:** `docker compose up -d --force-recreate`, which forces a genuine recreation instead of just starting the existing (broken) container. Confirmed via `docker ps -a` showing the correct `0.0.0.0:8000->8000/tcp` mapping, then a successful `curl`.

**Lesson:** a failed mid-creation container can leave a corrupted intermediate state that a naive retry/restart won't fix — `--force-recreate` is the reliable way to guarantee a clean container.

---

## 7. `init.sql` verified on fresh volume

```powershell
docker exec -it postgrescontainer-db-1 psql -U taskuser -d tasks -c "\dt"
```
Returned the `tasks` table — confirmed `init.sql` executed correctly on the genuine first boot against `task-pgdata-v2`.

---

## 8. `PostgresTaskRepository` — five debugging passes

Writing this class (swapping `sqlite3` for `psycopg2`, same five-method interface: `get_all`, `get`, `create`, `update`, `delete`) surfaced the same two categories of mistake repeatedly, across several rounds of manual retyping:

**Category 1 — leftover SQLite placeholder syntax.** SQLite uses `?`; psycopg2 requires `%s`. This appeared in early drafts of `get` and `create` and had to be corrected explicitly.

**Category 2 — no `lastrowid` equivalent in Postgres.** SQLite lets you read `cursor.lastrowid` after an `INSERT` to get the new row's id. Postgres has no such attribute — the `create` method needed the SQL changed to `INSERT ... RETURNING id`, then `cursor.fetchone()[0]` to actually read it back. Several attempts substituted a *different* guessed attribute name (`cursor.new_id`) instead of implementing the `RETURNING` clause — this had to be corrected multiple times before it landed.

**Also hit along the way:**
- A version of `get_all` that wasn't valid Python at all (a `for` loop mistakenly indented at class level instead of inside the method) — this was worse than the previous bug, since it blocked the whole file from importing, not just one endpoint from working.
- A `RETURNING_id` typo (underscore instead of a space) — `RETURNING id` is two separate SQL tokens, not one identifier.

**Final, correct version** (all five methods) was verified individually against a live Postgres container:

| Method | How verified | Result |
|---|---|---|
| `get_all` | `GET /tasks` on fresh volume | `[]` — correct (no seed data in `init.sql`, unlike the old SQLite `_init_schema()`) |
| `create` | `POST /tasks` | `201`, real `id` returned via `RETURNING id` |
| `get` | `GET /tasks/{id}` | `200`, correct data |
| `update` | `PUT /tasks/{id}` | `200`, field actually changed (`done: true`) |
| `delete` | `DELETE` then re-`GET` | `204`, then `404` — row genuinely removed |

**Side-effect worth knowing, not a bug:** `get`/`get_all` under Postgres return `done` as a real boolean (`true`/`false`), whereas the old SQLite version returned raw integers (`0`/`1`) from those same two methods. This is more consistent than before (SQLite only used `true`/`false` on `POST`/`PUT`), but it's an unannounced side-effect of the migration, not a deliberate fix — worth knowing if anything downstream expects the old `0`/`1` shape.

---

## 9. Persistence proof — full compose teardown, not just container restart

A stronger test than the original Stage B stop/start proof:

1. Created a task via the API (`id: 2`, "persistence proof after compose down").
2. `docker compose down` — removes containers and network, **not** named volumes.
3. Confirmed via `docker volume ls` that `postgrescontainer_task-pgdata-v2` still existed even with both containers gone.
4. `docker compose up -d` — recreated both containers from scratch.
5. `GET /tasks` via the live API (not `psql` directly) — task `id: 2` was still there.

This confirms data survives a full container/network rebuild, which is a stronger and more relevant claim than surviving a simple stop/start.

---

## 10. Frontend

Built as a single `index.html` (plain HTML/CSS/JS, no framework), covering all four planned stages at once (static shell, read, create, update/delete) rather than incrementally, due to time constraints — flagged explicitly as a deliberate shortcut, not an oversight.

**Prerequisite: CORS.** The frontend and API run on different origins (`localhost:5500` vs `localhost:8000`), so without explicit permission, the browser silently blocks the frontend's `fetch` calls — no visible error on the page, only in the browser's developer console. Added via FastAPI's built-in `CORSMiddleware`, allowing only `http://localhost:5500`.

**Decision made along the way:** the frontend must be *served* (`python -m http.server 5500`), not opened as a local `file://` page — some browsers block cross-origin `fetch` from `file://` origins regardless of CORS headers, since `file://` isn't treated as a real origin by CORS.

**Verified working** via the actual UI: tasks created, toggled done/undo, and deleted, with the visible list correctly reflecting each action — not just a static screenshot of the initial load.

---

## Open items / not yet done

- The four frontend stages were built as one combined artifact rather than incrementally — worth revisiting individually if a deeper understanding of the separate steps is needed later.
- `PostgresTaskRepository` still lives inside `main.py` rather than its own module — a known simplification, not a requirement violation.
- `psycopg2` import appears twice at the top of `main.py` (harmless — Python no-ops the duplicate — but worth cleaning up).
