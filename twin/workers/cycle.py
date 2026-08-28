"""The forecast worker.

The worker wakes on the configured cadence, runs the cycle in
ARCHITECTURE.md Section 4, and sleeps. At Phase 0 the cycle body is empty: the
state estimator arrives at T-038 and the forecaster at T-050. The loop exists
now so that the service starts, is observable, and has one place for the cycle
to be attached rather than a new process appearing in Phase 2.
"""

from __future__ import annotations

import logging
import time

CADENCE_S = 120.0

log = logging.getLogger(__name__)


def run_cycle() -> None:
    """Run one forecast cycle. Empty until T-050 attaches the forecaster."""
    log.info("cycle skipped: no forecaster is wired yet, see T-050")


def main() -> None:
    """Run the cycle loop until the process is stopped."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("worker started, cadence %.0f s", CADENCE_S)
    while True:
        started = time.monotonic()
        run_cycle()
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, CADENCE_S - elapsed))


if __name__ == "__main__":
    main()
