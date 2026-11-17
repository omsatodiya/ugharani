"""The follow-up call agent: what it knows, how it talks, and the notes it leaves.

Modelled on the staff member a trader pays to chase payments: she calls, asks
for the payment, carries the conversation, hands big amounts and disputes to
the owner, sends questions she can't answer to whoever the customer deals with,
and writes down what was agreed.
"""

from datetime import date, timedelta

from ugharani import dates, guard, llm
from ugharani.followup import OUTCOMES
from ugharani.lang.gu import (BUSY, CALL_VERB, CALLBACK_NOW, GUJARATI_WORDS, HINDI_NOW, HINDI_WORDS,  # noqa: F401
                              LATER, WEEKDAYS)
from ugharani.lang.gu import HOLD_OK as HOLD
from ugharani.reminders import spoken_date
from ugharani.speech import rupees

END = "<END>"  # the agent ends its last line with this to hang up


def greeting(customer: dict) -> str:
    """Her first words, then she waits, as a person calling does. (No comma: Timbre pauses at it.)"""
    return f"હેલો {customer['name']}?"


def intro(settings: dict, answered_yes: bool = True) -> str:
    """Who she is, once they answer.

    "હા નમસ્તે" after their "હા"/"બોલો"; plain "નમસ્તે" after "કોણ?" or someone else answering.
    With `disclose_ai` (the default) she says she is the business's automatic assistant. (No
    commas: Timbre pauses at them.)
    """
    yes = "હા " if answered_yes else ""
    if settings.get("disclose_ai", True):
        return (f"{yes}નમસ્તે. હું {settings['business_name_spoken']}ની ઓટોમેટિક આસિસ્ટન્ટ "
                f"{settings['agent_name']} બોલું છું.")
    return f"{yes}નમસ્તે. હું {settings['agent_name']} બોલું છું {settings['business_name_spoken']}માંથી."


def fallback_ask(customer: dict) -> str:
    """The call's main question, fixed: said if Gemini fails right after the intro."""
    return f"તમારું {rupees(customer['balance'])} નું પેમેન્ટ બાકી છે, એ ક્યારે મોકલશો?"


def opening(settings: dict, customer: dict) -> str:
    """Greeting and intro as one line, for typed test conversations (a call says them as two turns)."""
    return f"{greeting(customer)} {intro(settings, answered_yes=False)}"


def _dues_line(customer: dict, today: date) -> str:
    due = date.fromisoformat(customer["earliest_due"])
    if due < today:
        when = f"due date {spoken_date(due)} was {(today - due).days} days ago (overdue)"
    elif due == today:
        when = "due today"
    else:
        when = f"due on {spoken_date(due)}"
    return f"Pending: {rupees(customer['balance'])}, {when}."


def _bills_line(customer: dict) -> str:
    bills = customer.get("bills") or []
    if len(bills) < 2:
        return ""
    listed = ", ".join(f"{rupees(b['amount'])} (due {spoken_date(date.fromisoformat(b['due_date']))})" for b in bills)
    return f"\nOpen bills, oldest first (what is still unpaid of each): {listed}."


def system_prompt(settings: dict, customer: dict, today: date, last_call: dict | None = None) -> str:
    owner = settings["owner_name"]
    deals_with = customer.get("deals_with") or owner
    promise_by = spoken_date(today + timedelta(days=settings["promise_days"]))
    split_by = spoken_date(today + timedelta(days=settings["split_days"]))
    owner_calls = guard.instead(settings, customer)
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
customer about a pending payment ("ઉઘરાણી"). You have already greeted them and said who you are\
{" (and that you are the company's automatic assistant)" if settings.get("disclose_ai", True) else ""}.

CUSTOMER
Name: {customer['name']}{f", {customer['firm']}" if customer.get('firm') else ""}\
{f", {customer['city']}" if customer.get('city') else ""}
{_dues_line(customer, today)}{_bills_line(customer)}
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
- Never say the same sentence twice in a call. If they didn't answer a question, ask it differently.
- No formal or written words: not "આપની", "કૃપા કરીને", "જણાવશો", "ઉપરોક્ત", "રકમ"; say "તમારું", \
"કહેજો ને", "પૈસા", "પેમેન્ટ". Don't mention product names unless they ask.
- Language: mirror the customer. Default Gujarati. The customer's words reach you through Gujarati speech \
recognition, so their Hindi is usually written in Gujarati script: "ચલ રહા હૈ", "ભેજ દૂંગા", "કર દૂંગા", \
"અગલે સોમવાર કો", "બોલિએ", "ઠીક હૈ" are Hindi. When they speak Hindi, answer in simple spoken Hindi, e.g. \
"જી, તો બાકી કા પેમેન્ટ કબ તક હો જાએગા?" (still in Gujarati script). Mix English trade words naturally \
(payment, cheque, RTGS, NEFT, UPI, bill). ALWAYS write in Gujarati script, even Hindi and English words, \
because a Gujarati voice reads it aloud. No emojis, lists or brackets.
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
YOUR LIMITS (the owner's; never go past them)
- A date for the whole payment: up to {promise_by}. Part payments: only if the last part comes by {split_by}. If they want longer, ask once whether a part can come by {promise_by}; if not, don't agree and don't argue; say "{owner_calls}"
- In parts: get the date of EVERY part. If the last part is after {split_by} ("બાકીનું મહિના પછી"), \
that part is not agreed: say "{owner_calls}" (the first part can still be confirmed). Confirm all \
parts in one sentence: "તો 10 તારીખે ₹60,000 અને 18 તારીખે બાકીના ₹60,000, બરાબર ને?"
- Never offer or agree to a discount, waiving or charging interest, or any other change to the terms; for those too: "{owner_calls}"
OTHER JOBS
4. Already paid: thank them, ask when, how much and how (cheque no. or UTR if handy), say accounts will \
check. Never argue.
5. Disputes (rate, quantity, damaged or short goods, discount, credit note, wrong bill): don't argue or \
decide. Note it and say {deals_with} will call them about it.
6. Questions you can't answer (stock, new orders, rates, delivery, anything not about this payment): \
"એ માટે તમે {deals_with} સાથે વાત કરી લેજો". Never invent facts, rates or amounts.
7. Statement, ledger, bill copy, or bank details (account number, IFSC, UPI ID): "હું તમને WhatsApp પર મોકલાવી દઉં છું." Never say account numbers or bill numbers yourself. Which bill is pending: from the list above.
8. "એક મિનિટ", "હોલ્ડ કરો", someone else at their door: say only "{HOLD}" and wait for them.
   "બે મિનિટ પછી ફોન કરો", "પછી ફોન કરજો", busy or driving: a call-back, not a hold. If they said \
when, say you'll call then and end; if not, ask once when to call back, then end.
   Someone else answered (son, staff, wife; "ના, એ બહાર છે"): the dues are private, never tell them the \
amount or that a payment is pending. Say "સારું. તો {customer['name']}ને કહેજો ને કે \
{settings['business_name_spoken']}માંથી ફોન હતો. એ ક્યારે મળશે?", then thank them and say goodbye \
without using {customer['name']}'s name. Angry: stay calm, apologise for the trouble, say {owner} will call, end.
9. If asked whether you are a robot, AI or a recording: be honest, e.g. "હા જી, હું \
{settings['business_name_spoken']}ની ઓટોમેટિક આસિસ્ટન્ટ છું, {owner} વતી ફોન કર્યો છે. તમારે {deals_with} \
સાથે વાત કરવી હોય તો એ ફોન કરશે." Then go on with the payment.
10. NEVER: threaten, mention legal action, stopping supply, interest or penalties; guilt-trip; talk about \
the company's or your own problems; share anything about other customers; promise anything on the \
company's behalf.

ENDING
Keep the call short (about 2 minutes). Once there is an outcome, confirm it as a question in one \
sentence ("તો 10 નવેમ્બરે ₹50,000 RTGS, બરાબર ને?") and STOP: wait for their answer. Only in your next \
message, after they agree (or straight away after handing over to {deals_with} or {owner}, fixing a \
callback, or an angry customer), say a short thanks and goodbye ("સારું, આભાર {customer['name']}. આવજો.") \
and end that message with {END}. The goodbye message never contains a question. Confirm only once: \nif they already said yes to it ("હા", "ઠીક છે", "बराबर", "हाँ जी"), even while you were still asking, \ndo not ask again, say goodbye."""


# ---------- which language the customer speaks ----------


def language_words(text: str) -> tuple[int, int]:
    """(Hindi, Gujarati) marker words in `text`: Devanagari counts as Hindi."""
    hindi = gujarati = 0
    for word in text.replace("।", " ").split():
        word = word.strip(".,?!")
        if any("ऀ" <= ch <= "ॿ" for ch in word) or word in HINDI_WORDS:
            hindi += 1
        elif word in GUJARATI_WORDS:
            gujarati += 1
    return hindi, gujarati


def is_hindi(text: str) -> bool:
    hindi, gujarati = language_words(text)
    return hindi > gujarati


def speaks_hindi(history: list[dict]) -> bool:
    """Does the customer speak Hindi? Judged on their last two turns, so a switch is followed."""
    return is_hindi(" ".join([h["text"] for h in history if h["who"] == "customer"][-2:]))


def asks_for_callback(text: str) -> bool:
    """"બે મિનિટ પછી ફોન કરો", "સાંજે ફોન કરજો", "હું સામેથી ફોન કરું", "busy છું": call later.
    (Not a hold: she would wait on a line they have left.)"""
    return bool(CALL_VERB.search(text) and LATER.search(text)) or bool(BUSY.search(text))


def for_gemini(settings: dict, customer: dict, history: list[dict], today: date,
               last_call: dict | None = None, heard_language: str | None = None) -> tuple[str, list[dict]]:
    """The system prompt and conversation for the agent's next reply.

    When the customer speaks Hindi or asks to be called back, a note goes on their latest turn (the
    end of the conversation weighs more than a rule deep in the prompt); the stored transcript is
    not changed. `heard_language`: the language Gnani judged their latest words to be in
    (gnani.stt_languages); "hi-IN" means Hindi whatever the words say.
    """
    prompt = system_prompt(settings, customer, today, last_call)
    if history and history[-1]["who"] == "customer":
        notes = [note for note, applies in ((HINDI_NOW, (heard_language or "").startswith("hi") or speaks_hindi(history)),
                                            (CALLBACK_NOW, asks_for_callback(history[-1]["text"]))) if applies]
        if notes:
            history = [*history[:-1], {"who": "customer", "text": "\n".join([history[-1]["text"], *notes])}]
    return prompt, [dict(h) for h in history]  # a snapshot: the call goes on while Gemini writes


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
    text, end = split_end(await llm.generate(*for_gemini(settings, customer, history, today, last_call)))
    if guard.problem(text, settings, customer, history, today):  # (a live call checks each sentence)
        return guard.instead(settings, customer), False
    return text, end


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
owner_action: only if the owner or the person they deal with must do something, e.g. call back about a discount or a longer date, settle a dispute, or send the statement / bill copy / bank details on WhatsApp when the agent promised it. A callback time they asked for (or someone else who answered asked for) goes here too, e.g. "સાંજે ફરી ફોન કરવો"."""


NOW = ("હમણાં", "હમણા", "અત્યારે", "અભી", "अभी", "હાલ", "આજે", "આજ")
HALF = ("અડધા", "અડધું", "અડધી", "આધા", "આધે", "आधा", "आधे")


def check_notes(out: dict, customer: dict, history: list[dict], today: date) -> list[str]:
    """Gemini's promise checked against the call itself: a date someone said (as `dates.py` reads
    it) and an amount someone said, the balance, half of it, or what is left after a part. An
    unsupported value is dropped (a false promise would hold back the follow-up calls); what the
    owner should check is returned."""
    checks = []
    lines = [h["text"] for h in history]
    if out.get("promised_amount"):
        balance, amount = customer["balance"], out["promised_amount"]
        heard = set().union(*(guard._numbers(line) for line in lines), set())
        ok = {balance, *heard, *(balance - n for n in heard if 0 < n < balance)}
        if any(w in line for line in lines for w in HALF):
            ok.add(balance // 2)
        if amount not in ok:
            checks.append(f"નોંધ તપાસો: {rupees(amount)} ની રકમ ફોનમાં સંભળાઈ નથી.")
            out["promised_amount"] = None
    if out.get("promised_date") and out.get("outcome") == "promised":  # (a paid date is in the past)
        when = date.fromisoformat(out["promised_date"])
        spans = [span for line in lines for span in dates.spans(line, today)]
        said_now = when == today and any(w in line for line in lines for w in NOW)
        if not said_now and not any(start <= when <= until for start, until in spans):
            checks.append(f"નોંધ તપાસો: વાયદાની તારીખ {spoken_date(when)} ફોનમાં સંભળાઈ નથી.")
            out["promised_date"] = None
    return checks


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
    amount = out.get("promised_amount")
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    out["promised_amount"] = amount if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0 else None
    out["checks"] = check_notes(out, customer, history, today)
    if out["checks"]:  # the owner's to-do says what to look at
        out["owner_action"] = " ".join(filter(None, [out.get("owner_action"), *out["checks"]]))
    return out
