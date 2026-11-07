"""The follow-up desk: settings, contacts, call log and who the agent calls today."""

from datetime import date, datetime, timedelta

import pytest

from ugharani import db, followup
from ugharani.extract import parse

TODAY = date(2026, 11, 10)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "ledger.db"))
    yield c
    c.close()


def credit(conn, text, days_ago=0):
    on = TODAY - timedelta(days=days_ago)
    db.add_entry(conn, parse(text, today=on), text, today=on)


def call_on(conn, customer, day, **finish):
    call_id = followup.start_call(conn, customer, 100000, "auto", when=datetime.combine(day, datetime.min.time()))
    if finish:
        followup.finish_call(conn, call_id, transcript=[], summary="", **finish)
    return call_id


def names(conn, today=TODAY):
    return [c["customer"] for c in followup.to_call(conn, today)]


def test_settings_have_defaults_and_validate(conn):
    s = followup.get_settings(conn)
    assert s["business_name"] == "Genius Polyplast" and s["repeat_every_days"] == 3 and s["auto_calls"] is True

    s = followup.update_settings(conn, {"repeat_every_days": "5", "tone": "firm", "auto_calls": False})
    assert (s["repeat_every_days"], s["tone"], s["auto_calls"]) == (5, "firm", False)
    for bad in ({"tone": "angry"}, {"nope": 1}, {"handover_amount": -1}, {"business_name": " "}):
        with pytest.raises(ValueError):
            followup.update_settings(conn, bad)


def test_customers_merge_ledger_and_contacts(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 30 દિવસ", days_ago=40)
    followup.upsert_customer(conn, "રમેશભાઈ", phone="9800000001", deals_with="મનીષભાઈ")
    followup.upsert_customer(conn, "નવા ગ્રાહક", phone="9800000009")
    by_name = {c["name"]: c for c in followup.customers(conn)}
    assert by_name["રમેશભાઈ"]["phone"] == "9800000001" and by_name["રમેશભાઈ"]["balance"] == 100000
    assert by_name["નવા ગ્રાહક"]["balance"] == 0


def test_calls_start_when_due_and_repeat(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 30 દિવસ", days_ago=30)  # due today
    credit(conn, "કાંતાબેન ને ₹50,000 નો માલ, 40 દિવસ", days_ago=30)   # due in 10 days
    assert names(conn) == ["રમેશભાઈ"]
    assert followup.to_call(conn, TODAY)[0]["reason"] == "due_today"

    followup.update_settings(conn, {"remind_after_days": 2})
    assert names(conn) == [] and names(conn, TODAY + timedelta(days=2)) == ["રમેશભાઈ"]


def test_no_promise_means_call_again_after_the_gap(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    call_on(conn, "રમેશભાઈ", TODAY, outcome="unclear")
    assert names(conn) == []
    assert names(conn, TODAY + timedelta(days=2)) == []
    assert names(conn, TODAY + timedelta(days=3)) == ["રમેશભાઈ"]


def test_a_promise_is_waited_for_then_chased(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    call_on(conn, "રમેશભાઈ", TODAY, outcome="promised", promised_date=TODAY + timedelta(days=7))
    assert names(conn, TODAY + timedelta(days=7)) == []  # promise still good
    late = followup.to_call(conn, TODAY + timedelta(days=8))
    assert [(c["customer"], c["reason"]) for c in late] == [("રમેશભાઈ", "promise_missed")]


def test_missed_call_is_retried_next_day(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    call_id = call_on(conn, "રમેશભાઈ", TODAY)
    followup.set_status(conn, call_id, "missed")
    assert names(conn) == []
    assert followup.to_call(conn, TODAY + timedelta(days=1))[0]["reason"] == "retry"


def test_owner_cases_and_switches_stop_calls(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    credit(conn, "કાંતાબેન ને ₹50,000 નો માલ, 20 દિવસ", days_ago=30)
    call_on(conn, "રમેશભાઈ", TODAY - timedelta(days=10), outcome="handover")
    assert names(conn) == ["કાંતાબેન"]

    followup.upsert_customer(conn, "કાંતાબેન", auto_call=False)
    assert names(conn) == []

    followup.upsert_customer(conn, "કાંતાબેન", auto_call=True)
    followup.update_settings(conn, {"auto_calls": False})
    assert names(conn) == []


def test_paid_up_customers_are_not_called(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    db.add_entry(conn, parse("રમેશભાઈએ ₹1,00,000 જમા કરાવ્યા", today=TODAY), "", today=TODAY)
    assert names(conn) == []


def test_finished_call_keeps_the_notes(conn):
    credit(conn, "રમેશભાઈ ને ₹1,00,000 નો માલ, 20 દિવસ", days_ago=30)
    call_id = call_on(conn, "રમેશભાઈ", TODAY)
    followup.finish_call(conn, call_id, transcript=[{"who": "customer", "text": "આવતા સોમવારે"}],
                         outcome="promised", summary="Will pay Monday", promised_amount=50000,
                         promised_date=date(2026, 11, 16))
    call = followup.get_call(conn, call_id)
    assert (call["status"], call["outcome"], call["promised_amount"]) == ("completed", "promised", 50000)
    assert call["transcript"][0]["text"] == "આવતા સોમવારે"
    with pytest.raises(ValueError):
        followup.finish_call(conn, call_id, transcript=[], outcome="threatened", summary="")


def test_calls_go_out_only_in_the_call_hours(conn):
    rules = followup.get_settings(conn)
    wed = datetime(2026, 11, 4)
    at = lambda h, m=0, day=wed: followup.calling_time(rules, day.replace(hour=h, minute=m))
    assert at(10) and at(12, 59) and at(16) and at(19, 29)
    assert not at(9, 59) and not at(13) and not at(14, 30) and not at(19, 30) and not at(21)
    assert not at(11, day=datetime(2026, 11, 8))  # Sunday
    rules = followup.update_settings(conn, {"holidays": "2026-11-04, 2026-11-10"})
    assert rules["holidays"] == "2026-11-04,2026-11-10" and not followup.calling_time(rules, wed.replace(hour=11))
    with pytest.raises(ValueError):
        followup.update_settings(conn, {"call_hours": "10-1"})
    with pytest.raises(ValueError):
        followup.update_settings(conn, {"holidays": "Diwali"})


def test_customers_carry_their_open_bills(conn):
    today = date(2026, 11, 4)
    for text in ["રમેશભાઈને 50000 નો માલ 30 દિવસ", "રમેશભાઈને 70000 નો માલ 45 દિવસ", "રમેશભાઈએ 20000 આપ્યા"]:
        db.add_entry(conn, parse(text, today), text, today)
    ramesh = next(c for c in followup.customers(conn) if c["name"] == "રમેશભાઈ")
    assert [b["amount"] for b in ramesh["bills"]] == [30000, 70000]  # paid against the oldest first


def test_part_payments_may_not_end_sooner_than_a_whole_one(conn):
    with pytest.raises(ValueError):
        followup.update_settings(conn, {"promise_days": 20})  # (split_days is 15)
    assert followup.update_settings(conn, {"promise_days": 20, "split_days": 30})["split_days"] == 30


def test_the_demo_starts_with_a_few_past_calls(conn):
    from ugharani.seed import seed
    today = date(2026, 11, 7)
    seed(conn, today)
    calls = followup.list_calls(conn)
    assert [c["outcome"] for c in calls] == ["promised", "handover", "callback", None]
    assert calls[1]["owner_action"] and calls[1]["flags"]  # the owner has something to do
    assert [q["customer"] for q in followup.to_call(conn, today)] == ["રમેશભાઈ"]  # still due today
    seed(conn, today)
    assert len(followup.list_calls(conn)) == 4  # (never twice)
