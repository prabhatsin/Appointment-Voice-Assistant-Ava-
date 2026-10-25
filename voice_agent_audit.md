# Voice agent audit: VAD, turn-taking and barge-in

*Audit date: 2026-10-25. Read-only review of the working tree (which includes an uncommitted switch from Groq to Cerebras). Library defaults come from the installed packages: `livekit` 1.1.20, `deepgram-sdk` 7.12.0, `silero-vad` 6.2.3, and `livekit-client` in `frontend/node_modules`.*

The most important finding: the system is a well-structured hand-built pipeline, but barge-in has four real bugs. Two of them, a counter race and the agent's final ~1 s that can't be interrupted, likely explain the "sometimes she keeps talking" note at `transport/conversation_handler.py:184`. Tool calls also have a cancel path that can leave the conversation history broken.

---

## 0. Real-time audio path

**Coming in**
1. The browser turns on the mic with no options (`frontend/src/App.jsx:74`). So it gets livekit-client's defaults: `echoCancellation`, `noiseSuppression`, `autoGainControl` and `voiceIsolation` are all true (`livekit-client.esm.mjs:21168-21171`).
2. On the server, `track_subscribed` starts `handle_conversation` for each audio track (`transport/livekit_session_stream.py:17-20`). Tracks that were already in the room are picked up at `transport/agent_connector_stream.py:58-65`.
3. `rtc.AudioStream(track, 16000, mono)` is recreated on every pass of the STT reconnect loop (`transport/conversation_handler.py:96`). It uses the default frame size and an unbounded queue (`livekit/rtc/audio_stream.py:63-66`).
4. `forward_audio` (`conversation_handler.py:132-154`) awaits three steps in a row for each frame:
   - send to Deepgram (`:139`)
   - the "observe-only" `VADStream`, which only logs (`:142-144`)
   - the legacy `detect_speech`, which actually triggers barge-in (`:145-154`)

**Speech-to-text and end of turn**
- Deepgram Flux `flux-general-en` with no turn-detection settings (`voice_io/stt_stream_final.py:28-31`).
- Only `TurnInfo/EndOfTurn` is acted on (`stt_stream_final.py:57-61`). `Update` is ignored (`:53-55`), and `StartOfTurn`, `EagerEndOfTurn` and `TurnResumed` are never handled.
- EndOfTurn calls `handle_turn` (`conversation_handler.py:98-116`).

**LLM**
- `process_transcript` (`conversation_handler.py:17-80`) calls `get_agent_reply_stream` (`agent_core_cerebras/main_loop_cerebras.py:27-112`): streaming Cerebras `qwen-3.8-27b` with tools.
- Tools run with `asyncio.to_thread` (`main_loop_cerebras.py:98`).
- Sentences are split with the regex `[.!?]\s` (`conversation_handler.py:68-75`).

**TTS and playback**
- There is one shared `PersistentTTS` Deepgram Aura websocket at 24 kHz (`voice_io/tts_stream.py:16-32`, created at `agent_connector_stream.py:48-50`).
- Each sentence is sent as `send_text` plus `send_flush` (`tts_stream.py:37-41`).
- The audio bytes go to a single global chunk handler (`tts_stream.py:22-25`), which is `handle_tts_audio` (`conversation_handler.py:22-41`). That handler checks the turn id, builds an `AudioFrame` and calls `audio_source.capture_frame` (`:37`).
- The `AudioSource` is created with the default `queue_size_ms=1000` (`livekit_session_stream.py:10`, `livekit/rtc/audio_source.py:40`).

**Stopping**

`cancel_active_turn` (`conversation_handler.py:172-179`) does four things:
- bumps `turn_id`
- cancels `process_task` and `speaker_task`
- `audio_source.clear_queue()`, which drops the buffered audio (`audio_source.py:88-100`)
- `tts.stop()`, which sends Deepgram `Clear` and resets the flush counter (`tts_stream.py:47-50`)

```
Browser mic (AEC/NS/AGC defaults)
   │ WebRTC
   ▼
LiveKit track ─▶ rtc.AudioStream 16 kHz mono ─▶ forward_audio
                                                   ├─▶ Deepgram Flux STT ─▶ EndOfTurn ─▶ handle_turn
                                                   ├─▶ VADStream (smoothed, logs only)
                                                   └─▶ detect_speech (raw) ─▶ barge-in ─▶ cancel_active_turn
handle_turn ─▶ process_transcript ─▶ Cerebras LLM (stream + tools)
                     │ sentence split
                     ▼
              PersistentTTS (Deepgram Aura 24 kHz) ─▶ handle_tts_audio ─▶ AudioSource (1 s queue) ─▶ browser
```

---

## 1. VAD

### Current approach

Two Silero models run on every frame.

- **`VADStream`** (`voice_io/vad_session.py`) is a careful, LiveKit-style implementation:
  - exponential smoothing with α=0.35 (`:14`, `:80-88`)
  - two thresholds, 0.5 to start and 0.35 to end (`:15-16`, `:95-111`)
  - 50 ms minimum speech, 550 ms minimum silence (`:18-19`)
  - 16 kHz, 512-sample (32 ms) windows (`:11-13`)

  It is **observe-only**: its results are only printed (`conversation_handler.py:142-144`).
- **`detect_speech`** (`voice_io/vad_stream.py:60-81`) is what actually drives barge-in. It uses the raw probability with a 0.5 threshold (`:11`, `:79`), no smoothing and no hysteresis. It needs 3 speech windows in a row, about 96 ms (`conversation_handler.py:14`, `:146-154`).
- Neither VAD affects end of turn. Flux handles that.
- None of the settings can be configured: they are hard-coded module constants, with nothing read from env or arguments.

### Noise, echo and the agent's own voice

- The server does no echo cancellation or noise suppression. Everything relies on the browser defaults listed above.
- Barge-in is only armed while Ava is speaking (`conversation_handler.py:141`), which is exactly when echo leaks in. Anyone on laptop speakers where the browser's echo cancellation is weak can have Ava interrupt herself.
- There is no input-volume floor (Pipecat's `min_volume`) and no noise model (Krisp, or LiveKit's BVC).

### Rating: **Basic**

The good VAD exists but isn't the one in use.

### Gaps vs. Pipecat and LiveKit

- Both frameworks feed a single smoothed VAD into one event pipeline. Here the smoothed VAD is wired to nothing and the raw one decides.
- Both frameworks have configurable settings. Pipecat's `VADParams` include confidence, start_secs, stop_secs and min_volume.
- Both have optional noise cancellation in front of the VAD.

### Bugs and risks

- **Wasted work:** two Silero inferences per window, plus two thread hops for every ~10 ms frame (`conversation_handler.py:142`, `:145`).
- **Shared global state:** `vad_stream.py` keeps one module-level model and `vad_buffer` (`:23-25`, `:61`), shared by every participant. Two tabs or users mix their audio into the same buffer and the same recurrent model state. It is also never reset on STT reconnect: only `VADStream.reset()` is called (`conversation_handler.py:92`).
- **Tensor instead of bool:** `detect_speech` appends a tensor (`prob>VAD_THRESHOLD`) rather than a bool (`vad_stream.py:79`). It works, but `.item()` is missing.
- **Back-pressure:** every frame awaits the STT send and both VAD thread hops in sequence (`conversation_handler.py:139-145`). The `AudioStream` queue is unbounded, so a slow step adds delay silently instead of dropping frames.
- **Leak:** a new `AudioStream` is created on every reconnect and the old one is never closed (`conversation_handler.py:96`).

### Top 3 fixes

1. **(S)** Use `VADStream` for barge-in: trigger on `speaking`/`speech_time`, and delete `detect_speech`. This removes the global-state bug and halves the inference cost.
2. **(S)** Move the VAD settings into a config dataclass or env. Keep LiveKit-like defaults and add a minimum volume/RMS gate.
3. **(M)** Add noise suppression before the VAD and STT (Krisp or RNNoise), and/or ask the browser for audio processing explicitly. Test with speakers rather than headphones.

---

## 2. Turn-taking (end of the user's turn)

### Current approach

Deepgram Flux's built-in end-of-turn model, a semantic and acoustic turn detector, decides when the user has finished. This is the strongest part of the stack.

On top of that, `handle_turn` has a "merge continuation" rule (`conversation_handler.py:103-110`): if the user ends a second turn before Ava has made any sound, the two transcripts are joined, the reply is cancelled, the history is rolled back and the LLM is called again.

### Mid-sentence pauses, such as phone numbers or dates

- Flux's model handles some of these, but `eot_threshold` and `eot_timeout_ms` are left at Deepgram's defaults (`stt_stream_final.py:28-31`; the SDK supports them, `deepgram/listen/v2/raw_client.py:48-49`).
- After Ava starts speaking, a pause makes her answer the first half. The README admits this ("If you pause mid-sentence…").
- The only fallback maximum timeout is Flux's internal `eot_timeout_ms`. Nothing in the app sets or watches it.

### Avoidable latency

- **No early start:** `EagerEndOfTurn` and `TurnResumed` are ignored. LiveKit's preemptive generation and Flux's eager mode both start the LLM before the turn is confirmed.
- **Wrong starting point:** T0 is taken when EndOfTurn arrives (`conversation_handler.py:99`), not when the user stopped speaking. The end-of-turn delay is never measured, so it can't be tuned.
- **Slow first sentence:** the regex needs whitespace after punctuation (`conversation_handler.py:68`), so the first sentence waits for the next token. One-sentence replies are only sent when the stream ends (`:76-78`).
- **Merging restarts the LLM:** the merge path throws away work and starts over. That is correct, but it costs a full time-to-first-token.

### Rating: **Decent**

The detector is model-based, but none of it is tuned, used early or measured.

### Gaps vs. Pipecat and LiveKit

- Both combine VAD end-of-speech with a turn model: Smart Turn in Pipecat, the EOU model in LiveKit. They use minimum and maximum endpointing delays, and LiveKit adds preemptive generation.
- Here the VAD end-of-speech event (`vad_session.py:138-140`) exists but is never compared with Flux.

### Bugs and risks

- **Blocking listener:** `on_message` awaits `on_turn_end` inline (`stt_stream_final.py:60-61`). `handle_turn` then awaits `cancel_active_turn` and `gather(prev_task)`, which blocks the STT listener while the earlier turn shuts down.
- **Missing import:** `stt_stream_final.py:119` calls `asyncio.sleep`, but `import asyncio` is commented out (`:13`). The first failed reconnect attempt raises `NameError` and falls back to the outer loop in `handle_conversation`. That fallback still recovers, but it isn't the backoff that was written.
- **Keepalive disabled:** the keepalive is commented out (`conversation_handler.py:121-130`). This matches the README's "drops after idle" limit if the browser stops sending audio frames.

### Top 3 fixes

1. **(S)** Set the Flux parameters explicitly (`eot_threshold`, `eot_timeout_ms` as the maximum fallback) and log them.
2. **(M)** Handle `EagerEndOfTurn` to start the LLM speculatively, and `TurnResumed` to cancel it.
3. **(M)** Treat the turn as not over when Ava has started speaking and the user keeps going (see barge-in). Optionally use the `VADStream` end-of-speech plus a timeout as a second signal.

---

## 3. Barge-in (interruptions)

### Current approach

While `audio_started` is true and the reply task is running (`conversation_handler.py:141`), about 96 ms of raw-VAD speech triggers `cancel_active_turn`. That bumps the turn id, cancels the LLM and speaker tasks, clears the LiveKit buffer and sends TTS `Clear`. Late TTS chunks from the old turn are dropped by the turn-id guard (`:23-24`).

### Rating: **Basic**

The flush-and-cancel mechanism exists, but nothing filters what triggers it, nothing recovers from a false trigger, and the history isn't handled.

### What works

- Queued audio is flushed (`clear_queue`) and TTS is cleared server-side.
- The LLM stream task is cancelled (`task.cancel()` on `process_task`).

### Bugs and risks, most severe first

1. **Counter race can disarm barge-in for a whole reply.**
   - `tts.stop()` sets `_pending_flushes = 0` (`tts_stream.py:48`). Any `Flushed` from Deepgram that was already in flight still decrements it (`:26-29`), so it can go negative.
   - On the next turn, `send()` only raises it back to about 0. `wait_until_done()` then returns at once (`:44`), so `process_task` finishes as soon as the LLM text is sent, before any audio plays.
   - `is_ava_speaking` (`conversation_handler.py:141`) is then false for the entire spoken reply. This likely explains the intermittent "barge-in doesn't work" note (`conversation_handler.py:184`).
2. **The last ~1 s of every reply can't be interrupted.**
   - `wait_until_done` resolves on Deepgram `Flushed`, which means generation is done, not playback.
   - `capture_frame` returns once audio is queued, and the `AudioSource` holds up to 1000 ms (`audio_source.py:40`).
   - So `process_task` finishes while up to ~1 s, plus the WebRTC jitter buffer, is still playing, and barge-in is disarmed for that stretch. This matches the README's "Interrupting near the end may not work."
3. **Interrupting during a tool call can corrupt the history or double-book.**
   - Cancelling during `await asyncio.to_thread(tool)` (`main_loop_cerebras.py:98`) doesn't stop the thread, so the booking still happens.
   - If Ava had already said something before the tool call, the history keeps the assistant `tool_calls` message (`main_loop_cerebras.py:79-90`) but never gets the `tool` result. The OpenAI-style API will most likely reject the next request, and the session stays broken until history is cleared.
   - If she hadn't, the merge path deletes the tool messages (`conversation_handler.py:109`) while the booking still goes through. The LLM doesn't know it booked, so it can book again.
4. **The history never matches what the user heard.**
   - The assistant message is only appended when the stream finishes (`main_loop_cerebras.py:111`).
   - If the interruption comes mid-stream, nothing is recorded, and the next turn sends two user messages in a row.
   - If it comes after the stream finishes, which is common because Cerebras finishes in well under a second, the full intended reply is recorded even though the user heard part of it.
   - There is no truncation at the point of interruption.
5. **Anything triggers it: no filtering of backchannels, coughs or noise.**
   - Any 96 ms above the raw 0.5 threshold interrupts, including "uh-huh", coughs, keyboard noise and echo.
   - There is no minimum duration (LiveKit's `min_interruption_duration`), no minimum word count (Pipecat's `MinWordsInterruptionStrategy`), and no check against Flux's `StartOfTurn` or the transcript.
6. **No recovery from false interruptions.**
   - If it was a cough, Ava stops and stays silent. Flux sends no EndOfTurn for an empty transcript (`stt_stream_final.py:52`), so the conversation stalls until the user speaks.
   - LiveKit resumes after a false-interruption timeout. Pipecat-style approaches pause first and only cancel once confirmed.
7. **A stale chunk can play after an interruption.**
   - A `handle_tts_audio` call that passed the turn-id check (`conversation_handler.py:23`) and is blocked in `capture_frame` (buffer full) gets room after `clear_queue()` and enqueues one old chunk.
   - The turn id isn't checked again before the capture.
8. **Interruptions in the first few hundred ms are missed.**
   - `audio_started` is set when the first TTS bytes arrive (`conversation_handler.py:26`), so the window between that and audible playback is small.
   - The real gap is between EndOfTurn and the first TTS byte: VAD barge-in is off there and only Flux EndOfTurn can merge. A short "wait—" said then is only seen as a new turn after Flux decides the turn is over.
9. **Interruption stalls the mic path.** `forward_audio` awaits `cancel_active_turn`, including a network send (`conversation_handler.py:150`), which briefly stops mic forwarding.
10. **One shared `PersistentTTS`, chunk handler and `conversation_history` for all participants.** Two tabs give doubled or crossed replies (the README admits this).

### Gaps vs. Pipecat and LiveKit

Both frameworks interrupt on VAD start plus a minimum duration or word count, then flush every queue and cancel LLM and TTS. They write a truncated or "interrupted" assistant message using word timestamps or a transcript synchronizer, and they recover from false interruptions. Pipecat also offers `STTMuteFilter` to mute user input during function calls.

### Top 3 fixes

1. **(S–M) Fix the "is Ava speaking" signal.**
   - Track playout end, not TTS `Flushed`: for example, `await audio_source.wait_for_playout()` after the last chunk, or count queued audio duration.
   - Make the flush counter per-turn (tag it with the turn id and ignore stale `Flushed`/`Cleared`). This fixes bugs 1 and 2.
2. **(M) Make the history and tool calls safe on cancel.**
   - Catch `CancelledError` in `get_agent_reply_stream`. Always append matching `tool` results, or roll back the whole tool call atomically.
   - Write the assistant message as only the sentences actually played, marked as interrupted.
   - Don't cancel a running booking: mute or ignore interruptions during side-effecting tools, or let them finish and record the result.
3. **(M) Interruption filtering and recovery.**
   - Trigger on the smoothed `VADStream` with a minimum duration of about 300–500 ms.
   - Confirm with Flux `StartOfTurn` or at least one transcribed word, and ignore a small list of backchannels.
   - Pause (stop sending audio) first, and only cancel once confirmed. If no transcript arrives within about 1.5–2 s, resume or re-say the rest.

---

## 4. Latency metrics

### What exists

`print` statements, not structured logging, in `conversation_handler.py`:
- `[LATENCY]` T1–T0, LLM first token (`:64-66`), plus a duplicate un-tagged print at `:61-63`
- T2–T1, sentence to TTS (`:50-52`)
- T3–T2, TTS first audio (`:27-29`)
- T4–T3 and T4–T0, total (`:38-41`)

T0 is when EndOfTurn arrives and T4 is when the first frame is *queued*, not when it plays.

### What's missing

| Metric | How |
|---|---|
| End-of-turn delay (user stopped → EndOfTurn) | Timestamp the `VADStream` `"end"` event (`vad_session.py:138-140`), then diff it against EndOfTurn arrival |
| VAD pickup (speech start → `"start"`) | Log the `"start"` time and `speech_time` at the event |
| True time to first audio (user stopped → first frame queued) | T4 minus the VAD end time, not minus T0 |
| Interruption to silence | Time from barge-in trigger to `clear_queue` return. Log the queued ms that were discarded |
| Tool-call duration | Time around `to_thread` in `main_loop_cerebras.py:98` |
| Counts | Interruptions per turn, false interruptions (barge-in with no transcript within N s), merges |

Emit one structured JSON record per turn, keyed by turn id and session, through `logging` rather than `print`.

---

## Summary

| Area | Rating | Biggest gap | First fix |
|---|---|---|---|
| **VAD** | Basic | The smoothed `VADStream` only logs. Barge-in runs on a raw-threshold model with global state shared across users, and there's no echo or noise handling on the server | **S:** drive barge-in from `VADStream` and delete `detect_speech`; make the settings configurable |
| **Turn-taking** | Decent | Flux end-of-turn is used untuned and unmeasured. Eager EOT is ignored, and mid-sentence pauses after Ava starts speaking get answered early | **S:** set `eot_threshold` and `eot_timeout_ms` explicitly, and log the VAD-end-to-EndOfTurn delay |
| **Barge-in** | Basic | "Ava is speaking" is wrong: the flush-counter race and the ~1 s buffered tail disarm barge-in, and nothing filters triggers or recovers from false ones | **S–M:** track playout end and use a per-turn flush counter |
| **History on interruption** | Missing | Records either nothing or the full intended reply, never what was heard. Cancelling during a tool call can leave an orphan `tool_calls` message or cause a double booking | **M:** handle `CancelledError`, roll back tool calls atomically, write the played text marked as interrupted |
| **Latency metrics** | Basic | No end-of-turn delay, no interruption-to-silence time, and T0 is EndOfTurn arrival rather than when the user stopped speaking | **S:** structured per-turn record keyed on VAD end-of-speech |

**Bottom line:** the turn detector is good because Flux does the hard part, and the flush-and-cancel mechanism is there. The distance from Pipecat or LiveKit is mostly in what wraps that mechanism: knowing exactly when the agent is audible, filtering and confirming interruptions, recovering from false ones, and keeping the history true to what was played. Fix 1 under barge-in is small and probably fixes the intermittent bug noted at `conversation_handler.py:184`.
