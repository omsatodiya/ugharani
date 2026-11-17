"""Gujarati: the words the conversation code listens for and the fixed lines she says.

One place for them, so another language is a sibling file, not edits across live.py, agent.py and
guard.py. (Numbers and dates are read by extract.py and dates.py.)
"""

import re

from ugharani import extract

# ---------- her fixed lines (live.py) ----------

# Fixed lines: synthesised once, then always played from the cache.
FILLERS = ["જી,", "હા,", "અચ્છા,"]
# The short acknowledgements the agent starts a reply with (agent.py asks for exactly these):
# bundled clips, so the first word of a reply plays the moment Gemini writes it.
ACKS = ["હા જી.", "જી.", "સારું.", "બરાબર.", "અચ્છા.", "હં."]
HELLO = "હેલો? સાંભળાય છે?"
HELLO_SHORT = "હેલો?"
NO_ANSWER_BYE = "લાગે છે લાઇન બરાબર નથી. હું થોડી વાર પછી ફોન કરું છું. આવજો."
SORRY = "માફ કરજો, લાઇન થોડી ખરાબ છે. ફરી કહેશો?"
LINE_DROP_BYE = "માફ કરજો, લાઇનમાં તકલીફ છે. હું પછી ફોન કરું છું. આવજો."


def time_up_bye(owner_name: str) -> str:
    return f"સારું, હું આ વાત {owner_name}ને જણાવી દઉં છું. આભાર, આવજો."


# A reply's own opening acknowledgement, dropped after a filler ("જી, ... હા, 10 તારીખે")
ACK = re.compile(r"^(હા|જી|હા જી|અચ્છા|બરાબર|સારું|ઓકે)[,.!]?\s+")

HOLD_OK = "હા જી, વાંધો નહીં."  # what she says to "એક મિનિટ", then waits
WEEKDAYS = ["સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર", "રવિવાર"]


# ---------- what the customer says (live.py, agent.py) ----------

# Listening noises people make while the other side talks; a person doesn't stop for them.
BACKCHANNEL = {"હા", "હાં", "હં", "હમ", "હમ્મ", "જી", "હા જી", "ઓકે", "ok", "okay", "બરાબર", "અચ્છા", "સારું",
               "हाँ", "हां", "हा", "जी", "हम्म", "अच्छा", "ठीक", "ठीक है", "बराबर"}
# A yes to "હેલો રમેશભાઈ?"
YES = {"હા", "હાં", "હં", "જી", "બોલો", "બોલ", "બોલિએ", "બોલીએ", "બોલિયે", "હેલો", "હલો", "હા જી", "ok", "ઓકે",
       "हाँ", "हां", "हा", "जी", "बोलिए", "बोलो", "हेलो", "हैलो"}

# "એક મિનિટ", "જરા રાહ જુઓ", "ફોન ચાલુ રાખો": they'll be back on the line. ("ચાલુ રાખો" alone can
# mean "go on talking": only with ફોન/લાઈન.)
HOLD_WORDS = re.compile(r"(એક|બે|1|2|ek|be)\s*(મિનિટ|મિનીટ|મિનિટે|મિનટ|સેકન્ડ|minute|second|min)|હોલ્ડ|hold|"
                        r"[ઊઉ]ભા\s*(?:રહો|રે|રહેજો)|રુકો|રૂકો|રુકિએ|રૂકિએ|रुको|रुकिए|एक\s*(?:मिनट|सेकंड)|ठहरो|"
                        r"રાહ\s*(?:જુઓ|જુવો|જોજો|જોવો)|(?:ફોન|લાઈન|લાઇન)\s*ચાલુ\s*રાખ|(?:લાઈન|લાઇન)\s*પર\s*રહ",
                        re.IGNORECASE)
# "બે મિનિટ પછી ફોન કરો", "પછી ફોન કરજો", "હું સામેથી ફોન કરું", "busy છું": call later, not hold
# (the line is about to go dead). A call verb with a later time, or plainly busy.
CALL_VERB = re.compile(r"(?:ફોન|કૉલ|કોલ|call|फोन|फ़ोन|कॉल)\s*(?:કરો|કરજો|કરજે|કરશો|કરીશ|કરું|કરુ|કરીએ|કરિએ|"
                       r"કરિયે|કીજિએ|કરના|કરૂંગા|કરુંગા|કરેંગે|કર|करो|कीजिए|करना|करिए|करूँगा|करूंगा|करेंगे|कर)(?![઀-૿ऀ-ॿ])",
                       re.IGNORECASE)  # (a whole word: not "ફોન કર્યો હતો", I called)
LATER = re.compile(r"પછી|પાછો|પાછા|પાછળથી|થોડી\s*વાર|બાદમાં|બાદ|સાંજે|સવારે|બપોરે|(?<!ગઈ )(?<!ગઇ )કાલે|પરમ|કલાક|મિનિટ|મિનીટ|"
                   r"સામેથી|અઠવાડિ|later|फिर|बाद|शाम|सुबह|कल|घंटे|ફિર|શામ|ઘંટે", re.IGNORECASE)
BUSY = re.compile(r"બિઝી|busy|બીઝી|ડ્રાઇવ|ડ્રાઈવ|driving|ગાડી\s*ચલાવ|મીટિંગ|meeting|"
                  r"(?:અત્યારે|હમણાં|હમણા|અભી|अभी)\s*(?:વાત|બાત|बात)\s*(?:નહીં|નહિ|નથી|ન|नहीं)", re.IGNORECASE)
CALLBACK_NOW = ("[Note for you, not said by the customer: they are asking to be called back later, not to "
                "hold the line. If they said when, say you'll call then (e.g. \"સારું, હું સાંજે ફોન કરું છું. "
                "આવજો.\") and end the call; if not, ask once when to call, then end. Don't press for the "
                "payment now.]")

# Gujarati speech recognition writes Hindi in Gujarati script, so Gemini tends to read it as
# Gujarati and answer in Gujarati. These words tell the two apart: each is said in one language
# only. Not here, because Gujarati says them too: "પર" ("WhatsApp પર"), "કા"/"કી" (Kathiyawadi
# "કાં"), "તક" (a chance), "સાથ", "ઠીક" ("ઠીક છે"), "હમ" (a listening noise), "હાં", "નહીં", "જી".
HINDI_WORDS = {"હૈ", "હૈં", "હોગા", "હોગી", "જાએગા", "જાયેગા", "જાએંગે", "જાયેંગે", "કો", "અભી", "અગલે", "અગલા",
               "કબ", "ક્યા", "ક્યોં", "મૈં", "હમારા", "હમારે", "હમને", "મુઝે", "આપકા", "આપકો", "કુછ", "ઔર",
               "દૂંગા", "દુંગા", "દેંગે", "દેગા", "કરુંગા", "કરૂંગા", "કરેંગે", "કરના", "કરતે", "સકતે", "સકતા",
               "પાએગા", "પાએગી", "પાયેગા", "ભેજ", "ભેજૂંગા", "ભેજુંગા", "ભેજેંગે", "ભેજિએ", "દીજિએ", "કીજિએ",
               "રહા", "ચલ", "બોલિએ", "બોલિયે", "લેકિન", "દેખતે", "દેખેંગે", "બાત", "દિન", "કલ", "શામ"}
GUJARATI_WORDS = {"છે", "છું", "છો", "નથી", "તમે", "મને", "હું", "અમે", "મારે", "તમારું", "આવતા", "આવતી", "આવતે",
                  "મોકલી", "મોકલીશ", "મોકલું", "કરીશ", "કરું", "દઈશ", "દઉં", "આપું", "આપીશ", "જોઉં", "થઈ", "શું",
                  "કેમ", "હમણાં", "હમણા", "પછી", "ક્યારે", "જશે", "આવશે", "થશે", "હતું", "હતા", "હતી", "કાલે",
                  "કરજો", "આપજો", "મોકલજો", "દેજો", "લેજો"}

HINDI_NOW = ("[Note for you, not said by the customer: they are speaking HINDI. Reply in simple, polite "
             "spoken Hindi (આપ, ભેજેંગે, કરેંગે), not Gujarati, still written in Gujarati script, e.g. "
             "\"જી, ઠીક હૈ. તો બાકી કા પેમેન્ટ કબ તક હો જાએગા?\"]")


# ---------- the checker's words (guard.py) ----------

# Things she never brings up (the owner decides them, or they're never said at all). Matched on
# words, so "ભાવ" in "ભાવનગર" doesn't count.
NEVER = {
    "discount": ["ડિસ્કાઉન્ટ", "discount", "છૂટ", "છૂટછાટ", "કસર", "કમિશન", "રાહત"],
    "interest or penalty": ["વ્યાજ", "interest", "ઇન્ટરેસ્ટ", "પેનલ્ટી", "penalty", "દંડ", "ચાર્જ", "ચાર્જીસ",
                            "ફી", "fee", "સરચાર્જ"],
    "legal threat": ["કોર્ટ", "court", "વકીલ", "કેસ", "લીગલ", "legal", "નોટિસ", "notice", "પોલીસ", "શાખ", "આબરૂ", "બદનામી", "ઇજ્જત", "ઈજ્જત"],
    "stopping supply": ["સપ્લાય બંધ", "માલ બંધ", "ઓર્ડર બંધ", "બ્લોક", "block", "બ્લેકલિસ્ટ", "blacklist"],
    "rate": ["ભાવ", "rate", "રેટ", "કિંમત", "પ્રાઇસ", "પ્રાઈસ", "price", "એમઆરપી", "mrp"],
}
# Phrases, not single words: "ઓછું કરી આપીશું" (we'll reduce it), "માફ કરી દઈશું" (we'll waive it,
# but "માફ કરજો" is "sorry"), any percentage but 100 ("સો ટકા" is "definitely"); supply held,
# stopped or cancelled ("ઓર્ડર નહીં મળે", "ટ્રક રોકી દીધી", "ડિલિવરી ... બંધ"); a name spoiled.
_NUMBER_WORD = "(?:" + "|".join(sorted((w for w, v in extract.NUMBER_WORDS.items()
                                        if isinstance(v, int) and v < 100 and not w.isascii()), key=len, reverse=True)) + ")"
NEVER_PHRASES = {
    "discount": re.compile(
        r"(?<![\d.])(?!100\b)\d{1,2}(?:\.\d+)?\s*(?:%|ટકા|પર્સન્ટ|percent)"
        r"|" + _NUMBER_WORD + r"\s*(?:%|ટકા|પર્સન્ટ)"
        r"|(?<![઀-૿])(?:ઓછ[ુંાીો]+|કમ)\s+(?:કરી|કર|આપ|ભર|ચૂકવ|ચુકવ|લઈ|લે|દે|ચાલશે|ગણ|રકમ|પૈસા|રૂપિયા)"
        r"|વેવ\s*કર|waive|રાઉન્ડ\s*ઓફ|round\s*off|સેટલ\s*કર|settle"
        r"|કાપી\s*(?:ને|લ|દ|આપ)|બાદ\s*(?:કરી|કર)\s*(?:દ|આપ|લ)|જતું\s*કર"
        r"|માફ\s*(?:પણ\s*)?(?:કરી\s*(?:દ|શક|આપ)|કરીશ|કરીએ|કર\s*દ|થઈ\s*જ|થશે|હો\s*જ)"),
    "stopping supply": re.compile(
        r"(?:ઓર્ડર|માલ|સામાન|સપ્લાય|ડિલિવરી|ડિસ્પેચ|બુકિંગ|ડીલરશીપ|ડીલરશિપ|લાયસન્સ|ગાડી|ટ્રક|પાઇપ|પાઈપ"
        r"|order|supply|delivery|booking|dealership)[^.?!।]{0,40}?"
        r"(?:બંધ|રોક|અટકાવ|હોલ્ડ|hold|કેન્સલ|cancel|સસ્પેન્ડ|suspend|રદ|કાપ|(?:નહીં|નહિ|નઈ|नहीं)\s*"
        r"(?:મળે|મળશે|આપ|મોકલ|આવે|મિલ|ભેજ|નીકળે|ઉપડે|થાય|થશે|જાય|થવા|રવાના|અનલોડ|લોડ|ડિસ્પેચ))"
        r"|(?:પેમેન્ટ|પૈસા)[^.?!।]{0,30}(?:પછી|વિના|વગર)\s*(?:જ\s*)?[^.?!।]{0,30}"
        r"(?:ડિસ્પેચ|રવાના|લોડ|મોકલ|નીકળ|ઉપડ)"),  # "પેમેન્ટ આવે પછી જ રવાના થશે"
    "legal threat": re.compile(r"કાયદ|ફરિયાદ\s*(?:નોંધાવ|કરવી|કરીશ|કરશું|દાખલ)"
                               r"|(?:પોલિસ|પુલિસ)(?:માં|ને|નો|ની|થી)?(?![઀-૿])|નામ[઀-૿]*\s+(?:\S+\s+)?(?:ખરાબ|બગાડ)|બગાડ[^.?!।]{0,12}(?:નામ|શાખ)"
                               r"|સંબંધ[઀-૿]*\s+(?:\S+\s+)?(?:પૂરા|તોડ|બંધ|ખતમ)"),
}
# She offers something herself ("...લઈ લઈશું", "કરી આપીશું", "ચાલશે"): not a hand-over, even if
# the owner is named in the same sentence.
OFFER = re.compile(r"ઈશું|ીશું|ઈશ\b|આપશું|કરશું|ચાલશે|દઈએ|લઈએ|દેંગે|કર દેંગે")
# A sentence that hands the topic over ("ડિસ્કાઉન્ટ બાબતે શેઠ તમને ફોન કરશે") may name it. (A false
# block here costs little: she says the standard hand-over line instead.)
HANDING_OVER = re.compile(
    r"ફોન કરશે|ફોન કરી લેશે|વાત કરી લેજો|વાત કરશે|વાત કરી લેશે|કૉલ કરશે|કોલ કરશે|ફોન જોડ|ચર્ચા કરી લેજો"
    r"|નક્કી કરશે|નક્કી કરે|નક્કી કરજો|વાત કરાવ|વાત કરવી|ફોન કરજો|વાત મુકીશ|જ કહેશે|જણાવશે|જણાવીશ|જણાવું|નિર્ણય લેશે|સત્તા નથી|बात कर|फोन कर|ફોન કરેંગે|બાત કર")

CURRENCY = ("રૂપિય", "રૂ", "rupee")


SUFFIXES = ("", "માં", "મા", "નો", "ના", "ની", "નું", "ને", "થી", "નુ", "વાળા", "વાળું", "ે", "ો", "s")
REST = ("બાકીના", "બાકીનું", "બાકીનો", "બાકીની", "અડધા", "અડધું", "હપ્તા", "હપ્તે", "હપ્તો")
WHOLE = re.compile(r"પૂરા|પુરા|પૂરેપૂરા|પૂરું|આખું|આખી|આખા|સંપૂર્ણ|બધા\s*પૈસા|બધું\s*પેમેન્ટ|કુલ|ટોટલ|total|full")
