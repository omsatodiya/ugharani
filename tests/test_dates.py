"""Spoken dates as spans (earliest, latest). Today is Wednesday 4 November 2026."""

from datetime import date

import pytest

from ugharani import dates

TODAY = date(2026, 11, 4)
D = lambda m, d, y=2026: date(y, m, d)  # noqa: E731


@pytest.mark.parametrize("text, want", [
    ("15 તારીખે આપીશ", [(D(11, 15), D(11, 15))]),
    ("3 તારીખે", [(D(12, 3), D(12, 3))]),                       # the 3rd has gone: next month's
    ("5 ડિસેમ્બરે", [(D(12, 5), D(12, 5))]),
    ("10 ઑક્ટોબરનું બિલ", [(D(10, 10), D(10, 10))]),            # a recent past date: a bill's
    ("5 જાન્યુઆરીએ", [(D(1, 5, 2027), D(1, 5, 2027))]),
    ("કાલે મોકલી દઈશ", [(D(11, 5), D(11, 5))]),
    ("પરમ દિવસે", [(D(11, 6), D(11, 6))]),
    ("આજે સાંજે", [(TODAY, TODAY)]),
    ("શુક્રવારે", [(D(11, 6), D(11, 6))]),
    ("આવતા સોમવારે", [(D(11, 9), D(11, 9))]),
    ("બુધવારે", [(D(11, 11), D(11, 11))]),                       # said on a Wednesday: next week's
    ("અગલે સોમવાર કો", [(D(11, 9), D(11, 9))]),
    ("આવતા અઠવાડિયે", [(D(11, 9), D(11, 15))]),
    ("આ અઠવાડિયામાં", [(TODAY, D(11, 8))]),
    ("અગલે હફ્તે", [(D(11, 9), D(11, 15))]),
    ("આવતા મહિને", [(D(12, 1), D(12, 31))]),
    ("મહિનાના અંતે", [(TODAY, D(11, 30))]),
    ("20 દિવસમાં", [(TODAY, D(11, 24))]),
    ("ત્રીસ દિવસમાં", [(TODAY, D(12, 4))]),
    ("ત્રણ અઠવાડિયામાં", [(TODAY, D(11, 25))]),
    ("બે મહિનામાં", [(TODAY, D(1, 3, 2027))]),
    ("એક મહિના પછી", [(D(12, 4), dates.OPEN)]),
    # bounded by the word after: after (no end), before, by
    ("15 તારીખ પછી", [(D(11, 15), dates.OPEN)]),
    ("15 તારીખે પછી", [(D(11, 15), dates.OPEN)]),
    ("20 તારીખ સુધીમાં", [(TODAY, D(11, 20))]),
    ("આવતા અઠવાડિયા પછી", [(D(11, 15), dates.OPEN)]),
    # festivals (Diwali 2026: 8 November)
    ("દિવાળી પછી", [(D(11, 8), dates.OPEN)]),
    ("દિવાળી કે બાદ", [(D(11, 8), dates.OPEN)]),
    ("દિવાળી પહેલાં", [(TODAY, D(11, 8))]),
    ("દિવાળીએ", [(D(11, 8), D(11, 8))]),
    ("દિવાળીના દિવસે", [(D(11, 8), D(11, 8))]),
    ("લાભ પાંચમ પછી", [(D(11, 14), dates.OPEN)]),
    ("દેવ દિવાળી સુધી", [(TODAY, D(11, 24))]),
    ("ઉત્તરાયણ પર", [(D(1, 14, 2027), D(1, 14, 2027))]),
    ("હોળી પહેલાં", [(TODAY, D(3, 22, 2027))]),
    ("દિવાળીની શુભકામનાઓ", []),                                   # named, not as a date
    ("50 હજાર મોકલીશ", []),                                      # money, not a date
    ("હા જી, એક વાત કહું?", []),
])
def test_spans(text, want):
    assert dates.spans(text, TODAY) == want


def test_a_festival_with_no_known_date_ahead_is_open_ended():
    assert dates.spans("દિવાળી પછી", date(2029, 11, 1)) == [(date(2029, 11, 1), dates.OPEN)]
