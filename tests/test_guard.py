"""The owner's limits, enforced on every sentence the agent is about to say."""

from datetime import date

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
    assert check("તો 18 તારીખે, બરાબર ને?") is None  # 14 days: a split may run this far
    assert check("તો 25 તારીખે, બરાબર ને?")  # 21 days
    assert check("તો 2 ડિસેમ્બરે બાકીના, બરાબર ને?")
    assert check("તો 3 તારીખે, બરાબર ને?")  # the 3rd of next month
    assert check("તો 30 દિવસમાં કરી દેજો.")
