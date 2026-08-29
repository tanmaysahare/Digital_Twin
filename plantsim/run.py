"""Entrypoint for the line simulator service.

Two ways in.

`python -m plantsim.run` is what the `sim` container runs. It applies any
migrations that are outstanding, seeds the demo if the database is empty, and
then idles. Seeding on an empty database rather than on every start is what
makes `docker compose up` reach a working demo inside the five minute budget in
NFR-05 without rebuilding it on every restart.

`python -m plantsim.run --seed` rebuilds the demo from scratch, which is what
`make seed` calls after a migration has changed shape.

The simulator connects as the truth role. It has INSERT on the event table and
owns the truth schema, and the twin's role has neither.
"""

from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import Connection, func, select, text

from plantsim.seed import SeedSummary, seed, simulate
from twin.db.engine import create_database_engine
from twin.db.migration import upgrade_to_head
from twin.db.schema import event as event_table

IDLE_S = 60.0

log = logging.getLogger(__name__)


def _report(summary: SeedSummary) -> None:
    log.info(
        "seeded %s with scenario %s: %d units, %d events written, "
        "%d suppressed by the tier filter, observability %.2f",
        summary.line_id,
        summary.scenario_id,
        summary.units,
        summary.events,
        summary.suppressed,
        summary.observability,
    )
    for table, rows in sorted(summary.truth_rows.items()):
        log.info("  truth.%s: %d rows the twin cannot read", table, rows)


def _is_empty(connection: Connection) -> bool:
    """Whether the event table holds nothing yet."""
    count = connection.execute(
        select(func.count()).select_from(event_table)
    ).scalar_one()
    return int(count) == 0


def rebuild() -> int:
    """Rebuild the seeded demo database. Returns a process exit code."""
    engine = create_database_engine()
    try:
        with engine.begin() as connection:
            upgrade_to_head(connection)
            connection.execute(text("TRUNCATE event, station, variant, line CASCADE"))
            connection.execute(
                text(
                    "TRUNCATE truth.station_visit, truth.unit_outcome, "
                    "truth.gate_result, truth.buffer_occupancy, "
                    "truth.scenario_injection"
                )
            )
            _report(seed(connection))
    finally:
        engine.dispose()
    return 0


def bootstrap() -> None:
    """Migrate, and seed the demo if there is nothing in the database yet."""
    engine = create_database_engine()
    try:
        with engine.begin() as connection:
            upgrade_to_head(connection)
            if _is_empty(connection):
                _report(seed(connection))
            else:
                log.info("database already holds events, leaving the demo as it is")
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Start the simulator service, or rebuild the seeded database and exit."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description="The DigitalTwin.ai line simulator")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="rebuild the seeded demo database and exit",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="run one simulation and report it, without touching the database",
    )
    arguments = parser.parse_args(argv)
    if arguments.seed:
        return rebuild()

    if arguments.offline:
        result = simulate()
        log.info(
            "simulated %s, scenario %s: %d events for the twin, %d suppressed by "
            "the tier filter",
            result.line_id,
            result.scenario_id,
            result.emitted,
            result.suppressed,
        )
        return 0

    bootstrap()
    log.info("simulator idle. Run with --seed to rebuild the demo database")
    while True:
        time.sleep(IDLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
