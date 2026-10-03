# Analysis — October 3rd, 2026

What was looked at: why the conversation stopped flowing smoothly after the "latency down to subsecond"
commit (`c64a4f5`), why replies are slow, and why the agent gets stuck after the first exchange.

---

## 1. Observed log (Cerebras import active, fixes 1 & 2 applied)

```
EndofTurn Yeah. Hi. Good morning. Can you tell me something about myself?
LLM first token: 5.033s
[LATENCY] T2-T1 Sentence to TTS: 0.036s
[LATENCY] T3-T2 TTS first audio: 4.499s
[LATENCY] T4-T3 Frame published: 0.183s
[LATENCY] T4-T0 TOTAL latency: 9.758s
speech confirmed
<nothing after this>
```

- Transcripts (`You:`) printed fine for the first turn.
- Cerebras first token took 5.0s and Deepgram TTS first audio took 4.5s. Both are normally ~0.3s.
- Barge-in ("speech confirmed") fired right when Ava's audio started, and then nothing moved forward.

---

## 2. Lead 1: the machine is CPU-overloaded (strong evidence)

Measured while the agent was running:

- Load average **8–13 on a 4-core machine**, so about 2–3× more work than the CPU can handle.
- Agent process (`python -m transport.agent_connector_stream`) at **~90–115% CPU**: 7.5 minutes of CPU in 8 minutes of running.
  - LiveKit `AudioEngine` thread: ~2 min CPU
  - Main event-loop thread: ~2 min CPU
  - ~8 thread-pool workers (Silero VAD via `asyncio.to_thread`): ~13s each
- VS Code / Pylance and GNOME Shell are also using significant CPU.

**Why it matters:** two unrelated cloud services (Cerebras and Deepgram TTS) got about 10× slower at the
same moment. The likely explanation is that the asyncio event loop is starved and reads their responses
late, not that both services slowed down. A starved loop also delays sending mic audio to STT, so
transcripts appear late.

The VAD, STT and TTS code has **not changed** since `c64a4f5`, so this is most likely an environment
difference, not a code regression. (It is not proven that load was lower during the good sessions.)

---

## 3. Lead 2: silent TTS listener death → permanent freeze (likely suspect)

- `voice_io/tts_stream.py:75` registers only `EventType.MESSAGE` on the TTS socket. There is no
  `EventType.ERROR` handler.
- The Deepgram SDK stops its listen loop as soon as a callback raises an exception.
- If `handle_tts_audio` (which awaits `audio_source.capture_frame`) raises even once, the TTS listener
  dies **silently**.
- After that, every later turn waits forever in `tts.wait_until_done()` for a `SpeakV1Flushed` that
  never arrives. `speaker_task` and `process_task` never finish, and Ava never speaks again.

**Early barge-in:** "speech confirmed" fired about 0.2s after Ava's first audio frame. That suggests
the VAD is picking up **Ava's own voice through the mic** (speaker → mic echo). Testing with
headphones would rule this out.

---

## 4. Issues found earlier (Oct 2, still relevant)

### 4.1 Barge-in counted during the LLM wait (fix 1 applied, uncommitted)
- Originally `is_ava_speaking = process_task and not process_task.done()`
  (`transport/conversation_handler.py`). That is true from EndOfTurn onward, **including the entire LLM
  thinking time**.
- With Cerebras (~0.3s) the window was tiny. With slower LLMs, continuing a sentence, saying "umm", or
  background noise cancels the turn.
- `SPEECH_CONFIRM_CHUNKS = 3` is only ~96ms of speech (3 × 512 samples at 16kHz).
- `speech_streak` does **not** carry over between turns. It resets to 0 on every non-qualifying chunk.

### 4.2 Split utterances become two turns (fix 2 applied, uncommitted)
- A pause mid-sentence makes Flux emit two EndOfTurns. The first turn gets cancelled and leaves an
  unanswered user message in history.

### 4.3 History corruption on cancel (not fixed)
- `get_agent_reply_stream` appends the user message before streaming. On cancel, no assistant reply is
  appended, so history ends up with consecutive user messages.
- If a cancel lands mid tool call, an unanswered `function_call` / `tool_calls` entry stays in history.
  APIs usually reject that with a 400 error on the next request.

### 4.4 TTS flush counter can go negative (not fixed)
- `tts.stop()` sets `_pending_flushes = 0`, but late `SpeakV1Flushed` messages from cancelled sentences
  still decrement it (`tts_stream.py:71`).
- On the next turn `wait_until_done()` returns immediately, so `process_task` finishes while audio is
  still playing. Barge-in is then disabled for that turn ("sometimes barge-in works, sometimes not").

### 4.5 Stale audio leaking into the next turn (not fixed)
- `set_chunk_handler` swaps in the new turn's handler. Audio still in flight from the cancelled sentence
  passes the new handler's `turn_id` check and gets played.

### 4.6 Smaller items
- `is_ava_speaking` is calculated once per frame, so a second `cancel_active_turn` can fire inside the
  same VAD results loop.
- `vad_buffer` and the Silero model state are module-level globals, never reset across reconnects or
  participants.
- `handle_turn` is awaited inside the Deepgram STT callback, so `tts.stop()` blocks STT message handling.
- Two `SPEECH_CONFIRM_CHUNKS` constants exist. The one in `vad_stream.py` is unused; the one in
  `conversation_handler.py` is the real one.
- A handler from an old connection is never stopped after the user leaves. Its `while True` loop keeps
  reconnecting STT on a dead track.
- `agent_connector_stream.py` sets `httpx` logging to WARNING, which hides HTTP status lines (e.g.
  `429` rate-limit retries).

---

## 5. Changes after `c64a4f5` (see `CHANGES_SINCE_SUBSECOND_2026-10-02.md` for full diff)

- `agent_connector_stream.py`: auto-start for already-connected participants, clean shutdown on
  SIGINT/SIGTERM, history clear on disconnect.
- `agent_core_cerebras/main_loop.py`: `reasoning_effort="none"`, `prompt_cache_key`.
- `conversation_handler.py`: LLM import switching, plus fixes 1 & 2.
- `stt_stream_final.py`: `EndofTurn` print.
- New `agent_core_cerebras/main_loop_groq.py` (untracked).

---

## 6. Next diagnostic steps (no code changes needed)

1. **Free the CPU:** close extra VS Code windows and kill any old agent process before starting a new one.
2. **Run with asyncio debug mode:**
   ```
   PYTHONASYNCIODEBUG=1 python -m transport.agent_connector_stream
   ```
   Anything that blocks the event loop for more than 100ms prints
   `Executing <Task …> took X seconds`, which shows exactly what is blocking.
3. **When it freezes, say one more sentence:**
   - Nothing prints, not even `You:` → audio forwarding / STT side is stuck.
   - `You:`, `EndofTurn` and `Ava:` text print but no sound → TTS listener died (Lead 2).
4. **Test with headphones** to rule out Ava's voice triggering barge-in.

## 7. Candidate fixes (not applied yet)

- Add an `EventType.ERROR` handler on the TTS socket so failures print, plus a timeout on
  `wait_until_done()`.
- Stop the flush counter from going below zero.
- Raise `SPEECH_CONFIRM_CHUNKS` to ~6–8 (200–250ms).
- Clean history on a real barge-in (remove orphaned user message / dangling tool call).
