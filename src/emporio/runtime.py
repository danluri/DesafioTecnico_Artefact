"""Storage-ready P0 runtime: initialize SQLite, report readiness, and stay alive."""

from __future__ import annotations

import argparse
import signal
import time

from .config import database_path
from .conversation import ConversationService
from .dev_console import DevConsoleApplication, serve
from .llm import LLMFactory
from .policy_runtime import runtime_llm_and_tools
from .session import utc_now
from .session_service import SessionService
from .session_sqlite import SQLiteSessionRepository
from .store_hours import configured_hours_notice
from .tracing import without_tracing


def main() -> None:
    parser = argparse.ArgumentParser(description="Emporio storage-ready runtime")
    parser.add_argument("--check", action="store_true", help="initialize SQLite and exit")
    parser.add_argument(
        "--dev-console", action="store_true", help="start the localhost development console"
    )
    args = parser.parse_args()
    repository = SQLiteSessionRepository.connect(database_path())
    repository.purge_expired(utc_now())
    sessions = SessionService(repository)
    llm, tools, _policy = runtime_llm_and_tools(LLMFactory.create())
    assistant = ConversationService(sessions, llm, tools, hours_notice=configured_hours_notice())
    print(f"READY emporio storage db={database_path()}", flush=True)
    if args.check:
        with without_tracing():
            smoke = assistant.respond("runtime readiness")
        print(
            f"READY emporio assistant provider={llm.provider} session={smoke.session_id} "
            f"persistence={smoke.persistence.value}",
            flush=True,
        )
        return
    if args.dev_console:
        print(f"READY emporio dev-console provider={llm.provider}", flush=True)
        serve(DevConsoleApplication(assistant))
        return
    with without_tracing():
        smoke = assistant.respond("runtime readiness")
    print(
        f"READY emporio assistant provider={llm.provider} session={smoke.session_id} "
        f"persistence={smoke.persistence.value}",
        flush=True,
    )
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
