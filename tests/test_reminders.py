from datetime import date

import pytest
from fastapi.testclient import TestClient

from ugharani import db, gnani, main, reminders
from ugharani.extract import parse
from ugharani.seed import seed

OCT_1 = date(2026, 10, 1)
TODAY = date(2026, 10, 31)


def add(conn, text, on=OCT_1):
    db.add_entry(conn, parse(text, today=on), text, today=on)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("AUDIO_CACHE", str(tmp_path / "tts"))

    async def synthesize(text):
        return b"RIFF" + text.encode()

    monkeypatch.setattr(gnani, "synthesize", synthesize)
    conn = db.connect()
    add(conn, "Rameshbhai ne 1,00,000 nu maal, 20 divas")            # due Oct 21: overdue
    add(conn, "Rameshbhai ne 1,40,000 nu maal, 30 divas")            # due Oct 31: today
    add(conn, "Kantaben ne 75,000 nu kapad, 32 divas")               # due Nov 2: upcoming
    add(conn, "Maheshbhai ne 50,000 nu maal, 60 divas")              # due Nov 30: not yet
    add(conn, "Rameshbhai e 1,20,000 jama karavya", on=TODAY)        # pays oldest first
    yield conn
    conn.close()


def test_payments_settle_oldest_credits_first(conn):
    left = {(c.buyer, c.due_date.isoformat()): c.amount for c in reminders.open_credits(conn)}
    assert left == {
        ("Rameshbhai", "2026-10-31"): 120000,  # Oct 21 bill fully paid, 20,000 went to this one
        ("Kantaben", "2026-11-02"): 75000,
        ("Maheshbhai", "2026-11-30"): 50000,
    }


def test_due_items_and_summary(conn):
    items = reminders.due_items(conn, TODAY)
    assert [(i["buyer"], i["status"]) for i in items] == [("Rameshbhai", "today"), ("Kantaben", "upcoming")]
    assert reminders.summary_text(items) == "આજે 1 ઉઘરાણી આવવાની છે, કુલ ₹1,20,000. આવતા 3 દિવસમાં 1 ઉઘરાણી, કુલ ₹75,000."


def test_overdue_comes_first_in_summary(conn):
    items = reminders.due_items(conn, date(2026, 11, 5))
    assert [i["status"] for i in items] == ["overdue", "overdue"]
    assert reminders.summary_text(items) == "2 ઉઘરાણીની મુદત વીતી ગઈ છે, કુલ ₹1,95,000."


def test_nothing_due():
    assert reminders.summary_text([]) == "આજે કોઈ ઉઘરાણી બાકી નથી."


@pytest.mark.parametrize("today, when", [
    (date(2026, 10, 20), "31 ઑક્ટોબરના રોજ છે"),
    (TODAY, "આજે છે"),
    (date(2026, 11, 3), "31 ઑક્ટોબરના રોજ હતી"),
])
def test_buyer_reminder_wording(conn, today, when):
    reminder = reminders.buyer_reminder(conn, "Rameshbhai", today)
    assert reminder["amount"] == 120000
    assert reminder["say"] == f"નમસ્તે Rameshbhai, ₹1,20,000ની ચુકવણીની તારીખ {when}. અનુકૂળતાએ મોકલી આપશો. આભાર."


def test_fully_paid_buyer_gets_no_reminder(conn):
    add(conn, "Kantaben e 75,000 jama karavya", on=TODAY)
    assert reminders.buyer_reminder(conn, "Kantaben", TODAY) is None


def test_summary_and_reminder_endpoints(conn):
    client = TestClient(main.app)

    body = client.get("/summary", params={"today": "2026-10-31"}).json()
    assert [i["buyer"] for i in body["items"]] == ["Rameshbhai", "Kantaben"]
    assert client.get(body["audio"]).content == ("RIFF" + body["say"]).encode()

    # spelling variant from STT still finds the buyer
    reminder = client.get("/reminders/રમેશભાઈ", params={"today": "2026-10-31"}).json()
    assert (reminder["buyer"], reminder["amount"]) == ("Rameshbhai", 120000)
    assert reminder["audio"].startswith("/audio/")

    assert client.get("/reminders/Nobodybhai").status_code == 404


def test_seed_matches_its_summary_and_only_fills_an_empty_ledger(tmp_path):
    conn = db.connect(str(tmp_path / "seed.db"))
    assert seed(conn, today=TODAY) == 5
    assert seed(conn, today=TODAY) == 0
    items = reminders.due_items(conn, TODAY)
    assert reminders.summary_text(items) == "આજે 1 ઉઘરાણી આવવાની છે, કુલ ₹1,20,000. આવતા 3 દિવસમાં 1 ઉઘરાણી, કુલ ₹75,000."


def test_balances_show_the_oldest_unpaid_due_date(conn):
    rows = {r["buyer"]: (r["balance"], r["earliest_due"]) for r in reminders.balances(conn)}
    # Rameshbhai's Oct 21 bill is paid off, so his next due date is Oct 31
    assert rows["Rameshbhai"] == (120000, "2026-10-31")
    add(conn, "Kantaben e 75,000 jama karavya", on=TODAY)
    assert {r["buyer"]: r["earliest_due"] for r in reminders.balances(conn)}["Kantaben"] is None
