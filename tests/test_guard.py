"""The owner's limits, enforced on every sentence the agent is about to say."""

from datetime import date

import pytest

from ugharani import guard

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
