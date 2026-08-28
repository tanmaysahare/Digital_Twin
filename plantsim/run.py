"""Entrypoint for the line simulator service.

The SimPy model arrives at T-020 and scenario injection at T-027 to T-029. At
Phase 0 the process starts and idles so that the compose stack has the five
services ARCHITECTURE.md Section 3 specifies, and so that the simulator has a
service to be attached to rather than a new one appearing in Phase 1.
"""

from __future__ import annotations

import logging
import time

IDLE_S = 60.0

log = logging.getLogger(__name__)


def main() -> None:
    """Start the simulator service and idle until the model is attached."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("simulator service started, no line model attached yet, see T-020")
    while True:
        time.sleep(IDLE_S)


if __name__ == "__main__":
    main()
