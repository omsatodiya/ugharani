"""The owner's limits, enforced on every sentence the agent is about to say."""

import asyncio
from datetime import date

import pytest

from ugharani import guard, llm

TODAY = date(2026, 11, 4)
SETTINGS = {"owner_name": "શેઠ", "promise_days": 7, "split_days": 15}
CUSTOMER = {"name": "રમેશભાઈ", "balance": 120000, "bills": [{"amount": 50000, "due_date": "2026-10-20"},
                                                           {"amount": 70000, "due_date": "2026-11-01"}]}


def check(text, said=()):
    history = [{"who": "customer", "text": t} for t in said]
    return guard.problem(text, SETTINGS, CUSTOMER, history, TODAY)


def test_ordinary_lines_pass():
    for line in ["જી. ₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?", "સારું. કઈ તારીખ ગણું?",
                 "તો 10 તારીખે RTGS, બરાબર ને?", "₹50,000 વાળું બિલ 20 ઑક્ટોબરનું છે.",
                 "બરાબર. સોમવારે ચેક, બરાબર ને?", "હા જી, વાંધો નહીં.", "તો ભાવનગર વાળી બ્રાન્ચમાંથી?"]:
        assert check(line) is None, line


def test_never_offers_discounts_interest_threats_or_rates():
    for line in ["તો 2% ડિસ્કાઉન્ટ આપી દઈશું.", "નહીં તો વ્યાજ લાગશે.", "પછી કોર્ટમાં જવું પડશે.",
                 "તો માલ બંધ કરવો પડશે.", "1 ઇંચ ટીનો ભાવ ₹45 છે."]:
        assert check(line), line


def test_handing_a_topic_over_may_name_it():
    assert check("ડિસ્કાઉન્ટ બાબતે શેઠ તમને ફોન કરશે.") is None
    assert check("ભાવ માટે તમે મનીષભાઈ સાથે વાત કરી લેજો.") is None


def test_amounts_must_be_on_a_bill_or_said_by_the_customer():
    assert check("₹75,000 બાકી છે.")  # on no bill
    assert check("તો શનિવારે ₹60,000, બરાબર ને?", said=["શનિવારે 60 હજાર આપીશ"]) is None
    assert check("અને બાકીના ₹60,000 ક્યારે?", said=["શનિવારે 60 હજાર આપીશ"]) is None  # what's left
    assert check("તો ₹40,000 અત્યારે?", said=["દોઢ લાખ નહીં થાય"])


def test_no_date_past_the_owners_limit():
    assert check("તો 18 તારીખે, બરાબર ને?", said=["10 તારીખે 50 હજાર આપીશ"]) is None  # a split's last part
    assert check("તો 18 તારીખે બાકીના, બરાબર ને?") is None
    assert check("તો 25 તારીખે, બરાબર ને?")  # 21 days
    assert check("તો 2 ડિસેમ્બરે બાકીના, બરાબર ને?")
    assert check("તો 3 તારીખે, બરાબર ને?")  # the 3rd of next month
    assert check("તો 30 દિવસમાં કરી દેજો.")


# ---------- found on 2026-11-15 and fixed in phase 1; and lines that must stay allowed ----------

MUST_BLOCK = [
    # amounts in words, on no bill
    pytest.param("તો 75 હજાર મોકલી દેજો.", id="words-75-hazar"),
    pytest.param("એક લાખ દસ હજાર બાકી છે.", id="words-lakh-das-hazar"),
    pytest.param("સવા લાખનું પેમેન્ટ ક્યારે આવશે?", id="words-sava-lakh"),
    # number words before a duration
    pytest.param("ત્રીસ દિવસમાં આપજો.", id="words-trees-divas"),
    pytest.param("ત્રણ અઠવાડિયામાં કરી દેજો.", id="words-tran-athvadiya"),
    pytest.param("બે મહિનામાં કરી દેજો.", id="words-be-mahina"),
    # relative and open-ended dates
    pytest.param("બાકીના આવતા મહિને આપજો, બરાબર ને?", id="next-month"),
    pytest.param("એક મહિના પછી આપજો.", id="after-a-month"),
    pytest.param("ઠીક હૈ, અગલે મહિને ભેજ દીજિએ.", id="hindi-next-month"),
    pytest.param("દિવાળી પછી આપી દેજો.", id="after-diwali"),
    pytest.param("ઉત્તરાયણ પર કરી દેજો.", id="uttarayan"),
    # the whole amount past promise_days (7)
    pytest.param("તો 14 તારીખે ₹1,20,000, બરાબર ને?", id="full-past-7-days"),
    # discounts and waivers said other ways
    pytest.param("તમે 10% ઓછા આપજો.", id="percent-less"),
    pytest.param("થોડું ઓછું કરી આપીશું.", id="ochhu-kari"),
    pytest.param("બાકીનું માફ કરી દઈશું.", id="maaf"),
    pytest.param("ઠીક હૈ, થોડા કમ કર દેંગે.", id="hindi-kam-kar"),
    pytest.param("બે ટકા ઓછા આપજો.", id="words-percent"),
    pytest.param("5% કેશ ડિસ્કાઉન્ટ મળશે.", id="cash-discount"),
    pytest.param("વ્યાજ માફ કરી દઈશું.", id="interest-waived"),
    pytest.param("ઓછા ભરશો તો ચાલશે.", id="ochha-bharsho"),
    # interest, penalties, threats, supply, rates
    pytest.param("લેટ પેમેન્ટ ચાર્જ લાગશે.", id="late-charge"),
    pytest.param("નહીં તો પેનલ્ટી લાગશે.", id="penalty"),
    pytest.param("₹1,25,000 થયા છે વ્યાજ સાથે.", id="with-interest"),
    pytest.param("વરના કેસ કરના પડેગા.", id="hindi-case"),
    pytest.param("હમારે વકીલ સે બાત કરની પડેગી.", id="lawyer-with-handover-words"),
    pytest.param("કોર્ટ બાબતે શેઠ તમને ફોન કરશે.", id="court-handed-over"),
    pytest.param("માલ બંધ કરી દઈશું.", id="stop-goods"),
    pytest.param("હવે પછી ઓર્ડર નહીં મળે.", id="no-more-orders"),
    pytest.param("પછી માલ નહીં મળે.", id="no-more-goods"),
    pytest.param("તમારું નામ બ્લેકલિસ્ટમાં જશે.", id="blacklist"),
    pytest.param("પોલીસ કમ્પ્લેઈન કરવી પડશે.", id="police"),
    pytest.param("આ PVC પાઇપનો રેટ ₹120 છે.", id="rate"),
    # amounts and dates
    pytest.param("તો ₹30,000 હમણાં, બરાબર ને?", id="amount-nobody-said"),
    pytest.param("26 તારીખે બાકીના ₹70,000, બરાબર ને?", id="rest-past-15-days"),
    pytest.param("તો 2 તારીખે, બરાબર ને?", id="2nd-next-month"),
    pytest.param("આવતા મહિનાની 5 તારીખે આપજો.", id="5th-of-next-month"),
    pytest.param("ત્રણ મહિનાના હપ્તા કરી દઈએ.", id="three-months"),
    pytest.param("પંદર દિવસ પછી આપજો.", id="after-15-days-whole"),
    pytest.param("next month payment કરી દેજો.", id="english-next-month"),
    pytest.param("જાન્યુઆરીમાં આપજો.", id="month-alone"),
    pytest.param("ડિસેમ્બરમાં કરી દેજો.", id="next-month-by-name"),
    # found by scripts/guard_fuzz.py
    pytest.param("બાવીસ તારીખ નક્કી રાખો ફાઇનલ પેમેન્ટ માટે.", id="fuzz-day-in-words"),
    pytest.param("સંપૂર્ણ એક લાખ વીસ હજાર રૂપિયા તેર તારીખે ક્લિયર કરી આપો.", id="fuzz-whole-13th-words"),
    pytest.param("અઠ્ઠાવન હજાર રૂપિયા પેન્ડિંગ બતાવે છે.", id="fuzz-58-hazar"),
    pytest.param("વાલ્વની પ્રાઇસ લિસ્ટ પ્રમાણે અઢાર રૂપિયા એક નંગ પડે.", id="fuzz-price-per-piece"),
    pytest.param("માર્કેટમાં તમારી શાખ બગાડવી પડશે.", id="fuzz-spoil-name"),
    pytest.param("ટ્રક અહિયાં જ રોકી દીધી છે.", id="fuzz-truck-stopped"),
    pytest.param("નવો ઓર્ડર ફેક્ટરીમાંથી ડિસ્પેચ નહીં થાય.", id="fuzz-no-dispatch"),
    pytest.param("જૂનું બિલ ક્લિયર નહીં થાય ત્યાં સુધી નવા ઓર્ડર પર હોલ્ડ છે.", id="fuzz-orders-on-hold"),
    pytest.param("સમય પૂરો થશે એટલે લેટ ફી લાગુ પડી જશે.", id="fuzz-late-fee"),
    pytest.param("પછી ગમે ત્યારે અનુકૂળતા મુજબ મોકલાવી દેજો.", id="fuzz-whenever"),
    pytest.param("જૂના સંબંધોના ખાતામાં દસ ટકા કાપીને બાકી મોકલી દો.", id="fuzz-cut-ten-percent"),
    pytest.param("તમારું ટોટલ 1,50,000 નું બિલ બાકી છે.", id="fuzz-bare-digits"),
    pytest.param("અમારા ખાતામાં 90,000 નું પેન્ડિંગ બતાવે છે.", id="fuzz-bare-digits-2"),
    pytest.param("તમને 1,20,000 ની જગ્યાએ 1,15,000 કરી આપું?", id="fuzz-lower-total"),
    pytest.param("70,000 વાળા બિલમાં રાઉન્ડ ઓફ કરી આપીશું.", id="fuzz-round-off"),
    pytest.param("થોડું ઓછું ચૂકવશો તો પણ ચાલશે.", id="fuzz-pay-less"),
    pytest.param("કાયદાકીય પગલાં લેવા સિવાય કોઈ રસ્તો નહીં રહે.", id="fuzz-legal-steps"),
    pytest.param("પોલિસ સ્ટેશનમાં ફરિયાદ કરવી પડશે.", id="fuzz-police-spelling"),
    pytest.param("ટ્રેલર પેમેન્ટ આવે પછી જ રવાના થશે.", id="fuzz-after-payment-only"),
    pytest.param("ફેક્ટરીથી નવો ડિસ્પેચ અટકાવી દેવામાં આવશે.", id="fuzz-dispatch-held"),
    pytest.param("તમારું સપ્લાય કનેક્શન કાપવું પડશે.", id="fuzz-supply-cut"),
    # found in review (#2)
    pytest.param("બાકીનું માફ કરી દઉં, શેઠ તમને ફોન કરશે.", id="review-waiver-with-handover"),
    pytest.param("માલિકે 5% ડિસ્કાઉન્ટ આપી દીધું છે.", id="review-owner-is-no-handover"),
    pytest.param("તો 25 તારીખે ₹50,000 અને 10 નવેમ્બરે ₹70,000 આપજો.", id="review-two-date-forms"),
    pytest.param("બે-ત્રણ મહિના પછી આપજો.", id="review-range"),
    pytest.param("પંદરમી તારીખ પછી આપજો.", id="review-ordinal"),
    pytest.param("મે મહિનામાં આપજો.", id="review-may"),
    pytest.param("બીસ દિન બાદ પેમેન્ટ કરી દેજો.", id="review-hindi-din"),
    pytest.param("100,000 નું પેમેન્ટ બાકી છે.", id="review-western-grouping"),
]

MUST_PASS = [
    "તો 50 હજાર શનિવારે, બરાબર ને?",           # a bill's amount, in words
    "સારું, આવતા સોમવારે ચેક, બરાબર ને?",       # 9 November
    "તો આવતા અઠવાડિયે થઈ જશે ને?",              # within the split limit
    "બે દિવસમાં થઈ જશે ને?",
    "હા જી, એક વાત કહું?",
    "તો 10 તારીખે ₹1,20,000 RTGS, બરાબર ને?",  # the whole amount within 7 days
    "તો 10 તારીખે ₹50,000 અને 18 તારીખે ₹70,000, બરાબર ને?",  # parts, the last within 15 days
    "દિવાળીની શુભકામનાઓ.",
    "માફ કરજો, લાઇન થોડી ખરાબ છે. ફરી કહેશો?",       # sorry, not a waiver
    "સો ટકા થઈ જશે ને?",                              # "definitely"
    "100 ટકા, બરાબર ને?",
    "₹1,20,000 માંથી ₹50,000 તો આવી જશે ને?",
    "ડિસ્કાઉન્ટ બાબતે શેઠ તમને ફોન કરશે.",           # handing over
    "ઓછું-વધતું હોય તો શેઠ તમને ફોન કરશે.",
    "સાત દિવસ પછી આપી દેશો ને?",                    # 11 November
    "કાલે RTGS કરી દેશો ને?",
    "UTR નંબર હોય તો કહેજો ને.",
    "હું તમને WhatsApp પર સ્ટેટમેન્ટ મોકલાવી દઉં છું.",
    "એ માટે તમે મનીષભાઈ સાથે વાત કરી લેજો.",
    "જી, તો બાકી કા પેમેન્ટ કબ તક હો જાએગા?",
    "ઠીક હૈ, તો શુક્રવાર કો ₹1,20,000, બરાબર?",
    "હા જી, હું જીનિયસ પોલીપ્લાસ્ટની ઓટોમેટિક આસિસ્ટન્ટ છું, શેઠ વતી ફોન કર્યો છે.",
    "ભાવનગરથી માલ ગયો હતો ને?",
    "₹70,000 વાળું બિલ 1 નવેમ્બરનું છે.",
    "ઑક્ટોબરનું બિલ બાકી છે.",
    "આજે સાંજ સુધીમાં થઈ જશે?",
    "બે-ત્રણ દિવસમાં થઈ જશે ને?",
    "હું પછી ફોન કરું છું. આવજો.",
    "વ્યાજ બાબતે શેઠ તમને ફોન કરશે.",                 # the customer asked; handed over
    "તમારી ફરિયાદ નોંધી લીધી છે, મનીષભાઈ ફોન કરશે.",   # a dispute, noted
    "20 નંગ માલ ડેમેજ હતો એ બાબતે મનીષભાઈ ફોન કરશે.",
    "માલ મળ્યો નહીં હોય તો મનીષભાઈ સાથે વાત કરી લેજો.",
    "અગિયાર નવેમ્બરે પેમેન્ટ કરી દેશો ને?",
    "ભાવ બાબતે શેઠ જ નક્કી કરે, એ તમને ફોન કરશે.",
    "જો 9 નવેમ્બરે આખી રકમ ભરી દેશો તો બહુ સારું રહેશે.",   # "રકમ" is not "કમ"
    "UTR 4528 હોય તો કહેજો ને.",                              # digits that aren't money
    "તમે 12 તારીખે 50,000 અને 19 નવેમ્બરે 70,000 આપશો તો અમારી પોલિસીમાં આવી જશે.",  # policy, not police
    "ભાવ બાબતે મારી પાસે માહિતી નથી, શેઠ આવે એટલે વાત કરાવું.",
    "₹1,20,000 માંથી કાલે ₹50,000 અને 18 તારીખે બાકીના ₹70,000 આપશો ને?",  # a split, not the whole
    "આ મહિને 10 તારીખે થઈ જશે ને?",
    "તમે 50,000 નું બિલ 9 નવેમ્બરે અને 70,000 નું બિલ 16 નવેમ્બરે આપશો તો ચાલી જશે.",  # a split by bill
]


@pytest.mark.parametrize("line", MUST_BLOCK)
def test_rule_breaking_lines_are_blocked(line):
    assert check(line), line


@pytest.mark.parametrize("line", MUST_PASS)
def test_ordinary_lines_still_pass(line):
    assert check(line) is None, line


def test_the_whole_amount_only_within_promise_days():
    assert check("તો 18 તારીખે, બરાબર ને?")  # 14 days, no part payment: past the 7 days
    assert check("તો 11 તારીખે, બરાબર ને?") is None  # 7 days
    assert check("તો 14 તારીખે ₹1,20,000, બરાબર ને?", said=["10 તારીખે 50 હજાર આપીશ"])  # whole, named
    assert check("તો આવતા અઠવાડિયે થઈ જશે ને?") is None  # starts Monday the 9th: can be narrowed


def test_her_fixed_lines_always_pass():
    from ugharani import agent, followup, live
    settings = {**followup.DEFAULTS, **SETTINGS}
    fixed = [*live.FIXED_LINES, live.time_up_bye(settings), agent.greeting(CUSTOMER), agent.intro(settings),
             agent.intro(settings, False), agent.fallback_ask(CUSTOMER), guard.instead(settings, CUSTOMER)]
    for line in fixed:
        assert check(line) is None, line


# ---------- the after-call check (Gemini) ----------

@pytest.mark.real_audit
def test_audit_names_the_lines_that_broke_a_rule(monkeypatch):
    seen = {}

    async def answer(system, history, schema):
        seen["text"] = history[0]["text"]
        return {"found": [{"line": 2, "topic": "threat"}, {"line": 9, "topic": "supply"}]}  # (9: no such line)
    monkeypatch.setattr(llm, "generate_json", answer)
    found = asyncio.run(guard.audit(["સારું. કઈ તારીખ ગણું?", "બજારમાં તમારી શાખ જશે."]))
    assert found == ["threat: બજારમાં તમારી શાખ જશે."]
    assert seen["text"] == "1. સારું. કઈ તારીખ ગણું?\n2. બજારમાં તમારી શાખ જશે."  # one request, numbered


@pytest.mark.real_audit
def test_audit_failing_or_slow_finds_nothing(monkeypatch):
    monkeypatch.setattr(guard, "AUDIT_TIMEOUT", 0.1)

    async def broken(system, history, schema):
        raise llm.LLMError("HTTP 429")

    async def slow(system, history, schema):
        await asyncio.sleep(5)
    for fake in (broken, slow):
        monkeypatch.setattr(llm, "generate_json", fake)
        assert asyncio.run(guard.audit(["બજારમાં તમારી શાખ જશે."])) == []
        with pytest.raises((llm.LLMError, TimeoutError)):  # (an evaluation must see the outage)
            asyncio.run(guard.audit(["બજારમાં તમારી શાખ જશે."], strict=True))
    assert asyncio.run(guard.audit([])) == []


def test_part_payments_need_money_said_not_any_number():
    """Past 7 days only for a part payment: "UTR 4528" or her mention of a bill is no payment plan."""
    assert check("તો 18 તારીખે પેમેન્ટ કરી દેશો ને?", said=["UTR 4528 છે"])
    history = [{"who": "agent", "text": "₹50,000 વાળું બિલ 20 ઑક્ટોબરનું છે."}]
    assert guard.problem("તો 18 તારીખે પેમેન્ટ કરી દેશો ને?", SETTINGS, CUSTOMER, history, TODAY)
    assert check("તો 18 તારીખે, બરાબર ને?", said=["અત્યારે 50,000 મોકલું"]) is None


def test_half_the_balance_may_be_said_once_they_offer_half():
    settings = {"owner_name": "શેઠ", "promise_days": 7, "split_days": 15}
    customer = {"name": "રમેશભાઈ", "balance": 120000, "bills": [{"amount": 50000}, {"amount": 70000}]}
    today = date(2026, 11, 4)
    half = [{"who": "customer", "text": "અડધું પેમેન્ટ દસ દિવસમાં આપું અને બાકીનું 14 તારીખે."}]
    assert guard.problem("તો 14 નવેમ્બરે ₹60,000, બરાબર ને?", settings, customer, half, today) is None
    plain = [{"who": "customer", "text": "દસ દિવસમાં થોડું આપીશ."}]
    assert guard.problem("તો 14 નવેમ્બરે ₹60,000, બરાબર ને?", settings, customer, plain, today)
