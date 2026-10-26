from datetime import date

import pytest

from ugharani.extract import parse

TODAY = date(2026, 10, 26)

# (transcript, kind, buyer, amount, due_days)
CASES = [
    # Prisma output from the smoke test, plus a due date
    ("રમેશભાઈ ને ₹2,40,000 નું માલ આપ્યું, 60 દિવસ", "credit", "રમેશભાઈ", 240000, 60),
    ("રમેશભાઈને ₹2,40,000 નો માલ આપ્યો, સાઠ દિવસ", "credit", "રમેશભાઈ", 240000, 60),
    ("સુરેશભાઈ ને બે લાખ ચાળીસ હજાર નું માલ આપ્યું, બે મહિના", "credit", "સુરેશભાઈ", 240000, 60),
    ("મહેશભાઈ ને ₹૫૦,૦૦૦ નો માલ, આવતા મહિને", "credit", "મહેશભાઈ", 50000, 30),
    # romanised / Hinglish, as typed or spoken
    ("Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas", "credit", "Rameshbhai", 240000, 60),
    ("Rameshbhai ne 2.4 lakh nu maal aapyu, 60 divas", "credit", "Rameshbhai", 240000, 60),
    ("Kantaben ne 75,000 rupiya nu kapad, ek mahino", "credit", "Kantaben", 75000, 30),
    ("Mahesh ne 1,20,000 nu maal aapyu, 45 din", "credit", "Mahesh", 120000, 45),
    ("Patel sheth ko 3 lakh ka maal diya, dodh mahina", "credit", "Patel Sheth", 300000, 45),
    ("Rameshbhai ne 2 lakh, 60 divas", "credit", "Rameshbhai", 200000, 60),
    # payments received
    ("રમેશભાઈએ ₹50,000 જમા કરાવ્યા", "payment", "રમેશભાઈ", 50000, None),
    ("Rameshbhai e pachaas hazaar aapya", "payment", "Rameshbhai", 50000, None),
    ("Sureshbhai na 1 lakh malya", "payment", "Sureshbhai", 100000, None),
]


@pytest.mark.parametrize("text,kind,buyer,amount,due_days", CASES)
def test_parse(text, kind, buyer, amount, due_days):
    e = parse(text, today=TODAY)
    assert (e.kind, e.buyer, e.amount, e.due_days) == (kind, buyer, amount, due_days)
    assert e.complete


def test_due_date_is_computed_from_today():
    assert parse("Rameshbhai ne 2.4 lakh, 60 divas", today=TODAY).due_date == date(2026, 12, 25)


def test_saath_meaning_with_is_not_a_number():
    e = parse("Rameshbhai saath vaat thai, 2 lakh nu maal aapyu, 30 divas", today=TODAY)
    assert (e.amount, e.due_days) == (200000, 30)


def test_missing_fields_are_reported():
    e = parse("Rameshbhai ne maal aapyu", today=TODAY)
    assert e.missing == ["amount", "due_date"]
    assert not e.complete
