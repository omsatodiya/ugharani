"""A live follow-up call: the customer's voice in, the agent's voice out.

    phone page --PCM--> server --frames--> Gnani live STT --transcript--> Gemini (stream)
    phone page <--PCM-- server <--Timbre audio, sentence by sentence--------'

The browser phone is a stand-in for a phone line: everything here sees only 16 kHz PCM16
frames in and out, so a telephony media stream could replace it later.

Turn-taking, as a person on the phone would do it:
- wait a moment for the customer's "હેલો" before the opening line
- while the agent's reply is still being written, more speech from the customer restarts it
- a reply starts with a short acknowledgement ("જી.") from a bundled clip; a filler covers a slow one
- audio is fetched a segment ahead and held back a moment, so speech never breaks up mid-word
- speech heard while the agent is still talking is treated as echo and ignored (barge-in: next)
- long silence: "હેલો? સાંભળાય છે?", then a polite goodbye
- the agent ends the call with agent.END; a hard time limit protects the credits
"""

import asyncio
import json
import logging
import random
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date

from ugharani import agent, gnani, llm, speech

log = logging.getLogger("uvicorn.error")

BYTES_PER_SECOND = gnani.TTS_SAMPLE_RATE * 2  # 16 kHz mono PCM16

# Timings in seconds; tests shorten them.
GREETING_WAIT = 1.2    # how long to wait for the customer's "હેલો" before speaking first
GREETING_HEARD = 4.0   # once they started saying something, wait this long for the transcript
FILLER_AFTER = 1.6     # reply not started by then: say a filler (the reply's own "જી." usually comes first)
PREBUFFER = 0.4        # audio held back before a segment starts, so the phone never runs dry mid-word
NO_REPLY = 8.0         # silence after the agent finishes before "hello?"
MAX_CALL = 240.0       # then wrap up, whatever is going on
ECHO_MARGIN = 0.4      # speech starting this close to the end of the agent's audio still counts
AFTER_LAST_WORD = 0.6  # pause after the goodbye before the line drops

# Fixed lines: synthesised once, then always played from the cache.
FILLERS = ["જી,", "હા,", "અચ્છા,"]
# The short acknowledgements the agent starts a reply with (agent.py asks for exactly these):
# bundled clips, so the first word of a reply plays the moment Gemini writes it.
ACKS = ["હા જી.", "જી.", "સારું.", "બરાબર.", "અચ્છા.", "હં."]
HELLO = "હેલો? સાંભળાય છે?"
NO_ANSWER_BYE = "લાગે છે લાઇન બરાબર નથી. હું થોડી વાર પછી ફોન કરું છું. આવજો."
SORRY = "માફ કરજો, લાઇન થોડી ખરાબ છે. ફરી કહેશો?"
LINE_DROP_BYE = "માફ કરજો, લાઇનમાં તકલીફ છે. હું પછી ફોન કરું છું. આવજો."
FIXED_LINES = [*FILLERS, *ACKS, HELLO, NO_ANSWER_BYE, SORRY, LINE_DROP_BYE]


def time_up_bye(settings: dict) -> str:
    return f"સારું, હું આ વાત {settings['owner_name']}ને જણાવી દઉં છું. આભાર, આવજો."


SENTENCE_END = re.compile(r"(?<=[.?!।])\s+")


async def sentences(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """Re-cut a token stream into whole sentences, so each can be spoken as soon as it is complete."""
    buf = ""
    async for chunk in chunks:
        buf += chunk
        *done, buf = SENTENCE_END.split(buf)
        for s in done:
            if s.strip():
                yield s.strip()
    if buf.strip():
        yield buf.strip()


GROUP_CHARS = 160  # up to this much is spoken in one Timbre request: one intonation, no seams


async def segments(sents: AsyncIterator[str]) -> AsyncIterator[str]:
    """What to synthesise in one go.

    A leading acknowledgement goes alone (it plays from a bundled clip at once); the rest of the
    reply goes together so the voice keeps one intonation, split at sentence ends only when long.
    """
    group, first = "", True
    async for s in sents:
        if first:
            first = False
            if s in ACKS:
                yield s
                continue
        if group and len(group) + 1 + len(s) > GROUP_CHARS:
            yield group
            group = s
        else:
            group = f"{group} {s}".strip()
    if group:
        yield group


ACK = re.compile(r"^(હા|જી|હા જી|અચ્છા|બરાબર|સારું|ઓકે)[,.!]?\s+")


def drop_ack(sentence: str) -> str:
    """After a filler, 'જી, ... હા, 10 તારીખે' would stutter: drop the reply's own opening acknowledgement."""
    rest = ACK.sub("", sentence, count=1)
    return rest if rest.strip() else sentence


class LiveCall:
    """One answered call. `send_audio` / `send_event` reach the customer's phone."""

    def __init__(self, settings: dict, customer: dict, today: date, last_call: dict | None,
                 send_audio: Callable[[bytes], Awaitable[None]], send_event: Callable[[dict], Awaitable[None]]):
        self.settings, self.customer, self.today, self.last_call = settings, customer, today, last_call
        self._send_audio, self._send_event = send_audio, send_event
        self.history: list[dict] = []  # [{"who": "agent" | "customer", "text": ...}]
        self.ended_by: str | None = None  # agent, customer, no_answer, time_up, line_drop
        self.done = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self._started = self._loop.time()
        self._speaking_until = 0.0  # when the audio sent so far finishes playing on the phone
        self._heard_at: float | None = None  # the customer started talking (VAD), no transcript yet
        self._over_agent = False  # ...and the agent's audio was still playing then: likely echo
        self._last_heard = self._started
        self._turn: asyncio.Task | None = None
        self._turn_spoke = False
        self._filled = False
        self._last_filler: str | None = None  # never the same filler twice in a row
        self._again = False  # the customer spoke again while a reply was already being spoken
        self._prompted = False  # said "hello?" since the customer last spoke
        self._ending = False
        self._carry = b""
        self._fetches: set[asyncio.Task] = set()  # audio being fetched ahead of playing

    # ---------- speaking ----------

    def _now(self) -> float:
        return self._loop.time()

    async def _audio(self, pcm: bytes) -> None:
        pcm, self._carry = self._carry + pcm, b""
        if len(pcm) % 2:  # never split a sample between two messages
            pcm, self._carry = pcm[:-1], pcm[-1:]
        if pcm:
            self._speaking_until = max(self._now(), self._speaking_until) + len(pcm) / BYTES_PER_SECOND
            await self._send_audio(pcm)

    def _fetch(self, text: str) -> asyncio.Queue:
        """Start getting `text`'s audio now; its chunks (then None, or an exception) arrive on the queue."""
        out: asyncio.Queue = asyncio.Queue()

        async def run():
            t0, first, size = self._now(), None, 0
            try:
                async for chunk in speech.stream_pcm(text):
                    first = first or self._now()
                    size += len(chunk)
                    await out.put(chunk)
                await out.put(None)
            except Exception as e:  # handed to whoever plays it
                await out.put(e)
                return
            took, audio = self._now() - t0, size / BYTES_PER_SECOND
            log.info("tts: first audio %.2fs, done %.2fs for %.1fs of speech (%.1fx real time): %s",
                     (first or self._now()) - t0, took, audio, audio / took if took else 0, text[:40])

        task = asyncio.create_task(run())
        self._fetches.add(task)
        task.add_done_callback(self._fetches.discard)
        return out

    async def _play(self, text: str, out: asyncio.Queue) -> None:
        """Send one segment's audio, holding back PREBUFFER of it first: Timbre's first chunks come in
        bursts, and a phone that has started a word must not run dry before the rest arrives."""
        need = PREBUFFER * BYTES_PER_SECOND
        held: bytearray | None = bytearray()
        while (chunk := await out.get()) is not None:
            if isinstance(chunk, Exception):
                raise chunk
            if held is not None:
                held += chunk
                if len(held) >= need:
                    await self._audio(bytes(held))
                    held = None
            else:
                gap = self._now() - self._speaking_until
                if gap > 0.02:
                    log.info("call: the phone ran dry for %.2fs mid-sentence", gap)
                await self._audio(chunk)
        if held:
            await self._audio(bytes(held))
        await self._send_event({"type": "line", "who": "agent", "text": text})

    async def say(self, text: str) -> None:
        await self._play(text, self._fetch(text))

    def _add(self, who: str, text: str) -> None:
        if self.history and self.history[-1]["who"] == who:
            self.history[-1]["text"] += " " + text  # one turn, said in two breaths
        else:
            self.history.append({"who": who, "text": text})

    def speaking(self) -> bool:
        return self._now() < self._speaking_until

    async def _until_quiet(self) -> None:
        await asyncio.sleep(max(0.0, self._speaking_until - self._now()))

    async def hang_up(self, reason: str, last_words: str | None = None) -> None:
        if self._ending:
            return
        self._ending = True
        try:
            if last_words:
                await self.say(last_words)
                self._add("agent", last_words)
            await self._until_quiet()
            await asyncio.sleep(AFTER_LAST_WORD)
            await self._send_event({"type": "end"})
        finally:
            self.ended_by = reason
            self.done.set()

    # ---------- the agent's turn ----------

    async def _filler_later(self) -> None:
        await asyncio.sleep(FILLER_AFTER)
        if not self.speaking():
            self._last_filler = text = random.choice([f for f in FILLERS if f != self._last_filler])
            pcm = speech.cached_pcm(text)
            if pcm is not None:  # only ever a cached clip: a filler must be instant
                await self._audio(pcm)
                self._filled = True
                log.info("call: filler %s", text)

    async def _reply(self) -> None:
        self._turn_spoke = False
        self._filled = False
        heard_at = self._now()
        filler = asyncio.create_task(self._filler_later())
        spoken: list[str] = []
        hang = False
        system = agent.system_prompt(self.settings, self.customer, self.today, self.last_call)
        ready: asyncio.Queue = asyncio.Queue()  # (text, audio queue) in speaking order; None at the end

        async def write():
            """Gemini's reply, cut into segments; each segment's audio is fetched as soon as it exists."""
            nonlocal hang
            try:
                async for seg in segments(sentences(llm.stream(system, self.history))):
                    text, end = agent.split_end(seg)
                    hang |= end
                    if not text:
                        continue
                    if self._filled and not self._turn_spoke:
                        if text in ACKS:
                            continue  # the filler already acknowledged
                        text = drop_ack(text)
                    log.info("turn: segment ready %.2fs after the customer: %s", self._now() - heard_at, text[:40])
                    await ready.put((text, self._fetch(text)))
                await ready.put(None)
            except Exception as e:
                await ready.put(e)

        writer = asyncio.create_task(write())
        try:
            while (item := await ready.get()) is not None:
                if isinstance(item, Exception):
                    raise item
                text, audio = item
                filler.cancel()
                if not self._turn_spoke:
                    log.info("turn: first audio %.2fs after the customer", self._now() - heard_at)
                self._turn_spoke = True
                await self._play(text, audio)
                spoken.append(text)
        except (llm.LLMError, gnani.GnaniError) as e:
            log.warning("call: reply failed: %s", e)
            filler.cancel()
            if not spoken:
                await self.say(SORRY)
                spoken.append(SORRY)
        finally:
            filler.cancel()
            writer.cancel()
            if spoken:
                self._add("agent", " ".join(spoken))
        if hang:
            await self.hang_up("agent")
        elif self._again:
            self._again = False
            self._turn = asyncio.create_task(self._reply())

    def _start_reply(self) -> None:
        if self._turn and not self._turn.done():
            if self._turn_spoke:
                self._again = True  # don't cut a sentence off mid-word: answer once it is said
                return
            self._turn.cancel()  # they added more before the agent answered: answer all of it
        self._turn = asyncio.create_task(self._reply())

    # ---------- the customer ----------

    def _agent_audible(self) -> bool:
        """The agent's audio has more than ECHO_MARGIN left to play: anything heard now is likely echo."""
        return self._speaking_until - self._now() > ECHO_MARGIN

    async def heard(self, event: dict) -> None:
        """A message from the live STT session."""
        kind = event.get("type")
        if kind == "speech_start":
            if self._heard_at is None:
                self._heard_at = self._now()
                self._over_agent = self._agent_audible()
        elif kind == "transcript":
            seen_start, self._heard_at = self._heard_at is not None, None
            over_agent = self._over_agent if seen_start else self._agent_audible()
            text = (event.get("text") or "").strip()
            if not text or self._ending:
                return
            if over_agent:
                log.info("call: ignored while agent speaking: %s", text)
                return
            self._last_heard = self._now()
            self._prompted = False
            self._add("customer", text)
            await self._send_event({"type": "line", "who": "customer", "text": text})
            if self.history[0]["who"] != "customer" or len(self.history) > 1:
                # (the first "હેલો" before the opening is answered by the opening itself)
                self._start_reply()
        elif kind == "error":
            log.warning("call: STT error: %s", event.get("message"))

    # ---------- the call ----------

    async def _greet(self) -> None:
        """Real calls start with the customer's "હેલો"; don't talk over it."""
        deadline = self._now() + GREETING_WAIT
        while self._now() < deadline or (self._heard_at and self._now() < self._heard_at + GREETING_HEARD):
            if self.history:  # they said hello
                break
            await asyncio.sleep(0.05)
        line = agent.opening(self.settings, self.customer)
        await self.say(line)
        self._add("agent", line)
        self._last_heard = self._now()

    async def _watch(self) -> None:
        """Silence and the time limit."""
        while not self._ending:
            await asyncio.sleep(0.2)
            busy = (self._turn and not self._turn.done()) or self.speaking() or self._heard_at
            if self._now() - self._started > MAX_CALL and not (self._turn and not self._turn.done()):
                await self.hang_up("time_up", time_up_bye(self.settings))
            elif not busy and self._now() - max(self._last_heard, self._speaking_until) > NO_REPLY:
                if self._prompted:
                    await self.hang_up("no_answer", NO_ANSWER_BYE)
                else:
                    self._prompted = True
                    await self.say(HELLO)
                    self._add("agent", HELLO)

    async def run(self, stt_events: AsyncIterator[dict]) -> None:
        """Talk until someone hangs up. The caller ends the call (customer hangup) by setting `done`."""

        async def listen():
            async for event in stt_events:
                await self.heard(event)
            if not self._ending:  # the speech service dropped the line
                log.warning("call: live STT closed")
                await self.hang_up("line_drop", LINE_DROP_BYE)

        tasks = [asyncio.create_task(c) for c in (listen(), self._greet_then_watch())]
        try:
            await self.done.wait()
        finally:
            for t in [*tasks, self._turn]:
                if t and not t.done():
                    t.cancel()
            await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)
            for t in tasks:  # surface crashes in the log instead of losing them
                if t.done() and not t.cancelled() and t.exception():
                    log.error("call: task failed", exc_info=t.exception())

    async def _greet_then_watch(self) -> None:
        try:
            await self._greet()
        except gnani.GnaniError as e:
            log.warning("call: opening failed: %s", e)
            self.ended_by = "line_drop"
            self.done.set()
            return
        await self._watch()


async def warm_up(settings: dict, customer: dict) -> None:
    """Synthesise the opening and fixed lines while the phone rings, so answering is instant."""
    for text in [agent.opening(settings, customer), *FIXED_LINES]:
        try:
            await speech.speak(text)
        except gnani.GnaniError as e:
            log.warning("call: warm-up failed for %r: %s", text, e)
            return


def browser_message(message: dict) -> tuple[str, bytes | dict | None]:
    """A starlette websocket message from the phone page: ('audio', pcm), ('hangup', None) or ('closed', None)."""
    if message["type"] == "websocket.disconnect":
        return "closed", None
    if message.get("bytes") is not None:
        return "audio", message["bytes"]
    if message.get("text"):
        try:
            body = json.loads(message["text"])
        except ValueError:
            return "ignore", None
        if body.get("type") == "hangup":
            return "hangup", None
    return "ignore", None
