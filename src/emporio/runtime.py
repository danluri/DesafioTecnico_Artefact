"""Storage-ready P0 runtime: initialize SQLite, report readiness, and stay alive."""

from __future__ import annotations

import argparse
import signal
import time

from .config import database_path
from .conversation import ConversationService
from .llm import LLMFactory
from .session import utc_now
from .session_service import SessionService
from .session_sqlite import SQLiteSessionRepository
from .tools import ToolRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Emporio storage-ready runtime")
    parser.add_argument("--check", action="store_true", help="initialize SQLite and exit")
    args = parser.parse_args()
    repository = SQLiteSessionRepository.connect(database_path())
    repository.purge_expired(utc_now())
    sessions = SessionService(repository)
    llm = LLMFactory.create()
    tools = ToolRegistry()
    assistant = ConversationService(sessions, llm, tools)
    smoke = assistant.respond("runtime readiness")
    print(f"READY emporio storage db={database_path()}", flush=True)
    print(
        f"READY emporio assistant provider={llm.provider} session={smoke.session_id} "
        f"persistence={smoke.persistence.value}",
        flush=True,
    )
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
