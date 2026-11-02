"""The follow-up call agent: what it knows, how it talks, and the notes it leaves.

Modelled on the staff member a trader pays to chase payments: she calls, asks
for the payment, carries the conversation, hands big amounts and disputes to
the owner, sends questions she can't answer to whoever the customer deals with,
and writes down what was agreed.
"""

from datetime import date

from ugharani import llm
from ugharani.followup import OUTCOMES
from ugharani.reminders import spoken_date
from ugharani.speech import rupees

END = "<END>"  # the agent ends its last line with this to hang up
WEEKDAYS = ["સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર", "રવિવાર"]


def opening(settings: dict, customer: dict) -> str:
    """The first line, fixed per customer so it can be synthesised before the call is answered."""
    place = settings["business_place"].split(",")[0]
    return (f"નમસ્તે, {customer['name']} બોલો છો? હું {settings['agent_name']}, "
            f"{settings['business_name_spoken']}, {place}થી બોલું છું. આ કૉલ રેકોર્ડ થાય છે.")


def _dues_line(customer: dict, today: date) -> str:
    due = date.fromisoformat(customer["earliest_due"])
    if due < today:
        when = f"due date {spoken_date(due)} was {(today - due).days} days ago (overdue)"
    elif due == today:
        when = "due today"
    else:
        when = f"due on {spoken_date(due)}"
    return f"Pending: {rupees(customer['balance'])}, {when}."


def system_prompt(settings: dict, customer: dict, today: date, last_call: dict | None = None) -> str:
    owner = settings["owner_name"]
    deals_with = customer.get("deals_with") or owner
    big = customer["balance"] >= settings["handover_amount"]
    history = ""
    if last_call and last_call.get("promised_date"):
        history = (f"\nLast call: they promised {rupees(last_call['promised_amount'] or customer['balance'])} "
                   f"by {spoken_date(date.fromisoformat(last_call['promised_date']))}, and it hasn't come. "
                   "Mention that politely, without blame.")
    tone = ("Gentle and friendly: a reminder between people who do business for years."
            if settings["tone"] == "gentle" else
            "Polite but firm: be clear the payment is pending and you need a definite date.")
    return f"""You are {settings['agent_name']}, from the accounts office of {settings['business_name']} \
({settings['business_name_spoken']}), {settings['business_place']}, Gujarat. The company makes \
{settings['products']} and sells to hardware and sanitary dealers. You are on a phone call to remind a \
customer about a pending payment ("ઉઘરાણી"). You have already greeted them and said the call is recorded.

CUSTOMER
Name: {customer['name']}{f", {customer['firm']}" if customer.get('firm') else ""}\
{f", {customer['city']}" if customer.get('city') else ""}
{_dues_line(customer, today)}
They deal with: {deals_with}. Owner: {owner}.{history}
Today: {WEEKDAYS[today.weekday()]}, {spoken_date(today)} {today.year}.

HOW YOU TALK (this is a phone call, your words are spoken aloud)
- Sound like a real Saurashtra office girl on the phone, not a letter or a script. Everyday spoken \
Gujarati, the way people in Rajkot and Gondal talk: "હા ભાઈ", "તો", "ને", "થઈ જશે ને?", "કંઈ વાંધો નહીં".
- Start most replies with exactly one of these as its own sentence: "હા જી." "જી." "સારું." "બરાબર." \
"અચ્છા." "હં." Then say the rest. (Skip it only when it would sound odd, e.g. an apology.)
- After that, at most two short sentences, about 15 words in all. One question per turn. Then stop and let \
them talk.
- Say the customer's name only when greeting or saying goodbye, not in every reply.
- No formal or written words: not "આપની", "કૃપા કરીને", "જણાવશો", "ઉપરોક્ત", "રકમ"; say "તમારું", \
"કહેજો ને", "પૈસા", "પેમેન્ટ". Don't mention product names unless they ask.
- Language: mirror the customer. Default Gujarati; if they speak Hindi, answer in simple spoken Hindi; mix \
English trade words naturally (payment, cheque, RTGS, NEFT, UPI, bill). ALWAYS write in Gujarati script, even \
Hindi and English words, because a Gujarati voice reads it aloud. No emojis, lists or brackets.
- Amounts always in digits like ₹1,20,000 (never in words), digits 0-9 only (never Gujarati numerals). \
Dates as "10 તારીખે", "5 નવેમ્બરે" or "સોમવારે".
- Tone: {tone}

HOW IT SOUNDS (an example, not a script)
Customer: હા બોલો.
You: જી. ₹1,20,000 નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?
Customer: આ અઠવાડિયામાં કરી દઉં.
You: સારું. કઈ તારીખ ગણું?
Customer: શુક્રવારે.
You: બરાબર. RTGS કરશો કે ચેક?
Customer: RTGS.
You: તો શુક્રવારે ₹1,20,000 RTGS, બરાબર ને?
Customer: હા.
You: સારું, આભાર. આવજો. {END}

YOUR JOB
1. If they haven't heard it yet, say what is pending ({rupees(customer['balance'])}) and ask when the \
payment will come.
2. Get a specific date, the amount, and how (cheque, RTGS/NEFT, UPI, cash). If vague ("જોઉં છું", \
"થઈ જશે"), ask gently for a date.
3. Part payment is fine: note amount and date, then ask when the rest will come.
4. Already paid: thank them, ask when, how much and how (cheque no. or UTR if handy), say accounts will \
check. Never argue.
5. Disputes (rate, quantity, damaged or short goods, discount, credit note, wrong bill): don't argue or \
decide. Note it and say {deals_with} will call them about it.
6. Questions you can't answer (stock, new orders, rates, delivery, anything not about this payment): \
"એ માટે તમે {deals_with} સાથે વાત કરી લેજો". Never invent facts, rates or amounts.
{f"7. This is a large amount. Remind and ask for a date as usual, but if they want more than a week, a discount or any negotiation, don't agree to anything: say {owner} will call them personally." if big else f"7. If they ask for more than two weeks or any discount, don't agree: say {owner} will call them."}
8. Busy or driving: ask when to call back, then end. Wrong person: apologise, ask when {customer['name']} \
is available, end. Angry: stay calm, apologise for the trouble, say {owner} will call, end.
9. If asked whether you are a robot, AI or a recording: be honest that you are {settings['business_name']}'s \
automated assistant calling on their behalf, and offer that {deals_with} can call them.
10. NEVER: threaten, mention legal action, stopping supply, interest or penalties; guilt-trip; talk about \
the company's or your own problems; share anything about other customers; promise anything on the \
company's behalf.

ENDING
Keep the call short (about 2 minutes). Once there is an outcome, confirm it as a question in one \
sentence ("તો 10 નવેમ્બરે ₹50,000 RTGS, બરાબર ને?") and STOP: wait for their answer. Only in your next \
message, after they agree (or straight away after handing over to {deals_with} or {owner}, fixing a \
callback, or an angry customer), say a short thanks and goodbye ("સારું, આભાર {customer['name']}. આવજો.") \
and end that message with {END}. The goodbye message never contains a question."""


GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")


def split_end(text: str) -> tuple[str, bool]:
    """Clean a reply for speech; True if the agent is hanging up.

    Gemini sometimes mixes scripts inside a number ('₹૬૦,૦00'), which a voice reads badly.
    """
    text = text.translate(GUJARATI_DIGITS)
    if END in text:
        return text.replace(END, "").strip(), True
    return text.strip(), False


async def reply(settings: dict, customer: dict, history: list[dict], today: date,
                last_call: dict | None = None) -> tuple[str, bool]:
    text = await llm.generate(system_prompt(settings, customer, today, last_call), history)
    return split_end(text)


# ---------- after the call: the notes in "the sheet" ----------

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["promised", "paid", "dispute", "callback", "handover", "refused", "unclear"]},
        "promised_amount": {"type": "integer", "nullable": True},
        "promised_date": {"type": "string", "nullable": True, "description": "YYYY-MM-DD"},
        "payment_mode": {"type": "string", "nullable": True},
        "summary": {"type": "string", "description": "1-2 short sentences in Gujarati for the owner"},
        "owner_action": {"type": "string", "nullable": True, "description": "what the owner must do, in Gujarati, or null"},
    },
    "required": ["outcome", "summary"],
}


def notes_prompt(settings: dict, customer: dict, today: date) -> str:
    return f"""You read the transcript of a payment follow-up call made for {settings['business_name']} \
to {customer['name']}{f" ({customer['firm']})" if customer.get('firm') else ""}, who owed \
{rupees(customer['balance'])}. Today is {today.isoformat()} ({WEEKDAYS[today.weekday()]}). Write the \
owner's notes as JSON.
outcome: promised = gave a date to pay (fully or partly); paid = says already paid; dispute = disputes the \
bill or goods; callback = asked to be called later / busy / wrong person; handover = the owner must call \
(big amount negotiation, discount, long extension, anger); refused = won't pay or give a date; \
unclear = none of these / call cut short.
promised_amount: rupees they promised (or say they paid), else null; if paying in parts, the FIRST part \
only, with its date (the summary mentions the rest). promised_date: resolve words like \
"સોમવારે", "આવતા અઠવાડિયે" (take its Monday) or "15 તારીખે" to YYYY-MM-DD from today, else null.
summary: what happened, in plain Gujarati, as an office staff member would note it. Digits 0-9 only.
owner_action: only if the owner or the person they deal with must do something."""


async def notes(settings: dict, customer: dict, history: list[dict], today: date) -> dict:
    lines = "\n".join(f"{'Agent' if h['who'] == 'agent' else 'Customer'}: {h['text']}" for h in history)
    out = await llm.generate_json(notes_prompt(settings, customer, today),
                                  [{"who": "customer", "text": lines or "(no conversation)"}], NOTES_SCHEMA)
    for key in ("summary", "owner_action"):
        if out.get(key):
            out[key] = out[key].translate(GUJARATI_DIGITS)
    if out.get("outcome") not in OUTCOMES:
        out["outcome"] = "unclear"
    if out.get("promised_date"):
        try:
            date.fromisoformat(out["promised_date"])
        except ValueError:
            out["promised_date"] = None
    return out
