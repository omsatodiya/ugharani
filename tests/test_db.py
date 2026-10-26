from datetime import date

import pytest

from ugharani import db
from ugharani.extract import parse

TODAY = date(2026, 10, 26)


def test_balance_is_credits_minus_payments(tmp_path):
    conn = db.connect(str(tmp_path / "ledger.db"))
    for text in [
        "Rameshbhai ne 2,40,000 nu maal aapyu, 60 divas",
        "Rameshbhai e 50,000 jama karavya",
        "Kantaben ne 75,000 nu kapad, 30 divas",
    ]:
        db.add_entry(conn, parse(text, today=TODAY), text, today=TODAY)

    rows = {r["buyer"]: (r["balance"], r["earliest_due"]) for r in db.balances(conn)}
    assert rows == {"Rameshbhai": (190000, "2026-12-25"), "Kantaben": (75000, "2026-11-25")}


def test_incomplete_entry_is_rejected(tmp_path):
    conn = db.connect(str(tmp_path / "ledger.db"))
    with pytest.raises(ValueError):
        db.add_entry(conn, parse("Rameshbhai ne maal aapyu"), "Rameshbhai ne maal aapyu")
