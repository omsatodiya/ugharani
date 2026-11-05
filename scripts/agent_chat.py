"""Try the call agent on typed conversations, with Gemini playing the customer. No Gnani credits.

Usage: uv run python scripts/agent_chat.py [scenario ...]    (default: all)
"""

import asyncio
import sys
from datetime import date

from ugharani import agent, followup, llm

TODAY = date.today()
SETTINGS = {**{k: followup.TYPES.get(k, str)(v) if followup.TYPES.get(k, str) is not bool else v == "1"
               for k, v in followup.DEFAULTS.items()}}

BASE = {"name": "રમેશભાઈ", "firm": "શ્રીજી હાર્ડવેર", "city": "જેતપુર", "deals_with": "મનીષભાઈ",
        "balance": 120000, "earliest_due": TODAY.isoformat(),
        "bills": [{"amount": 50000, "due_date": TODAY.isoformat()},
                  {"amount": 70000, "due_date": date.fromordinal(TODAY.toordinal() + 5).isoformat()}]}

# name: (customer overrides, persona for the simulated customer)
SCENARIOS = {
    "promise": ({}, "Busy but cooperative hardware dealer. Speaks Gujarati. Can pay ₹60,000 this Saturday by "
                    "RTGS and the rest next week; only commits when asked for a date."),
    "paid": ({}, "Says he already sent ₹1,20,000 by NEFT on 30 October, a bit surprised by the call."),
    "dispute": ({}, "Says 20 CPVC elbows in the last lot were damaged and he wants a credit note before paying. "
                    "Slightly annoyed but polite."),
    "hindi": ({"name": "સુરેશભાઈ", "firm": "બાલાજી સેનિટરી"},
              "Speaks only Hindi (Marwari trader in Rajkot). Vague at first ('dekhte hain', 'ho jayega'), "
              "gives the 15th of this month when pressed politely."),
    "robot": ({}, "Suspicious. First asks 'તમે robot છો કે માણસ?'. Then asks the price of 1 inch CPVC tee and "
                  "whether new stock came. Finally says he'll pay next Monday."),
    "angry": ({}, "Irritated: 'રોજ ફોન કરો છો, મેં કીધું ને થઈ જશે'. Doesn't want to talk."),
    "long": ({}, "Friendly. Says the market is slow and asks to pay the whole amount after 25 days, then "
                 "asks if he can pay half in 10 days and half after a month."),
    "statement": ({}, "Wants the account statement and the bank details (IFSC) before paying; asks which bill "
                      "is pending. Then says he'll pay on Saturday by NEFT."),
    "hold": ({}, "Answers in a shop: first says 'એક મિનિટ, ગ્રાહક છે' and then, on his next turn, 'હા બોલો, "
                 "શું હતું?'. Pays on the 10th."),
    "wrong": ({}, "Is the son, not Rameshbhai. Father has gone to Rajkot, back in the evening."),
    "english": ({}, "Speaks Gujarati mixed with a lot of English ('payment process ma che, by Monday done "
                    "thai jashe'). Asks for 3% discount for paying early."),
    "big": ({"balance": 350000, "earliest_due": date.fromordinal(TODAY.toordinal() - 12).isoformat()},
            "Owes a lot, market is slow, asks for 30 more days and a 2% discount for early part payment."),
}

CUSTOMER_PROMPT = """You are role-playing a customer of a pipe-fittings manufacturer, receiving a payment \
reminder phone call. Persona: {persona}
Reply as this person would on the phone: one or two short sentences, in Gujarati script. If your persona \
speaks Hindi, speak HINDI words (not Gujarati), just written in Gujarati script, e.g. "हाँ बोलिए" -> \
"હાં બોલિએ". If the caller has said goodbye, reply with a short goodbye."""


async def run(name: str) -> None:
    overrides, persona = SCENARIOS[name]
    customer = {**BASE, **overrides}
    history = [{"who": "agent", "text": agent.opening(SETTINGS, customer)}]
    print(f"\n=== {name}: {persona}")
    print(f"  કાવ્યા : {history[0]['text']}")
    for _ in range(8):
        # the simulated customer sees the call from the other side
        flipped = [{"who": "customer" if h["who"] == "agent" else "agent", "text": h["text"]} for h in history]
        said = await llm.generate(CUSTOMER_PROMPT.format(persona=persona), flipped)
        history.append({"who": "customer", "text": said})
        print(f"  ગ્રાહક : {said}")
        await asyncio.sleep(4)  # free tier: requests per minute
        text, done = await agent.reply(SETTINGS, customer, history, TODAY)
        history.append({"who": "agent", "text": text})
        print(f"  કાવ્યા : {text}{'  [hangs up]' if done else ''}")
        await asyncio.sleep(4)
        if done:
            break
    notes = await agent.notes(SETTINGS, customer, history, TODAY)
    print(f"  NOTES  : {notes}")


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for name in sys.argv[1:] or SCENARIOS:
        await run(name)


if __name__ == "__main__":
    asyncio.run(main())
