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


def test_the_opening_is_two_turns_like_a_person_calling(settings):
    assert agent.greeting(CUSTOMER) == "હેલો રમેશભાઈ?"  # (no comma: Timbre pauses at commas)
    # (by default she says she's automatic)
    assert agent.intro(settings) == "હા નમસ્તે. હું જીનિયસ પોલીપ્લાસ્ટની ઓટોમેટિક આસિસ્ટન્ટ કાવ્યા બોલું છું."
    assert agent.intro(settings, answered_yes=False) == "નમસ્તે. હું જીનિયસ પોલીપ્લાસ્ટની ઓટોમેટિક આસિસ્ટન્ટ કાવ્યા બોલું છું."
    assert "automatic assistant" in agent.system_prompt(settings, CUSTOMER, TODAY)


def test_the_owner_can_switch_the_disclosure_off(settings, tmp_path):
    from ugharani import db
    conn = db.connect(str(tmp_path / "x.db"))
    off = followup.update_settings(conn, {"disclose_ai": False})
    assert off["disclose_ai"] is False
    assert agent.intro(off) == "હા નમસ્તે. હું કાવ્યા બોલું છું જીનિયસ પોલીપ્લાસ્ટમાંથી."
    assert "automatic assistant" not in agent.system_prompt(off, CUSTOMER, TODAY)
    conn.close()


def test_prompt_carries_dues_contacts_and_rules(settings):
    p = agent.system_prompt(settings, CUSTOMER, TODAY)
    assert "₹1,20,000" in p and "due today" in p and "મનીષભાઈ" in p and "શ્રીજી હાર્ડવેર" in p
    overdue = agent.system_prompt(settings, {**CUSTOMER, "earliest_due": "2026-10-20"}, TODAY)
    assert "12 days ago" in overdue
    # her limits, as dates: 7 days for the whole payment, 15 for the last part
    assert "up to 8 નવેમ્બર" in p and "comes by 16 નવેમ્બર" in p
    assert "એ બાબતે હું શેઠને વાત કરી દઉં છું, એ તમને ફોન કરશે." in p and "WhatsApp" in p
    bills = [{"amount": 50000, "due_date": "2026-10-20"}, {"amount": 70000, "due_date": "2026-11-01"}]
    assert "₹50,000 (due 20 ઑક્ટોબર), ₹70,000 (due 1 નવેમ્બર)" in agent.system_prompt(
        settings, {**CUSTOMER, "bills": bills}, TODAY)


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


def _notes(monkeypatch, settings, said: list[tuple[str, str]], **wrote):
    import asyncio

    async def fake(system, history, schema):
        return {"outcome": "promised", "summary": "વાયદો", "owner_action": None, **wrote}
    monkeypatch.setattr(llm, "generate_json", fake)
    history = [{"who": who, "text": text} for who, text in said]
    return asyncio.run(agent.notes(settings, CUSTOMER, history, date(2026, 11, 4)))  # a Wednesday


def test_notes_keep_what_was_said_in_the_call(settings, monkeypatch):
    out = _notes(monkeypatch, settings, [("customer", "શનિવારે 60 હજાર મોકલી દઈશ."),
                                         ("agent", "તો શનિવારે ₹60,000, બરાબર ને?"), ("customer", "હા.")],
                 promised_amount=60000, promised_date="2026-11-07")
    assert (out["promised_amount"], out["promised_date"], out["checks"]) == (60000, "2026-11-07", [])
    # the whole balance, a range's day, half, "today"
    out = _notes(monkeypatch, settings, [("customer", "આવતા અઠવાડિયે બધું આપી દઈશ.")],
                 promised_amount=120000, promised_date="2026-11-09")
    assert out["checks"] == [] and out["promised_date"] == "2026-11-09"
    out = _notes(monkeypatch, settings, [("customer", "અડધા કાલે, અડધા સોમવારે.")],
                 promised_amount=60000, promised_date="2026-11-05")
    assert out["checks"] == [] and out["promised_amount"] == 60000
    out = _notes(monkeypatch, settings, [("customer", "હમણાં જ RTGS કરું છું.")],
                 promised_amount=120000, promised_date="2026-11-04")
    assert out["checks"] == []


def test_notes_not_backed_by_the_call_go_to_the_owner(settings, monkeypatch):
    out = _notes(monkeypatch, settings, [("customer", "શનિવારે 60 હજાર મોકલી દઈશ.")],
                 promised_amount=70000, promised_date="2026-11-25", owner_action="સ્ટેટમેન્ટ મોકલવું")
    assert out["promised_amount"] is None and out["promised_date"] is None  # (no false promise holds calls back)
    assert out["checks"] == ["નોંધ તપાસો: ₹70,000 ની રકમ ફોનમાં સંભળાઈ નથી.",
                             "નોંધ તપાસો: વાયદાની તારીખ 25 નવેમ્બર ફોનમાં સંભળાઈ નથી."]
    assert out["owner_action"] == " ".join(["સ્ટેટમેન્ટ મોકલવું", *out["checks"]])
    # a payment already made: its (past) date isn't a promise to check
    out = _notes(monkeypatch, settings, [("customer", "મેં તો 30 ઑક્ટોબરે ₹1,20,000 NEFT કરી દીધા.")],
                 outcome="paid", promised_amount=120000, promised_date="2026-10-30")
    assert out["checks"] == [] and out["promised_date"] == "2026-10-30"


def test_hindi_is_recognised_even_in_gujarati_script(settings):
    from ugharani import agent as a
    said = lambda text: [{"who": "agent", "text": "..."}, {"who": "customer", "text": text}]
    # as Gnani's Gujarati recognition wrote a Hindi speaker on a real call
    assert a.speaks_hindi(said("अभी થોડા tight ચલ રહ્યા છે, અગલે સોમવાર કો 50,000 ભેજ દૂંગા."))
    assert a.speaks_hindi(said("બાકી કા મહીને કે આખિર તક કર દૂંગા."))
    assert not a.speaks_hindi(said("હમણાં થોડી તંગી છે, આવતા સોમવારે 50,000 મોકલી દઈશ."))
    assert not a.speaks_hindi(said("હા બોલો."))
    assert a.speaks_hindi(said("ઠીક હૈ, દસ તારીખ કો ભેજ દેંગે."))
    assert a.speaks_hindi(said("કલ શામ કો કર દૂંગા."))
    assert a.speaks_hindi(said("હમારા પેમેન્ટ અભી ચલ રહા હૈ."))

    customer = {"name": "રમેશભાઈ", "balance": 100000, "earliest_due": "2026-11-01"}
    _, convo = a.for_gemini(settings, customer, said("બાકી કા મહીને કે આખિર તક કર દૂંગા."), date(2026, 11, 3))
    assert convo[-1]["text"].endswith(a.HINDI_NOW)  # the note rides on their latest turn
    _, convo = a.for_gemini(settings, customer, said("હા બોલો."), date(2026, 11, 3))
    assert convo[-1]["text"] == "હા બોલો."


@pytest.mark.parametrize("text", [
    "WhatsApp પર statement મોકલો.",       # "પર": Gujarati too
    "ઠીક, બોલો.",                          # "ઠીક છે" is Gujarati
    "હમ, તક મળે તો આપી દઈશ.",
    "કાં તો શનિવારે, કા સોમવારે.",          # Kathiyawadi "or"
    "એની સાથ વાત કરી લેજો.",
    "હાં, નહીં, જી.",
    "બીસ દિન બાદ પેમેન્ટ કરી દેજો.",        # mixed, a Gujarati verb: stays Gujarati
    "નમસ્તે, હા બોલિએ.",                   # polite Gujarati (found by the conversation suite)
])
def test_words_gujarati_shares_with_hindi_are_no_sign_of_hindi(text):
    said = [{"who": "agent", "text": "..."}, {"who": "customer", "text": text}]
    assert not agent.speaks_hindi(said), text


def test_a_call_back_is_told_apart_from_a_hold_and_noted_for_gemini(settings):
    for text in ["બે મિનિટ પછી ફોન કરો", "પછી ફોન કરજો", "સાંજે ફોન કરજો", "હું સામેથી ફોન કરું છું",
                 "થોડી વાર પછી કૉલ કરો", "અત્યારે હું ડ્રાઇવ કરું છું", "busy છું, કાલે ફોન કરજો",
                 "હમણાં વાત નહીં થાય", "बाद में फोन करो", "અભી બાત નહીં હો પાએગી, શામ કો ફોન કરના"]:
        assert agent.asks_for_callback(text), text
    for text in ["એક મિનિટ", "મેં ગઈ કાલે ફોન કર્યો હતો", "શુક્રવારે પેમેન્ટ કરી દઈશ", "હા બોલો",
                 "ફોન ચાલુ રાખો", "પછી આપીશ"]:
        assert not agent.asks_for_callback(text), text

    customer = {"name": "રમેશભાઈ", "balance": 100000, "earliest_due": "2026-11-01"}
    said = [{"who": "agent", "text": "..."}, {"who": "customer", "text": "બે મિનિટ પછી ફોન કરો"}]
    _, convo = agent.for_gemini(settings, customer, said, date(2026, 11, 3))
    assert convo[-1]["text"] == f"બે મિનિટ પછી ફોન કરો\n{agent.CALLBACK_NOW}"
    assert said[-1]["text"] == "બે મિનિટ પછી ફોન કરો"  # (the transcript itself is unchanged)
    hindi = [{"who": "agent", "text": "..."}, {"who": "customer", "text": "અભી બાત નહીં હો પાએગી, શામ કો ફોન કરના"}]
    _, convo = agent.for_gemini(settings, customer, hindi, date(2026, 11, 3))
    assert convo[-1]["text"].endswith(f"{agent.HINDI_NOW}\n{agent.CALLBACK_NOW}")


def test_a_yes_to_her_confirmation_gets_a_goodbye_note(settings):
    customer = {"name": "રમેશભાઈ", "balance": 120000, "earliest_due": "2026-11-01"}
    asked = {"who": "agent", "text": "સારું. તો ચેક ₹1,20,000 નો છે, અને શુક્રવારે કુરિયર કરાવી દેશો, બરાબર ને?"}
    for yes in ["હા, બરાબર છે. બીજું કંઈ કામ હતું?", "હા.", "જી", "पाक्का", "ઠીક છે"]:
        _, convo = agent.for_gemini(settings, customer, [asked, {"who": "customer", "text": yes}], TODAY)
        assert convo[-1]["text"].endswith(agent.CONFIRMED_NOW) == (yes != "पाक्का"), yes
    for not_yes in ["ના, શનિવારે.", "એક મિનિટ"]:
        _, convo = agent.for_gemini(settings, customer, [asked, {"who": "customer", "text": not_yes}], TODAY)
        assert agent.CONFIRMED_NOW not in convo[-1]["text"]
    question = {"who": "agent", "text": "₹1,20,000 બાકી છે, ક્યારે મોકલશો?"}  # (not a confirmation)
    _, convo = agent.for_gemini(settings, customer, [question, {"who": "customer", "text": "હા, શુક્રવારે."}], TODAY)
    assert agent.CONFIRMED_NOW not in convo[-1]["text"]
