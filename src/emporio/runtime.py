"""Storage-ready P0 runtime: initialize SQLite, report readiness, and stay alive."""

from __future__ import annotations

import argparse
import signal
import time

from .config import database_path
from .session import utc_now
from .session_sqlite import SQLiteSessionRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Emporio storage-ready runtime")
    parser.add_argument("--check", action="store_true", help="initialize SQLite and exit")
    args = parser.parse_args()
    repository = SQLiteSessionRepository.connect(database_path())
    repository.purge_expired(utc_now())
    print(f"READY emporio storage db={database_path()}", flush=True)
    if args.check:
        return
    running = True

    def stop(*_signals: int) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        time.sleep(1)
    del repository


if __name__ == "__main__":
    main()
