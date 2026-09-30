# Voice Agent Pipeline — Read-Only Analysis

Scope: `transport/agent_connector_stream.py`, `transport/livekit_session_stream.py`,
`transport/conversation_handler.py`, `voice_io/stt_stream_final.py`, `voice_io/tts_stream.py`,
`voice_io/vad_stream.py`.

All fixes below are suggestions to apply yourself, one at a time.

---

## Per-file summaries

1. **`transport/agent_connector_stream.py`** is the entry point. It connects to the room, opens one
   Deepgram TTS websocket that the whole process shares, publishes Ava's 24 kHz output track,
   registers the `track_subscribed` handler, and then waits forever. When someone joins it clears
   `conversation_history`. When they leave it only logs.
2. **`transport/livekit_session_stream.py`** creates and publishes the output `AudioSource`. For every
   audio track it subscribes to, it starts `handle_conversation(...)` as a task and keeps no reference
   to it.
3. **`transport/conversation_handler.py`** is the core of each track's session. It opens STT, forwards
   16 kHz frames to both Deepgram and the VAD, and cuts Ava off when the VAD sees speech while she's
   talking. When STT reports end of turn, it cancels the previous turn and starts
   `process_transcript`. That function streams the LLM reply, splits it into sentences, sends each
   sentence to TTS, and pushes the returned audio into the `AudioSource`, with a check that drops
   audio from an old turn.
4. **`voice_io/stt_stream_final.py`** is a Deepgram Flux (listen v2) client stored in module globals
   (`ctx`, `connection`, `on_turn_end`). It prints interim `Update` transcripts and passes the
   `EndOfTurn` transcript to the callback.
5. **`voice_io/tts_stream.py`** holds one persistent Deepgram Aura websocket. It counts flushes still
   waiting to finish, has a single replaceable chunk handler, and implements `stop()` by sending
   `Clear`. The top half of the file is dead code that's been commented out.
6. **`voice_io/vad_stream.py`** holds one global Silero model and one global byte buffer. It cuts
   incoming audio into 512-sample chunks and returns a True/False speech result for each one.

### Dependencies the pipeline relies on

- `agent_core/main_loop_stream.get_agent_reply_stream` changes the `messages` list you pass it. It
  adds the user turn at the start and adds the model turn only when the stream finishes normally.
  Tool calls run synchronously.
- On the Deepgram SDK side (v7.9.0), `start_listening()` **awaits each MESSAGE callback before
  reading the next message**. It also **catches any exception a callback raises and then exits the
  listen loop**. This drives several of the findings below.
- On the LiveKit side (v1.1.18), `AudioFrame` raises `ValueError` when the data has an odd number of
  bytes. `AudioSource` has a 1000 ms queue, and `capture_frame` blocks while that queue is full.

---

## End-to-end flow as the code actually runs it

```
main(): room.connect → tts.connect (1 shared WS + _listen_task) → setup_audio_output (24k source, publish)
        → register_audio_handlers → wait forever
track_subscribed (audio) → ensure_future(handle_conversation(track, source, tts))
handle_conversation:
  stt_connect()  → sets GLOBAL ctx/connection
  stt_on_turn_end(handle_turn) → sets GLOBAL callback
  gather(
    forward_audio:  AudioStream(16k mono) → for each ~10ms frame:
                      await send_audio(raw)                  (Deepgram STT)
                      detect_speech(raw) → [bool per 32ms]   (Silero, sync on event loop)
                      if 3 speech chunks in a row while process_task not done → cancel_active_turn
    stt_register_listener: connection.start_listening()
        on_message(EndOfTurn) ─awaited inline─▶ handle_turn(transcript)
            await cancel_active_turn  (turn_id++, cancel tasks, clear_queue, await tts.stop → send Clear)
            process_task = ensure_future(process_transcript(...))
  )
  stt_close()
process_transcript:
  tts.set_chunk_handler(handle_tts_audio)   # replaces the single global handler
  speaker_task: queue.get → tts.send(text + Flush) … → tts.wait_until_done
  async for chunk in get_agent_reply_stream(transcript, conversation_history): split on [.!?]\s → queue
  put None → await speaker_task
TTS _listen_task: on bytes ─awaited inline─▶ handle_tts_audio → await audio_source.capture_frame (blocks when 1s queue full)
                  on Flushed → _pending_flushes -= 1 → set event when ≤ 0
```

Two things about this flow matter for several findings:

- **The STT and TTS receive loops are both blocked by your own awaits.** The STT loop waits on
  `tts.stop()`. The TTS loop is held back by playback speed, because `capture_frame` blocks whenever
  the 1 s queue is full.
- **"Ava is speaking" means `process_task` isn't done yet.** That's not the same as audio still
  playing.

---

## Findings, most severe first

### A. Incorrect or broken behavior

#### 1. Any exception inside a Deepgram callback silently kills that connection for good

- **Where:** `tts_stream.py:114-124` (`on_message`) and `stt_stream_final.py:27-38`.
- **What's wrong:** The SDK catches the exception, emits ERROR (nothing is listening for it), and
  exits `start_listening`. Some realistic triggers:
  - On TTS, `handle_tts_audio` → `rtc.AudioFrame(...)` raises `ValueError` if a websocket chunk has an
    odd byte count.
  - Also on TTS, `capture_frame` can raise.
  - On STT, `handle_turn` → `tts.stop()` → `send_clear` raises if the TTS socket has dropped.
- **Symptom:**
  - If the TTS listener dies, Ava goes permanently silent for the rest of the process. `send()` may
    still succeed, but nothing reads the replies, and `wait_until_done` blocks forever, so
    `process_task` never finishes. That leaves `is_ava_speaking` stuck at True.
  - If the STT listener dies, `gather` keeps running `forward_audio`, which keeps streaming audio to a
    socket nobody reads. Ava is deaf and nothing is logged.
- **Fix:**
  - Wrap each callback body in `try/except Exception: logging.exception(...)` so one bad message
    can't end the loop.
  - Register `EventType.ERROR` and `EventType.CLOSE` handlers that log, and on TTS, mark the
    connection dead so the next `send()` reconnects.
  - For odd byte counts, keep leftover bytes between chunks:
    ```python
    self._carry += data; n = len(self._carry) & ~1
    data, self._carry = self._carry[:n], self._carry[n:]
    ```
    Put this in the TTS handler and reset `_carry` in `stop()`. It prevents both the exception and the
    static you'd get if samples fell out of alignment.

#### 2. STT state is global, so a second session hijacks or closes the first session's STT

- **Where:** `stt_stream_final.py:5-7, 11-18, 40-41`; used by `conversation_handler.py:60, 67, 84-85`.
- **What's wrong:** Each `handle_conversation` overwrites `ctx`, `connection` and `on_turn_end`. Take
  the case where a user leaves and rejoins, or reconnects a device, while the old session's listener
  is still alive. Deepgram only closes the old socket after its idle timeout.
  - The new session sets the globals.
  - The old session's `forward_audio` has already ended, but its listener keeps running until
    Deepgram times out.
  - Then the old `stt_close()` runs `ctx.__aexit__` on the **new** `ctx`.
- **Symptom:** The rejoined user's STT closes a few seconds after they join and Ava stops hearing
  them. With two participants, both audio streams go into the second connection, and turn callbacks
  fire in the wrong session.
- **Fix:** Turn the STT module into a small class (your TODO already says this). Each session makes
  its own `SttSession` with `connect / send_audio / listen / close`, and `handle_conversation` keeps it
  in a local variable. This stays inside `voice_io` and fits your module split.

#### 3. VAD buffer and model state are global and never reset

- **Where:** `vad_stream.py:14, 16, 50-59`.
- **What's wrong:** `vad_buffer` is appended to by every session. Silero's model carries internal
  state between calls, and that state is never reset between sessions.
- **Symptom:**
  - With two audio tracks, their bytes interleave in one buffer, so the chunks are nonsense and
    speech detection is garbage.
  - After a rejoin, leftover bytes from the old session misalign the first chunk, and the model starts
    from the old session's state. That can cause a false barge-in or a missed one right after a join.
- **Fix:** Wrap it in a `VadStream` class that holds its own buffer (and ideally its own model, or at
  least call `model.reset_states()` when a session starts). Create one per `handle_conversation`.

#### 4. Participants who are already in the room are never heard

- **Where:** `agent_connector_stream.py:51-73`.
- **What's wrong:** `room.connect()` auto-subscribes to tracks that already exist. The
  `track_subscribed` handler is registered only after two more network awaits (`tts.connect`,
  `setup_audio_output`).
- **Symptom:** If the agent starts (or restarts) while a user is already in the room, their mic's
  `track_subscribed` event fires before the handler exists. The user never gets a conversation. It
  only works when the user joins after the agent.
- **Fix:** Either register the handler before `connect` and create the TTS and audio source up front,
  or loop over the existing tracks right after registering:
  ```python
  for p in room.remote_participants.values():
      for pub in p.track_publications.values():
          if pub.track and pub.kind == rtc.TrackKind.KIND_AUDIO:
              start_session(pub.track, p)   # same code path as on_track_subscribed
  ```

#### 5. Conversation history is left inconsistent when a turn is interrupted

- **Where:** `conversation_handler.py:42` together with `main_loop_stream.py:24/63`.
- **What's wrong:** The user message is added before streaming starts. The model message is added
  only if the stream finishes. A barge-in cancels in between.
- **Symptom:** History ends up with user, user in a row, and no record of what Ava actually said
  before she was cut off. The model then repeats itself or answers as if its half-finished reply was
  never heard. After several interruptions, history keeps collecting orphaned user turns.
- **Fix:** In `process_transcript`, keep the text you actually sent to TTS. Wrap the LLM loop in
  `try/except CancelledError`. On cancel, add `Content(role="model", parts=[text of spoken_so_far])`
  (possibly marked as interrupted), then re-raise. This way the transport layer owns what happened,
  and the agent core stays unaware of cancellation.

#### 6. A failure in the LLM or TTS leaves a stuck `speaker_task` and an exception nobody sees

- **Where:** `conversation_handler.py:38-56`.
- **What's wrong:** If `get_agent_reply_stream` raises (network error, rate limit, 5xx), the `None`
  sentinel is never queued. `speaker_task` waits on `sentence_queue.get()` forever. `process_task`
  dies with "Task exception was never retrieved", which only shows up when the task is
  garbage-collected. If `tts.send` raises instead, `speaker_task` dies, and `await speaker_task`
  re-raises into a task nobody awaits.
- **Symptom:** The user gets silence and no log line.
- **Fix:** Wrap the body in
  `try: ... except Exception: logging.exception(...) finally: speaker_task.cancel()` (or put `None` in
  the queue in `finally`). Also call `gen.aclose()` in `finally` on the LLM async generator, so the
  Gemini HTTP stream closes right away on cancel instead of whenever it's garbage-collected.

#### 7. Session cleanup only happens if everything goes well

- **Where:** `conversation_handler.py:84-85`.
- **What's wrong:**
  - When the participant leaves, `AudioStream` sends end-of-stream and `forward_audio` returns. But
    `stt_register_listener` keeps waiting until Deepgram times out the idle socket, so cleanup is
    delayed and the stale STT state from finding 2 hangs around.
  - If either `gather` branch raises (for example, `send_audio` on a closed socket), `gather` does
    **not** cancel the other branch, and `stt_close()` is skipped.
  - The in-flight turn is never cancelled, so Ava can keep talking to an empty room.
  - `AudioStream` is never `aclose()`d.
- **Fix:**
  ```python
  listener = asyncio.create_task(stt.listen())
  try:
      await forward_audio()
  finally:
      await cancel_active_turn(...)
      await stt.send_close_stream()   # or just close
      listener.cancel()
      await stt.close()
      await audio_stream.aclose()
  ```

#### 8. Session tasks are fire-and-forget with no references

- **Where:** `livekit_session_stream.py:20`, `conversation_handler.py:66`.
- **What's wrong:** `asyncio.ensure_future` results aren't stored. The event loop keeps only weak
  references, so an unreferenced task can in principle be garbage-collected mid-run. More
  practically, you have no handle to cancel a session when its participant leaves.
- **Fix:** Keep `sessions: dict[participant.identity, Task]` in `livekit_session_stream`. Cancel the
  task in `participant_disconnected` / `track_unsubscribed`, and attach
  `task.add_done_callback(lambda t: t.exception() and logging.error(...))` so errors show up.
  `process_task` is already stored in `active_turn`, so that one is fine.

#### 9. Late `Flushed` messages from an interrupted turn corrupt the flush counter

- **Where:** `tts_stream.py:119-121, 130, 139-141`.
- **What's wrong:** `stop()` sets the counter to 0, but any `Flushed` still on its way from the
  cleared turn then drives it to -1, -2, and so on. Whether Deepgram sends those after `Clear` isn't
  guaranteed either way, but the TTS listener is slowed down by playback, so late messages are quite
  possible.
- **Symptom:** On the next turn, `send()` only brings the counter back to 0. `wait_until_done` then
  returns immediately, `process_task` finishes while Ava is still talking, and **VAD barge-in is
  disabled for that whole reply**.
- **Fix:**
  - Clamp the counter with `max(0, …)`.
  - Better: add a generation counter. `stop()` increments `self._gen`, and each `send()` records it.
    Simplest is to ignore every `Flushed` that arrives between `stop()` and the matching
    `SpeakV1Cleared`.
  - Also handle `SpeakV1Cleared` explicitly (see finding 10).

#### 10. Stale audio from a cleared turn can play at the start of the next turn

- **Where:** `conversation_handler.py:17-19, 28` and `tts_stream.py:116-117`.
- **What's wrong:** The turn check compares against the handler that's currently installed. Here's
  the sequence:
  - `handle_turn` cancels the old turn and sends `Clear`.
  - The new `process_transcript` immediately installs a new handler with the new `turn_id`.
  - Any old-turn audio still buffered in the websocket, or already generated before Deepgram
    processed the `Clear`, reaches the new handler and passes its check.
- **Symptom:** A fragment of the old sentence plays right before the new reply. It's most likely when
  STT's end of turn (not the VAD) is what triggered the interruption.
- **Fix:** In `PersistentTTS`, set `self._discarding = True` in `stop()`, drop every byte message
  while it's set, and clear it when `SpeakV1Cleared` arrives. That puts the boundary where it
  belongs, in the TTS protocol.

### B. Timing and fragility (works today, but brittle)

#### 11. The STT receive loop is blocked while `handle_turn` runs

- **Where:** `stt_stream_final.py:34`.
- `on_turn_end` is awaited inline, so no STT messages are read while `cancel_active_turn` →
  `tts.stop()` does its network round trip. That's small today. It gets worse if TTS is slow or you
  add anything else to `handle_turn`.
- Suggestion: have the callback be a plain function that schedules work with `create_task`, or keep
  it as fast as it is now.

#### 12. The TTS receive loop is paced by playback

- **Where:** `tts_stream.py:117` → `capture_frame`.
- `capture_frame` blocks whenever the 1 s queue is full, so control messages (`Flushed`, `Cleared`)
  sit behind audio that hasn't played yet. This is why `process_task.done()` can turn True while up
  to about 1 s of audio is still queued. Barge-in during Ava's last second is only caught by STT's end
  of turn, not by the fast VAD path.
- Suggestion: base `is_ava_speaking` on whether audio is actually playing, for example a flag cleared
  when the source's queue drains. `AudioSource` has `wait_for_playout()`, so await that in
  `speak_sentences` after `wait_until_done()`.

#### 13. The one shared `PersistentTTS` never reconnects

- **Where:** `agent_connector_stream.py:60-64`, `tts_stream.py`.
- The whole process has one websocket and no keepalive, reconnect, or `close()`. Any idle timeout or
  network blip makes Ava permanently mute (and see finding 1). Its single `_current_on_chunk` slot
  also means two sessions at once would steal each other's audio.
- Suggestion: either one TTS per session, or lazy reconnect inside `send()` when
  `self._listen_task.done()`.

#### 14. `conversation_history` is a module global cleared from a different module

- **Where:** `conversation_handler.py:10`, `agent_connector_stream.py:8, 40`.
- Two files manage it: one owns it, the other resets it. `clear()` on a participant join also changes
  the list while a running `process_transcript` may be streaming against it. And with two
  participants they'd share one history.
- Suggestion: create the history list inside `handle_conversation` (one per session), pass it into
  `process_transcript`, and drop the join handler's `clear()`. The session's lifetime then defines the
  history's lifetime.

#### 15. Nothing checks that frame sizes and sample rates actually match

- **Where:** `conversation_handler.py:20-26`, `livekit_session_stream.py:6`, `tts_stream.py:110`.
- `samples_per_channel = len(data)//2` and the hard-coded 24000/1 assume Deepgram's output format
  matches `AudioSource`. The 24000 is written in three places. Change the TTS sample rate or provider
  in one place and you get chipmunk audio or `ValueError`s.
- Suggestion: have `PersistentTTS` expose `sample_rate` / `num_channels` attributes, and have both
  `setup_audio_output` and `handle_tts_audio` read from them.

#### 16. Constants are duplicated across files

- `SAMPLE_RATE=16000` is defined in 4 files, and `livekit_session_stream.py:5` never uses it.
  `TTS_SAMPLE_RATE` is in 2 files. `SPEECH_CONFIRM_CHUNKS` is in 2 files, and the VAD copy is unused.
- For the voice_io/transport split, a clean rule: `voice_io` modules define the audio format they need
  and expose it, and `transport` imports it rather than redefining it.

#### 17. VAD inference runs synchronously on the event loop

- **Where:** `vad_stream.py:67`.
- One Silero forward pass every 32 ms is cheap on one stream. With several participants, or a slow
  CPU, it delays websocket reads and `capture_frame` pacing, which you'd hear as choppy output.
- Suggestion: wrap it in `torch.no_grad()`. If it becomes an issue, move it off the loop with
  `asyncio.to_thread`.

#### 18. Blocking tool calls stall the whole pipeline

- **Where:** `main_loop_stream.py:56` (a dependency, noted only).
- `tool_name(**tool_call.args)` is synchronous. If the booking tool does network I/O, audio
  forwarding, VAD and TTS playback all freeze during that call.

#### 19. Echo may cause false barge-ins

- Barge-in relies entirely on the client's echo cancellation. A participant without it (phone bridge,
  SIP, some native clients) would have Ava's own voice trip the VAD after about 96 ms and cancel her
  turn.

### C. Minor observations

- **Empty `EndOfTurn` still cancels the current turn.** `process_transcript`'s whitespace check
  (`conversation_handler.py:14`) runs after `handle_turn` has already cancelled the in-flight turn.
  Move the check into `handle_turn`, before the cancel.
- **Repeated cancels.** After a VAD-triggered cancel, `task.cancel()` doesn't make `done()` true
  immediately, so for a frame or two `is_ava_speaking` can still be True. A second cancel may fire,
  incrementing `turn_id` again and sending another `Clear`. It's harmless but noisy. Setting
  `active_turn["process_task"] = None` inside `cancel_active_turn` fixes it.
- **Sentence splitting misses the last punctuation.** The regex `[.!?]\s` doesn't split on
  punctuation at the very end of a chunk until more text arrives. It also splits "Dr. Smith" and
  "3.5". This only affects latency and prosody.
- **Logging style is inconsistent.** Some files use `print` and others use `logging`.
  `logging.basicConfig` is set in the entry point but `print` is used in the pipeline.
- **Dead code.** `tts_stream.py` lines 9–97 and its repeated imports (57–60) are unused.
- **Misleading comment.** `vad_stream.py:71` mentions `.item()`, but the code compares a tensor
  directly (`prob > VAD_THRESHOLD` gives a bool tensor). It works in an `if`, but adding `.item()`
  would make the result a plain `bool`.
- **Shutdown isn't graceful.** `asyncio.Event().wait()` never returns, so `tts.close()` and
  `room.disconnect()` never run on Ctrl-C.

---

## On the module split

It's respected. The only mild leak is that transport (`conversation_handler`) has to know TTS
internals like the sample rate and turn-drop rules that really belong to TTS (findings 10 and 15).
Moving those into `PersistentTTS` strengthens the split rather than breaking it.

## Suggested order to apply

1. Findings 1, 7 and 6, which make failures visible and stop the pipeline dying silently.
2. Finding 4.
3. Findings 2 and 3 together, since both change `voice_io` to one instance per session.
