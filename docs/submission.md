# Submission: write-up and LinkedIn post (drafts)

## Write-up (~350 words)

**Ugharani: an AI voice agent that makes payment follow-up calls in Gujarati**

**Problem.** Gujarat's manufacturers and traders sell on credit. Their ledgers are already in
software (Tally, Miracle), but chasing payments is still a person on the phone: a staff member
paid ₹10-15k a month to call dealers, ask when the payment will come, note promises, and pass
discounts, disputes and big amounts to the owner. Traders told us this "ઉઘરાણી" call is the job
nobody has automated.

**What we built.** કાવ્યા, an AI accounts assistant for Genius Polyplast (a real pipe-fittings
maker in Gondal, used with permission). The owner sees who is due today and taps "call"; Kavya
phones the dealer (a browser phone stands in for the phone line), greets them like a person
("હેલો રમેશભાઈ?"), and gets a date, amount and payment mode in
everyday Saurashtra Gujarati, or Hindi if the dealer speaks Hindi. After the call the owner's
dashboard shows the outcome, the promise and anything the owner must do.

**Gnani at the core.**
- **Prisma v3 live STT** (`gu-IN` websocket) hears the dealer in real time, biased with the
  dealer's name, firm and city.
- **Timbre** (voice Tarika) speaks every reply, sentence by sentence as the reply is written.
  Fixed lines are bundled clips, so they play instantly and cost no credits.

**Making it feel human.**
- Replies stream; a short "જી." or "સારું." covers thinking time.
- Talked over, she pauses within about 0.25 s. Our own speech detector on the call audio does
  this. "હા", a cough or her own echo let her continue; real words make her stop and answer.
- "એક મિનિટ" gets "હા જી, વાંધો નહીં." and patience.

**Safe for the business.**
- The owner sets her limits: a promise within 7 days, part payments only if everything comes in
  15 days. They also set the call hours, Sundays and festival days.
- Every sentence is checked in code before it is spoken. Discounts, interest, threats, prices,
  amounts on no bill and dates past the limit are never said; she hands those to the owner.
- Dues are never told to whoever else picks up.

**Built and tested.**
- 165 automated tests; a headless-browser test of the real phone page with a scripted
  microphone; Gemini role-playing 12 difficult dealers.
- Free tier throughout: Render, Gemini, GitHub Actions.

**Next.** Real phone lines (the server already exchanges plain 16 kHz audio, the format telephony
media streams use), Excel and Tally import of outstanding bills, and WhatsApp statements sent
automatically.

Live demo: https://ugharani.onrender.com · Code: https://github.com/omsatodiya/ugharani

## LinkedIn post (~170 words + video)

Every trader in Gujarat who sells on credit pays someone just to make one kind of call:
"ભાઈ, પેમેન્ટ ક્યારે મોકલશો?" 📞

I built કાવ્યા, an AI voice agent that makes those ઉઘરાણી calls in Gujarati (and Hindi), for
Genius Polyplast, a real pipe-fittings manufacturer in Gondal.

🎥 In the video she:
✅ greets the dealer like a person and waits for their "હા"
✅ stops the moment you talk over her, and carries on after a "હા"
✅ gets a date, an amount and RTGS or cheque
✅ politely refuses a discount or 30 more days ("શેઠ તમને ફોન કરશે"): the owner's limits are
   checked in code before she says a word
✅ writes the notes on the owner's dashboard

Built with @Gnani AI's Prisma (live Gujarati speech recognition) and Timbre (voice), as a solo
entry from SVNIT Surat.

Try it: https://ugharani.onrender.com

#GnaniAI #GreatIndianAIInternshipChallenge #VoiceAI #Gujarati #MSME

(Tag Gnani AI's LinkedIn page itself when posting, so it's a real mention.)
