"""The trader's date and time: India time, whatever the server's clock is set to.

Render's servers run on UTC, so the plain `date.today()` / `datetime.now()` were 5½ hours behind
the trader: the call hours ("10:00-13:00") were checked against the wrong time, and between
midnight and 5:30 am "today" was still yesterday. India has one time zone and no daylight saving,
so a fixed +5:30 is exact and needs no time zone database in the image.

`UGHARANI_TODAY=YYYY-MM-DD` fixes the date: tests that must not depend on the day they run, and a
demo that wants to jump ahead.
"""

import os
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now() -> datetime:
    """India time, without a time zone attached (as the rest of the app stores and compares it)."""
    return datetime.now(IST).replace(tzinfo=None)


def today() -> date:
    fixed = os.getenv("UGHARANI_TODAY", "").strip()
    return date.fromisoformat(fixed) if fixed else now().date()
