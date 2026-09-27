# Pipecat Low-Latency Voice Pipeline Notes

Findings from the Pipecat source (commit `2967e1c09`), gathered as a reference for building a hand-rolled LiveKit + Deepgram STT/TTS + Gemini pipeline with sub-second latency (user stops speaking → agent audio starts).

All paths are relative to `pipecat/src/pipecat/`.

---

## 1. Streaming LLM tokens into TTS

**Files:** `services/tts_service.py` (`TTSService._process_text_frame`), `utils/text/simple_text_aggregator.py` (`SimpleTextAggregator`), `utils/string.py` (`match_endofsentence`)

- **What counts as "enough":** one complete sentence, with no minimum length. LLM tokens go into a buffer one character at a time. A sentence-ending character (`. ! ? ; …` plus CJK, Indic and Arabic equivalents) marks a *possible* boundary.
- **One character of lookahead:** it doesn't split on the period itself. It waits for the next non-space character, then asks a sentence tokenizer (the `sentencex` library) to confirm. So `"Hello. N"` releases `"Hello."` right away, while `"Dr. S"` and `"$29.9"` stay buffered. Only the confirmed sentence is sent to TTS; the lookahead character stays in the buffer. The code comments say waiting for a whole next word instead added up to ~297 ms.
- **Unclear cases:** if the tokenizer isn't sure (`"...you and I. D"`), it checks once more when that next word ends. It never checks partial words, so `"Albert I. Do..."` doesn't split early.
- **End of response:** when the LLM finishes, whatever is left is sent as-is. For Deepgram it also sends a `Flush` message so the server speaks its buffered text.
- **Alternative mode:** `TextAggregationMode.TOKEN` skips buffering and sends every token straight to TTS. Use it only with a TTS that does its own buffering.
- **Context IDs:** all sentences from one LLM turn share one TTS context ID (`reuse_context_id_within_turn=True`). Deepgram just gets several `Speak` messages on the same socket, then one `Flush`.

## 2. Interruption

**Flow:** the user turn starts → `InterruptionFrame` is sent through the whole pipeline → each stage cancels its own work.

- **Trigger:** `processors/aggregators/llm_response_universal.py` → `_on_user_turn_started` calls `broadcast_interruption()`. By default a VAD speech start or any transcript starts a user turn. `turns/user_start/min_words_user_turn_start_strategy.py` is an option that requires N words while the bot is speaking (but only 1 when it isn't), which avoids "uh-huh" interruptions.
- **Priority:** the interruption is a system frame, so it skips each stage's normal queue.
- **Cancelling the LLM:** `processors/frame_processor.py` → `_start_interruption`. Every stage runs its work in a per-stage task. On interruption that task is cancelled and recreated, and queued frames are dropped. Frames marked uninterruptible, such as function-call results, are kept. The Gemini streaming loop (`services/google/llm.py`) runs inside that task, so cancelling it kills the stream. A `finally` block calls `aclose()` on the response to release the HTTP stream.
- **Cancelling TTS:** `TTSService._handle_interruption`
  - clears the sentence buffer and the text filters;
  - cancels the task that drains the per-context audio queues, then recreates it;
  - resets the ordering queue;
  - calls `on_audio_context_interrupted` for every open context. Deepgram's version (`services/deepgram/tts.py`) sends `{"type":"Clear"}` on the **same** websocket, so nothing reconnects.
  - For providers that can't clear server-side, `InterruptibleTTSService` disconnects and reconnects the websocket, but only if audio had started.
- **Clearing the output buffer, two layers:**
  - **Pipecat's own queue:** `transports/base_output.py` → `handle_interruptions` cancels the audio-writer task and makes a fresh queue. Output is written in small chunks (see §5), so at most one chunk is already in flight.
  - **LiveKit's buffer:** `transports/livekit/transport.py` (~line 1120) calls `rtc.AudioSource.clear_queue()` on interruption. That source is created with `queue_size_ms=1000`. **You need this step too:** without it, up to 1 s of queued audio keeps playing after the user starts talking.

## 3. VAD and endpointing

**Plain VAD:** `audio/vad/vad_analyzer.py` (`VADParams`) with `audio/vad/silero.py`

- `confidence=0.7`, `start_secs=0.2`, `stop_secs=0.2`, `min_volume=0.6`.
- Silero looks at 512-sample windows at 16 kHz (32 ms).
- It's a four-state machine: QUIET → STARTING → SPEAKING → STOPPING. A state only changes after the start/stop duration's worth of windows in a row.
- 0.2 s of silence is a short stop time. That's deliberate: VAD stop only means "check now". A separate layer decides whether the turn is really over.

**What ends a turn by default:** `turns/user_turn_strategies.py` uses `TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3)`.

- On VAD stop it runs **Smart Turn**, a small local model that looks at the last ≤8 s of audio (plus 500 ms before speech started) and returns a "turn complete" yes/no with a probability (`audio/turn/smart_turn/base_smart_turn.py`).
- If it says incomplete, a fallback of 3 s of silence (`STOP_SECS = 3`) forces the turn to end.
- **Waiting on STT:** the turn can end once the model says complete *and* a transcript is in. On VAD stop, Deepgram STT sends a `Finalize` message (`services/deepgram/stt.py` ~line 809). A transcript returned with `from_finalize` counts as final, so the turn ends immediately.
- **Safety net:** a timer of `ttfs_p99_latency` (Deepgram: 0.35 s, `services/stt_latency.py`), measured from when the user actually stopped speaking.

**Simpler option:** `SpeechTimeoutUserTurnStopStrategy` uses a fixed 0.6 s silence (`user_speech_timeout`) plus the same STT safety net.

**Faster endpointing:**

- **LLM-judged completion:** `FilterIncompleteUserTurnStrategies` with `turns/user_turn_completion_mixin.py`. The LLM is asked to start each reply with a marker: `●` complete, `◐` incomplete-short, `○` incomplete-long. If the reply is marked incomplete, it isn't spoken; the system waits 5 s or 10 s and then prompts the LLM again. So the LLM, rather than silence, decides whether the user was finished.
- **Eager end-of-turn (speculative LLM call):** `EagerUserTurnStrategies` / `turns/user_stop/eager_user_turn_stop_strategy.py`, with `turns/speculation_gate.py`.
  - Deepgram **Flux** STT (`services/deepgram/flux/stt_base.py`) sends an `EagerEndOfTurn` event (`eager_eot_threshold`, default 0.5) before the final `EndOfTurn` (`eot_threshold`, 0.7–0.8).
  - Pipecat starts the LLM call on the eager transcript. The LLM service's output is **held** by the speculation gate until the turn is confirmed.
  - It's thrown away if a `TurnResumed` event arrives, if the final transcript doesn't match (exact or normalized match), or after 5 s.

## 4. Concurrency

- **Stages run independently:** every pipeline stage has its own queue and its own asyncio task. STT, LLM, TTS and output all run at the same time and hand frames downstream.
- **STT keeps running while TTS plays:** input audio feeds VAD and STT the whole time. That's what makes barge-in possible. Muting input during bot speech is an opt-in feature (`turns/user_mute/*`), off by default.
- **TTS overlaps the LLM:** sentence 1 is sent to TTS while the LLM is still generating sentence 2. TTS audio is received in a background task, separate from the text path, so text and audio flow in parallel.
- **LLM start timing:** by default the LLM starts only after a final transcript. Interim transcripts only help decide when the user turn *starts* (i.e. interruption). The only case where the LLM starts before the final transcript is the eager/speculative path in §3. Pipecat uses end-of-turn predictions for that, not raw interim transcripts.

## 5. Audio chunking

- **TTS input side:** the Deepgram websocket version passes each binary message straight through as audio. There's no minimum buffer, so playback starts with the first bytes.
  - For HTTP TTS, `TTSService.chunk_size` is 0.5 s of audio (`sample_rate × 0.5 × 2` bytes) per read, so the rest can download while it plays (`DeepgramHttpTTSService` uses `iter_chunked(chunk_size)`).
  - `_stream_audio_frames_from_iterator` only aligns bytes to whole 16-bit samples and resamples if needed.
- **Output transport side:** `transports/base_output.py` re-splits all output into `audio_out_10ms_chunks × 10 ms` = **40 ms** chunks by default (`transports/base_transport.py`). The small size exists so interruption is fast: you can only cancel between chunks. The last partial chunk is padded with silence when TTS stops.
- **Bot-speaking detection:** "bot stopped speaking" fires after 0.35 s with no output audio (`BOT_VAD_STOP_SECS`).

## 6. Connection reuse and pre-warming

- **Deepgram STT:** a single persistent websocket for the whole session, with a `KeepAlive` every 5 s (Deepgram closes idle sockets after 10 s). It reconnects in a loop with exponential backoff, and gives up after too many quick failures. The generic `STTService` also has an option (`keepalive_timeout`) that sends 100 ms of silence when idle.
- **Deepgram TTS:** connects in `setup()`, at pipeline start and before the first turn. One socket for the whole session. Each turn is `Speak`… then `Flush`; an interruption is `Clear`. It reconnects lazily in `run_tts` if the socket was closed. Base reconnect logic is in `services/websocket_service.py` (backoff 4–10 s).
- **HTTP services:** they're given a shared `aiohttp.ClientSession` so connections are pooled. The Gemini `genai.Client` is created once and reused.
- **Explicit prewarm example:** `services/assemblyai/stt.py`. On *VAD user started speaking*, it fires a request to a `/v1/warm` endpoint so DNS, TCP and TLS are set up before the real request. You could use the same trick for Gemini: send a cheap request on VAD start so the HTTP/2 connection is warm when the transcript lands.
- **Models load once:** Silero and Smart Turn are loaded when their objects are created, not per turn.

---

## What matters most for the sub-second goal

- **Endpointing:** keep 0.2 s VAD stop, send Deepgram `Finalize` on VAD stop, then end the turn on the finalized transcript. Add a turn-completion check (a model like Smart Turn, or Flux EOT) instead of a long silence timeout.
- **Speculative LLM:** optionally start Gemini on Flux's eager end-of-turn, and hold its output until the turn is confirmed.
- **Early TTS:** split sentences with one character of lookahead, keep one persistent Deepgram TTS socket per session, and use `Speak` per sentence, `Flush` at the end, `Clear` on barge-in.
- **Fast barge-in:** use 40 ms output chunks and call LiveKit `AudioSource.clear_queue()` on interruption.
