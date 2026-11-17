"""The conversation suite's own checks (scripts/agent_chat.py), on calls written by hand."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("agent_chat", Path(__file__).parent.parent / "scripts" / "agent_chat.py")
chat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chat)

OPENING = "હેલો રમેશભાઈ? નમસ્તે. હું જીનિયસ પોલીપ્લાસ્ટની ઓટોમેટિક આસિસ્ટન્ટ કાવ્યા બોલું છું."
GOOD = [("agent", OPENING), ("customer", "હા બોલો."),
        ("agent", "જી. ₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"), ("customer", "શુક્રવારે RTGS કરી દઈશ."),
        ("agent", "બરાબર. તો શુક્રવારે ₹1,20,000 RTGS, બરાબર ને?"), ("customer", "હા."),
        ("agent", "સારું, આભાર રમેશભાઈ. આવજો.")]
NOTES = {"outcome": "promised", "promised_amount": 120000, "promised_date": "2026-11-06", "checks": [],
         "owner_action": None}


def call(lines, scenario="promise", stops=(), ended=True, **notes):
    return {"scenario": scenario, "history": [{"who": w, "text": t} for w, t in lines],
            "stops": list(stops), "ended": ended, "notes": {**NOTES, **notes}}


def test_a_good_call_passes():
    assert chat.problems(call(GOOD)) == []


@pytest.mark.parametrize("bad, want", [
    (call(GOOD, stops=["she was about to talk about discount: 2% ઓછા"]), "checker stopped"),
    (call(GOOD, ended=False), "didn't end"),
    (call(GOOD, outcome="refused"), "notes say refused"),
    (call(GOOD, checks=["નોંધ તપાસો: ..."]), "notes: નોંધ તપાસો"),
    (call(GOOD[:5] + [("customer", "હા, બરાબર."), ("agent", "તો શુક્રવારે ₹1,20,000, બરાબર ને?"),
                      ("customer", "હા"), ("agent", "આભાર. આવજો.")]), "confirmed again"),
    (call(GOOD[:3] + [("customer", "જોઉં છું."), ("agent", "જી. ₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?")]
          + GOOD[3:]), "said twice"),
    (call(GOOD[:3] + [("customer", "હા"), ("agent", "જી, તો બાકી કા પેમેન્ટ કબ તક હો જાએગા?")] + GOOD[3:]),
     "in Hindi"),
    (call(GOOD, scenario="hindi"), "Hindi speaker in Gujarati"),
    (call(GOOD, scenario="statement"), "to-do is empty"),
    (call(GOOD[:3] + [("customer", "IFSC આપો"), ("agent", "SBIN0001234 છે.")] + GOOD[3:], scenario="statement",
          owner_action="સ્ટેટમેન્ટ મોકલવું"), "account number"),
    (call(GOOD, scenario="wrong", outcome="callback"), "someone else about the dues"),
    (call(GOOD[:5] + [("customer", "માણસ મોકલો"), ("agent", "સારું, અમારો માણસ શુક્રવારે આવી જશે, બરાબર ને?")]
          + GOOD[5:], scenario="collect"), "someone will come"),
    (call(GOOD[:3] + [("customer", "બે મિનિટ પછી ફોન કરો"), ("agent", "હા જી, વાંધો નહીં.")] + GOOD[3:],
          scenario="callback", outcome="callback"), "held the line"),
])
def test_a_bad_call_is_caught(bad, want):
    found = chat.problems(bad)
    assert any(want in p for p in found), found


def test_allowed_stops_pass():
    stopped = call(GOOD, scenario="english", stops=["she was about to talk about discount: 3% ઓછા"])
    assert chat.problems(stopped) == []
    late = call(GOOD, scenario="long", outcome="handover",
                stops=["she was about to agree to 2026-11-29, past the 15-day limit: ..."])
    assert chat.problems(late) == []
