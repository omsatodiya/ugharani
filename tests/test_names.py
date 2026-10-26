import pytest

from ugharani.names import match, normalize

SAME = [
    ("Rameshbhai", "રમેશભાઈ"),
    ("રામેશભાઈ", "રમેશભાઈ"),  # STT vowel slip from the romanised round trip
    ("Raameshbhai", "Rameshbhai"),
    ("Ramesh bhai", "Rameshbhai"),
    ("Ramesh", "Rameshbhai"),
    ("Kantaben", "કાંતાબેન"),
    ("Rajnikant", "રજનીકાંત"),
    ("Patel Sheth", "પટેલ શેઠ"),
    ("Jayeshbhai", "જયેશભાઈ"),
    ("Chhaganbhai", "Chaganbhai"),
]
DIFFERENT = [
    ("Rameshbhai", "Sureshbhai"),
    ("Rameshbhai", "મહેશભાઈ"),
    ("Kantaben", "Kantilal"),
    ("Rajubhai", "Rajeshbhai"),
]


def test_normalize():
    assert normalize("રમેશભાઈ") == normalize("Rameshbhai") == "ramesh"


@pytest.mark.parametrize("a,b", SAME)
def test_same_buyer(a, b):
    assert match(a, [b]) == b


@pytest.mark.parametrize("a,b", DIFFERENT)
def test_different_buyer(a, b):
    assert match(a, [b]) is None


def test_picks_the_right_buyer_among_many():
    known = ["Sureshbhai", "રમેશભાઈ", "Mahesh"]
    assert match("Rameshbhai", known) == "રમેશભાઈ"
