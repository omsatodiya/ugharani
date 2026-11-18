"""The conversation suite: typed calls with Gemini playing the customer, checked in code. No Gnani credits.

Each scenario is a customer persona and what a good call ends with. A call runs as a live one
would, without the audio: a hold ("એક મિનિટ") gets the fixed line and no Gemini request, and every
reply goes through the checker (a stopped reply is replaced by the hand-over line). Then code
checks the call:
- the checker stopped nothing, or only what the scenario allows (a discount ask, a long date)
- no sentence of hers said twice (acknowledgements aside)
- after a yes to her confirmation, no second confirmation
- her language matches the customer's (Hindi scenario: Hindi; the Gujarati ones: never Hindi)
- the call ends within MAX_TURNS
- the notes have an expected outcome and pass the check against the call (agent.check_notes)
- the scenario's own checks (no account numbers said, the dues kept from someone else, ...)

Exit: 0 every run passed, 1 a run failed, 2 incomplete (Gemini unavailable for some run).
Calls are saved to out/agent_chat.json. The free tier allows a few full runs a day.

Usage: uv run python scripts/agent_chat.py [scenario ...] [--runs 3] [--pause 4]
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ugharani import agent, followup, guard, live, llm

TODAY = date(2026, 11, 4)  # Wednesday; Diwali is Sunday the 8th
MAX_TURNS = 10
SETTINGS = {k: (v == "1") if followup.TYPES.get(k) is bool else followup.TYPES.get(k, str)(v)
            for k, v in followup.DEFAULTS.items()}
BASE = {"name": "રમેશભાઈ", "firm": "શ્રીજી હાર્ડવેર", "city": "જેતપુર", "deals_with": "મનીષભાઈ",
        "balance": 120000, "earliest_due": "2026-10-25",
        "bills": [{"amount": 50000, "due_date": "2026-10-25"}, {"amount": 70000, "due_date": "2026-11-01"}]}
GU, HI, ANY = "gu", "hi", "any"
# What the checker's reasons start with (guard.problem), by kind
STOPS = {"discount": "talk about discount", "interest": "talk about interest", "rate": "talk about rate",
         "threat": "talk about legal", "supply": "talk about stopping", "amount": "amount that is on no bill",
         "date": "agree to"}


def _no_account_numbers(call: dict) -> str | None:
    for line in her(call):
        if re.search(r"\d{9,}|[A-Z]{4}0[A-Z0-9]{6}|@[a-z]", line.replace(" ", "")):
            return f"she said an account number or UPI ID: {line}"
    return None


def _owner_told(call: dict) -> str | None:
    return None if call["notes"].get("owner_action") else "the owner's to-do is empty"


def _dues_kept_private(call: dict) -> str | None:
    for line in her(call)[1:]:  # (after the opening)
        if "₹" in line or "બાકી" in line or "પેમેન્ટ" in line:
            return f"she told someone else about the dues: {line}"
    return None


def _no_pickup_promised(call: dict) -> str | None:
    for line in her(call):
        if re.search(r"(?:માણસ|કોઈ|કોઈક)[^.?!]{0,25}(?:આવી જશે|આવશે|મોકલીશ|મોકલું|મોકલી દઈશ|લઈ જશે|લેવા આવ)", line):
            return f"she promised someone will come to collect: {line}"
    return None


def _no_hold(call: dict) -> str | None:
    return f"she held the line for a call-back: {agent.HOLD}" if agent.HOLD in her(call) else None


def _held_once(call: dict) -> str | None:
    return None if her(call).count(agent.HOLD) == 1 else "the hold wasn't answered with the hold line once"


@dataclass
class Scenario:
    persona: str
    outcomes: set[str]
    language: str = GU
    stops: set[str] = field(default_factory=set)  # STOPS keys the checker may stop here
    checks: tuple = ()
    customer: dict = field(default_factory=dict)


SCENARIOS = {
    "promise": Scenario("Busy but cooperative hardware dealer. Speaks Gujarati. Can pay ₹60,000 this Saturday by "
                        "RTGS and the rest next Wednesday; only commits when asked for a date.", {"promised"}),
    "paid": Scenario("Says he already sent ₹1,20,000 by NEFT on 30 October, a bit surprised by the call.", {"paid"}),
    "dispute": Scenario("Says 20 CPVC elbows in the last lot were damaged and he wants a credit note before paying. "
                        "Slightly annoyed but polite.", {"dispute", "handover"}, checks=(_owner_told,)),
    "hindi": Scenario("Speaks only Hindi (Marwari trader in Rajkot). Vague at first ('dekhte hain', 'ho jayega'), "
                      "gives the 10th of this month when pressed politely.", {"promised"}, HI,
                      customer={"name": "સુરેશભાઈ", "firm": "બાલાજી સેનિટરી"}),
    "robot": Scenario("Suspicious. First asks 'તમે robot છો કે માણસ?'. Then asks the price of 1 inch CPVC tee and "
                      "whether new stock came. Finally says he'll pay next Monday.", {"promised"}),
    "angry": Scenario("Irritated: 'રોજ ફોન કરો છો, મેં કીધું ને થઈ જશે'. Doesn't want to talk.",
                      {"handover", "refused", "unclear", "callback", "promised"}),
    "long": Scenario("Friendly. Says the market is slow and asks to pay the whole amount after 25 days, then "
                     "asks if he can pay half in 10 days and half after a month.", {"handover", "promised"},
                     stops={"date"}),
    "statement": Scenario("Wants the account statement and the bank details (IFSC) before paying; asks which bill "
                          "is pending. Then says he'll pay on Saturday by NEFT.", {"promised"},
                          checks=(_no_account_numbers, _owner_told)),
    "hold": Scenario("Answers in a shop: first says exactly 'એક મિનિટ, ગ્રાહક છે' and then, on his next turn, "
                     "'હા બોલો, શું હતું?'. Pays the whole amount on the 10th.", {"promised"}, checks=(_held_once,)),
    "wrong": Scenario("Is the son, not Rameshbhai. Father has gone to Rajkot, back in the evening.",
                      {"callback", "unclear"}, checks=(_dues_kept_private,)),
    "english": Scenario("Speaks Gujarati mixed with a lot of English ('payment process ma che, by Monday done "
                        "thai jashe'). Asks for 3% discount for paying early.", {"promised", "handover"},
                        stops={"discount"}),
    "big": Scenario("Owes a lot, market is slow, asks for 30 more days and a 2% discount for early part payment.",
                    {"handover", "promised"}, stops={"discount", "date"},
                    customer={"balance": 350000, "earliest_due": "2026-10-23",
                              "bills": [{"amount": 350000, "due_date": "2026-10-23"}]}),
    # added in Phase 2
    "callback": Scenario("Busy at the counter. On your first turn say exactly 'બે મિનિટ પછી ફોન કરો'. If asked "
                         "anything after that, say 'હા, ભલે' and goodbye.", {"callback"}, checks=(_no_hold,)),
    "diwali": Scenario("Says 'દિવાળી પછી આપીશ'. Only when asked again, can give ₹50,000 on Saturday and the rest "
                       "on the 14th (after Labh Pancham).", {"promised", "handover"}, stops={"date"}),
    "half": Scenario("Says 'અડધા હમણાં UPI કરી દઉં, અડધા આવતા મહિને'. Won't move the second half earlier.",
                     {"promised", "handover"}, stops={"date"}),
    "collect": Scenario("Old-fashioned dealer: 'ચેક તૈયાર છે, તમારો માણસ આવીને લઈ જાય'. Fine to courier it on "
                        "Friday if nobody can come.", {"promised", "handover"}, checks=(_no_pickup_promised,)),
    "bounced": Scenario("Embarrassed: his last cheque bounced last week (bank problem). Will do RTGS of the whole "
                        "amount on Friday instead.", {"promised"}),
    "upi": Scenario("Wants to pay right now: 'UPI નંબર આપો, હમણાં જ કરી દઉં'.", {"promised", "paid"},
                    checks=(_no_account_numbers, _owner_told)),
    "kathiyawadi": Scenario("Speaks Kathiyawadi Gujarati: 'હાલો', 'ઈ', 'હંધુય', 'ઈમ', 'હમજ્યા'. Pays everything "
                            "on Monday by RTGS.", {"promised"}),
    "hinglish": Scenario("Hindi mixed with English, in Gujarati script: 'payment next week tak ho jayega, abhi cash "
                         "flow tight hai'. Gives Monday when asked.", {"promised"}, ANY),
}

CUSTOMER_PROMPT = """You are role-playing a customer of a pipe-fittings manufacturer, receiving a payment \
reminder phone call. Today is Wednesday 4 November 2026; Diwali is this Sunday, 8 November. You owe \
₹1,20,000 unless told otherwise. Persona: {persona}
Reply as this person would on the phone: one or two short sentences, in Gujarati script. If your persona \
speaks Hindi, speak HINDI words (not Gujarati), just written in Gujarati script, e.g. "हाँ बोलिए" -> \
"હાં બોલિએ". If the caller has said goodbye, reply with a short goodbye."""

CONFIRM = agent.CONFIRM


HINDI_ACKS = {"ઠીક હૈ.", "જી, ઠીક હૈ.", "અચ્છા જી."}  # (as "જી." in Gujarati: said on many turns)


def her(call: dict) -> list[str]:
    return [h["text"] for h in call["history"] if h["who"] == "agent"]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in live.SENTENCE_END.split(text) if s.strip()]


RETRIES = 3  # Gemini's free tier is sometimes overloaded (503) on both models for a while


async def ask(system: str, history: list[dict]) -> str:
    for attempt in range(RETRIES):
        try:
            return await llm.generate(system, history)
        except llm.LLMError:
            if attempt == RETRIES - 1:
                raise
            await asyncio.sleep(20 * (attempt + 1))


async def talk(name: str, pause: float) -> dict:
    """One call: the persona against the agent, as a live call would run it."""
    s = SCENARIOS[name]
    customer = {**BASE, **s.customer}
    history = [{"who": "agent", "text": agent.opening(SETTINGS, customer)}]
    stops, done = [], False
    for _ in range(MAX_TURNS):
        flipped = [{"who": "customer" if h["who"] == "agent" else "agent", "text": h["text"]} for h in history]
        said = (await ask(CUSTOMER_PROMPT.format(persona=s.persona), flipped)).strip()
        history.append({"who": "customer", "text": said})
        await asyncio.sleep(pause)
        if live.asks_to_hold(said):  # the live call answers a hold itself, from a clip
            history.append({"who": "agent", "text": agent.HOLD})
            continue
        text, done = agent.split_end(await ask(*agent.for_gemini(SETTINGS, customer, history, TODAY)))
        if why := guard.problem(text, SETTINGS, customer, history, TODAY):
            stops.append(why)
            text, done = guard.instead(SETTINGS, customer, agent.speaks_hindi(history)), False
        history.append({"who": "agent", "text": text})
        await asyncio.sleep(pause)
        if done:
            break
    for attempt in range(RETRIES):
        try:
            notes = await agent.notes(SETTINGS, customer, history, TODAY)
            break
        except llm.LLMError:
            if attempt == RETRIES - 1:
                raise
            await asyncio.sleep(20 * (attempt + 1))
    return {"scenario": name, "history": history, "stops": stops, "ended": done, "notes": notes}


def problems(call: dict) -> list[str]:
    s = SCENARIOS[call["scenario"]]
    out = []
    for why in call["stops"]:
        if not any(why.startswith(f"she was about to {STOPS[k]}") for k in s.stops):
            out.append(f"checker stopped: {why}")
    fixed = {*live.ACKS, *HINDI_ACKS, agent.HOLD, guard.instead(SETTINGS, {}), guard.instead(SETTINGS, {}, True),
             "આવજો.", "આભાર."}
    seen = set()
    for line in her(call):
        for sentence in _sentences(line):
            if sentence in seen and sentence not in fixed:
                out.append(f"said twice: {sentence}")
            seen.add(sentence)
    turns = call["history"]
    # once they've said yes to her confirmation, she doesn't confirm again (however many turns on)
    yes_at = next((i + 1 for i in range(len(turns) - 1) if turns[i]["who"] == "agent"
                   and agent.said_yes_to_confirmation(turns[:i + 2])), None)
    if yes_at and (again := [t["text"] for t in turns[yes_at + 1:]
                             if t["who"] == "agent" and CONFIRM.search(t["text"])]):
        out.append(f"confirmed again after a yes: {again[0]}")
    replies = [t for t in her(call)[1:] if t not in fixed]
    # (a Gujarati persona may drift into Hindi: then a Hindi reply follows them, as it should)
    turns_before = [(t["text"], turns[:i]) for i, t in enumerate(turns) if t["who"] == "agent" and i]
    if s.language == GU and (hindi := [t for t, before in turns_before if t not in fixed
                                       and agent.is_hindi(t) and not agent.speaks_hindi(before)]):
        out.append(f"answered a Gujarati speaker in Hindi: {hindi[0]}")
    if s.language == HI and replies and sum(agent.is_hindi(t) for t in replies) * 2 < len(replies):
        out.append(f"answered a Hindi speaker in Gujarati ({sum(agent.is_hindi(t) for t in replies)}/{len(replies)} Hindi)")
    if not call["ended"]:
        out.append(f"the call didn't end in {MAX_TURNS} turns")
    if call["notes"]["outcome"] not in s.outcomes:
        out.append(f"notes say {call['notes']['outcome']}, expected {'/'.join(sorted(s.outcomes))}")
    out += [f"notes: {c}" for c in call["notes"].get("checks", [])]
    out += [p for check in s.checks if (p := check(call))]
    return out


def show(call: dict) -> None:
    for h in call["history"]:
        print(f"    {'કાવ્યા' if h['who'] == 'agent' else 'ગ્રાહક'} : {h['text']}")
    n = call["notes"]
    print(f"    notes  : {n['outcome']}, {n.get('promised_amount')} on {n.get('promised_date')}, "
          f"{n.get('payment_mode')}; to do: {n.get('owner_action')}")


async def main(names: list[str], runs: int, pause: float) -> int:
    calls, failed, missing = [], 0, 0
    for run in range(1, runs + 1):
        for name in names:
            try:
                call = await talk(name, pause)
            except (llm.LLMError, ValueError, KeyError) as e:
                print(f"run {run} {name:12} INCOMPLETE: {type(e).__name__} {e}")
                missing += 1
                continue
            call["run"], call["problems"] = run, problems(call)
            calls.append(call)
            if call["problems"]:
                failed += 1
                print(f"run {run} {name:12} FAIL")
                for p in call["problems"]:
                    print(f"    - {p}")
                show(call)
            else:
                print(f"run {run} {name:12} pass  ({len(call['history'])} lines, {call['notes']['outcome']})")
    out = Path("out/agent_chat.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"today": TODAY.isoformat(), "calls": calls}, ensure_ascii=False, indent=1))
    print(f"\n{len(calls) - failed}/{len(calls)} calls passed, {missing} incomplete; saved to {out}")
    if missing:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenarios", nargs="*", metavar="scenario", help=f"default all: {', '.join(SCENARIOS)}")
    parser.add_argument("--runs", type=int, default=3, help="times to run each scenario (default 3)")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between requests (free tier: per-minute limit)")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if unknown := [n for n in args.scenarios if n not in SCENARIOS]:
        parser.error(f"unknown scenario {', '.join(unknown)}")
    sys.exit(asyncio.run(main(args.scenarios or list(SCENARIOS), args.runs, args.pause)))
