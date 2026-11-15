import os
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from ugharani import clock


@pytest.fixture
def utc_server():
    """The process clock on UTC, as on Render."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    if before is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = before
    time.tzset()


def test_now_is_india_time_on_a_utc_server(monkeypatch, utc_server):
    monkeypatch.delenv("UGHARANI_TODAY")
    india = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    assert abs((clock.now() - india.replace(tzinfo=None)).total_seconds()) < 5
    assert clock.now().tzinfo is None  # compared with naive times (call hours) and stored as text


def test_today_can_be_fixed(monkeypatch):
    monkeypatch.setenv("UGHARANI_TODAY", "2026-12-31")
    assert clock.today() == date(2026, 12, 31)


def test_today_follows_india_time_without_a_fixed_date(monkeypatch, utc_server):
    monkeypatch.delenv("UGHARANI_TODAY")
    assert clock.today() == clock.now().date()
    assert os.environ["TZ"] == "UTC"


def test_now_is_on_the_fixed_date(monkeypatch):
    monkeypatch.setenv("UGHARANI_TODAY", "2026-11-30")
    assert clock.now().date() == date(2026, 11, 30)


def test_daily_budgets_follow_the_real_date(monkeypatch):
    """A budget keyed on a fixed date would never refill."""
    monkeypatch.setenv("UGHARANI_TODAY", "2020-01-01")
    assert clock.real_today() == datetime.now(clock.IST).date()


def test_gnani_budget_refills_on_the_real_next_day(monkeypatch):
    from ugharani import gnani
    monkeypatch.setenv("GNANI_DAILY_LIMIT", "1")
    monkeypatch.setattr(gnani, "_calls", {})
    day = {"value": date(2026, 11, 3)}
    monkeypatch.setattr(clock, "real_today", lambda: day["value"])
    gnani._spend()
    with pytest.raises(gnani.GnaniError):
        gnani._spend()
    day["value"] = date(2026, 11, 4)
    gnani._spend()  # a new day, a new budget, whatever UGHARANI_TODAY says
