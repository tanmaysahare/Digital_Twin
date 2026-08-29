# RUNNING.md

**Purpose:** how to run the stack, with and without Docker.
**Audience:** the team, and a judge who cannot or will not install Docker.
**Last updated:** 2026-08-29

---

## 1. The Docker path

This is the supported path and the one the cold start budget applies to (NFR-05,
5 minutes on a clean machine).

```
git clone https://github.com/tanmaysahare/Digital_Twin.git
cd Digital_Twin
docker compose up
```

Five containers start: `db`, `api`, `worker`, `sim` and `web`. Open
`http://localhost:3000`. The API is on `http://localhost:8000`, and
`http://localhost:8000/health` reports whether it is up.

`docker compose down` stops them. `docker compose down -v` also drops the
database volume, which is what to do when a migration has changed shape and the
seeded data needs rebuilding.

Ports are configurable in `.env`. Copy `.env.example` if 3000, 8000 or 5432 are
already taken on the machine.

---

## 2. The non-Docker path

Needed when Docker Desktop is unavailable, which on a corporate Windows laptop
is common enough that the path is documented here in Phase 0 rather than
discovered during submission week.

### 2.1 What you need

| Component | Version | Note |
|---|---|---|
| Python | 3.11 | Pinned by TECHNICAL_SPEC.md Section 1 and by `pyproject.toml` |
| Node | 20 or newer | For the web application only |
| PostgreSQL | 16 | With the TimescaleDB extension available |

The database is the only genuinely awkward dependency. Three options, in order
of how little work they are:

1. **Run the database container alone.** If Docker exists but you would rather
   run the application code on the host: `make db`. Everything else runs
   natively against `localhost:5432`.
2. **Install PostgreSQL 16 and TimescaleDB natively.** TimescaleDB ships
   installers for Windows, macOS and Debian derivatives. After installing,
   create the database and enable the extension:
   ```
   createdb digitaltwin
   psql -d digitaltwin -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
   ```
3. **Plain PostgreSQL 16 with no TimescaleDB.** The migrations detect the
   missing extension and create ordinary tables where a hypertable would
   otherwise be used. Ingest throughput drops and the retention policies do
   nothing, which is acceptable for a demo and is not acceptable for a pilot.
   The interface is unchanged.

### 2.2 Setup

```
python -m venv .venv
.venv/bin/activate            # Windows: .venv\Scripts\activate
make install                  # Windows without make: .\make.cmd install
make migrate
make seed
```

`make install` installs the Python package in editable mode with its
development extras, then installs the web dependencies.

`make seed` runs the simulator once and writes two things: the canonical event
stream to the `event` table, which is what the twin reads, and the ground truth
to the `truth` schema, which the application role has no privilege on. It prints
both counts, and the gap between them is how much of the line the twin cannot
see. Re-run it whenever a migration has changed shape.

### 2.3 Running

Four processes, in four terminals. They are separate because a 200-replication
Monte Carlo run must never block an HTTP request (ARCHITECTURE.md Section 3).

```
uvicorn twin.api.main:app --reload --port 8000
python -m twin.workers.cycle
python -m plantsim.run
cd web && npm run dev
```

Set `DIGITALTWIN_DATABASE_URL` and `DIGITALTWIN_LINE_CONFIG` in the environment,
or copy `.env.example` to `.env`. The defaults in `.env.example` point at a
local database on port 5432.

---

## 3. Windows without make

`make` is not installed by default on Windows and the project does not require
it. `make.cmd` accepts the same task names and runs the same steps:

```
.\make.cmd            list every task
.\make.cmd install
.\make.cmd lint
.\make.cmd test
```

Both the Makefile and `make.cmd` delegate to `tools/tasks.py`, so there is one
definition of what each task does rather than two that drift.

---

## 4. Checking it worked

| Check | Command | Expected |
|---|---|---|
| Services are up | `docker compose ps` | Five services, `db` healthy |
| API answers | `curl http://localhost:8000/health` | `{"service":"digitaltwin-api","status":"OK",...}` |
| Lint is green | `make lint` | Design rules, ruff, mypy, eslint and stylelint all pass |
| Tests are green | `make test` | pytest and the web unit tests pass |

---

## 5. Known rough edges

- **The first `docker compose up` builds images.** That is the slow one. The
  5 minute cold start budget is measured on a machine with the base images
  already pulled, which is the state of any machine that has run Docker before.
  A genuinely cold machine spends most of the time pulling `postgres` and
  `node`.
- **Windows line endings.** `.gitattributes` pins the Makefile and the Python
  sources to LF. If a file arrives with carriage returns anyway, `git config
  core.autocrlf false` and re-checkout.
- **Port 5432 is often taken** by an existing PostgreSQL install. Set
  `POSTGRES_PORT` in `.env`.

---

**Related:** [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [../ai/TASKS.md](../ai/TASKS.md)
