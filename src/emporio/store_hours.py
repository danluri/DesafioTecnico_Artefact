"""Store opening hours (manual, section 2) and the out-of-hours notice (section 7.1)."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Callable

# Campo Grande/MS observes UTC-4 year-round (no daylight saving time since 2019).
# A fixed offset avoids depending on the OS time-zone database (absent on Windows).
STORE_TZ = timezone(timedelta(hours=-4), "America/Campo_Grande")

# weekday() -> (opens, closes); Sunday is closed. Holidays are not modelled: the
# manual lists no dates, so a holiday is treated as a regular weekday.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    **{day: (time(9), time(18)) for day in range(5)},
    5: (time(9), time(13)),
}

NOTICE_MARKER = "fora do horário de atendimento"
_WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
             "sexta-feira", "sábado", "domingo")


def is_open(moment: datetime) -> bool:
    local = moment.astimezone(STORE_TZ)
    hours = OPENING_HOURS.get(local.weekday())
    return hours is not None and hours[0] <= local.time() < hours[1]


def next_opening(moment: datetime) -> datetime:
    local = moment.astimezone(STORE_TZ)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        hours = OPENING_HOURS.get(day.weekday())
        if hours is None:
            continue
        opening = datetime.combine(day, hours[0], STORE_TZ)
        if opening > local:
            return opening
    raise RuntimeError("opening hours define no opening within a week")  # pragma: no cover


def out_of_hours_notice(moment: datetime) -> str | None:
    """Return the customer notice when the store is closed, otherwise None."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    if is_open(moment):
        return None
    local = moment.astimezone(STORE_TZ)
    opening = next_opening(moment)
    days = (opening.date() - local.date()).days
    if days <= 1:
        when = "hoje" if days == 0 else "amanhã"
    else:
        name = _WEEKDAYS[opening.weekday()]
        when = f"{'no' if opening.weekday() >= 5 else 'na'} {name}"
    return (
        f"Obs.: no momento estamos {NOTICE_MARKER} da equipe da loja "
        "(seg. a sex., 9h às 18h; sáb., 9h às 13h). "
        f"Nossa equipe retorna {when}, às {opening:%H:%M}."
    )


def current_notice() -> str | None:
    return out_of_hours_notice(datetime.now(timezone.utc))


def configured_hours_notice() -> Callable[[], str | None] | None:
    """Runtime wiring: enabled unless EMPORIO_BUSINESS_HOURS_NOTICE is false."""
    flag = os.getenv("EMPORIO_BUSINESS_HOURS_NOTICE", "true").strip().lower()
    return None if flag in {"0", "false", "no", "off"} else current_notice
