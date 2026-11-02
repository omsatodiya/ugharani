"""The call agent's prompt and notes, with Gemini mocked out."""

from datetime import date

import pytest

from ugharani import agent, followup, llm

TODAY = date(2026, 11, 1)
CUSTOMER = {"name": "રમેશભાઈ", "firm": "શ્રીજી હાર્ડવેર", "city": "જેતપુર", "deals_with": "મનીષભાઈ",
            "balance": 120000, "earliest_due": "2026-11-01"}


@pytest.fixture
def settings(tmp_path):
    from ugharani import db
    conn = db.connect(str(tmp_path / "x.db"))
    yield followup.get_settings(conn)
    conn.close()


def test_opening_names_the_business_and_says_it_records(settings):
    line = agent.opening(settings, CUSTOMER)
    assert line.startswith("નમસ્તે, રમેશભાઈ બોલો છો?")
    assert "જીનિયસ પોલીપ્લાસ્ટ, ગોંડલથી" in line and "રેકોર્ડ" in line


def test_prompt_carries_dues_contacts_and_rules(settings):
    p = agent.system_prompt(settings, CUSTOMER, TODAY)
    assert "₹1,20,000" in p and "due today" in p and "મનીષભાઈ" in p and "શ્રીજી હાર્ડવેર" in p
    assert "large amount" not in p  # under ₹2,00,000
    big = agent.system_prompt(settings, {**CUSTOMER, "balance": 350000, "earliest_due": "2026-10-20"}, TODAY)
    assert "large amount" in big and "12 days ago" in big


def test_prompt_mentions_a_broken_promise(settings):
    last = {"promised_date": "2026-10-28", "promised_amount": 60000}
    assert "₹60,000" in agent.system_prompt(settings, CUSTOMER, TODAY, last)


def test_split_end_cleans_numbers_and_spots_the_hang_up():
    assert agent.split_end("તો ₹૬૦,૦00 RTGS, બરાબર ને?") == ("તો ₹60,000 RTGS, બરાબર ને?", False)
    assert agent.split_end("સારું, આભાર. આવજો. <END>") == ("સારું, આભાર. આવજો.", True)


async def _fake_json(system, history, schema):
    return {"outcome": "promised", "promised_amount": 60000, "promised_date": "not a date",
            "summary": "શનિવારે ૬૦,૦૦૦ RTGS"}


def test_notes_are_cleaned(settings, monkeypatch):
    import asyncio
    monkeypatch.setattr(llm, "generate_json", _fake_json)
    out = asyncio.run(agent.notes(settings, CUSTOMER, [{"who": "customer", "text": "શનિવારે"}], TODAY))
    assert out["summary"] == "શનિવારે 60,000 RTGS" and out["promised_date"] is None


def test_hindi_is_recognised_even_in_gujarati_script(settings):
    from ugharani import agent as a
    said = lambda text: [{"who": "agent", "text": "..."}, {"who": "customer", "text": text}]
    # as Gnani's Gujarati recognition wrote a Hindi speaker on a real call
    assert a.speaks_hindi(said("अभी થોડા tight ચલ રહ્યા છે, અગલે સોમવાર કો 50,000 ભેજ દૂંગા."))
    assert a.speaks_hindi(said("બાકી કા મહીને કે આખિર તક કર દૂંગા."))
    assert not a.speaks_hindi(said("હમણાં થોડી તંગી છે, આવતા સોમવારે 50,000 મોકલી દઈશ."))
    assert not a.speaks_hindi(said("હા બોલો."))

    customer = {"name": "રમેશભાઈ", "balance": 100000, "earliest_due": "2026-11-01"}
    _, convo = a.for_gemini(settings, customer, said("બાકી કા મહીને કે આખિર તક કર દૂંગા."), date(2026, 11, 3))
    assert convo[-1]["text"].endswith(a.HINDI_NOW)  # the note rides on their latest turn
    _, convo = a.for_gemini(settings, customer, said("હા બોલો."), date(2026, 11, 3))
    assert convo[-1]["text"] == "હા બોલો."
