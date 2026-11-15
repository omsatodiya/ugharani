"""The trader's date and time: India time, whatever the server's clock is set to.

Render's servers run on UTC, so the plain `date.today()` / `datetime.now()` were 5½ hours behind
the trader: the call hours ("10:00-13:00") were checked against the wrong time, and between
midnight and 5:30 am "today" was still yesterday. India has one time zone and no daylight saving,
so a fixed +5:30 is exact and needs no time zone database in the image.

`UGHARANI_TODAY=YYYY-MM-DD` fixes the date (tests that must not depend on the day they run, a demo
that jumps ahead); `now()` then is that date at the current time of day, so call hours, Sundays,
holidays and call timestamps all agree with it. Daily budgets use `real_today()`, which never
follows the fixed date: a budget whose day never changes would never refill.
"""

import os
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _india() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def real_today() -> date:
    """The actual date in India, for daily budgets and limits."""
    return _india().date()


def today() -> date:
    fixed = os.getenv("UGHARANI_TODAY", "").strip()
    return date.fromisoformat(fixed) if fixed else real_today()


def now() -> datetime:
    """India time, without a time zone attached (as the rest of the app stores and compares it),
    on the fixed date if UGHARANI_TODAY is set."""
    actual = _india()
    return datetime.combine(today(), actual.time())
