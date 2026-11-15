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


def test_now_is_india_time_on_a_utc_server(utc_server):
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
