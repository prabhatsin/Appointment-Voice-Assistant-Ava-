# Ava: Voice Scheduling Assistant

Ava is a voice-based scheduling assistant. You talk to her in the browser, and she checks availability, books, reschedules and cancels appointments on Google Calendar, in natural conversation.

The whole speech pipeline (STT → LLM → TTS) is **hand-built**. LiveKit Agents is deliberately not used; LiveKit provides only rooms and WebRTC transport. The project is built in phases, so every layer is written, tested and understood on its own.

**Status:** works end to end. A rewritten VAD is merged in observe-only mode; barge-in, turn handling and booking guards are still being improved (see [Roadmap](#known-issues--roadmap)).

---

## What Ava can do

- Check available appointment slots for a date
- Book, reschedule and cancel appointments (Google Calendar)
- Stream her answer sentence by sentence, so speech starts while the LLM is still generating
- Be interrupted mid-sentence (barge-in)
- Reconnect automatically when the speech-to-text socket drops
- Answer general questions and chat, not only scheduling

## Architecture

```
Browser mic ──WebRTC──▶ LiveKit room ──audio track──▶ forward_audio
                                                       │          │
                              Deepgram Flux STT ◀──────┘          └──▶ Silero VAD
                                    │ EndOfTurn                          (barge-in)
                                    ▼
                               handle_turn ──▶ Cerebras LLM (streaming + tool calls)
                                    │                         │
                                    │                         ▼
                                    │                  Google Calendar
                                    ▼  sentence by sentence
                               Deepgram TTS ──▶ LiveKit audio source ──▶ Browser speaker
```

**One turn:**
1. Mic frames arrive from the LiveKit track. `forward_audio` sends each frame to Deepgram STT, then to the VAD.
2. Deepgram Flux decides the user has finished and sends `EndOfTurn` with the transcript.
3. `handle_turn` starts a reply task (and cancels any earlier one still running).
4. The LLM streams its answer. If it calls a tool, the tool runs and the result is fed back to the model.
5. Each finished sentence goes to TTS immediately, and the audio is published to the room.

## Tech stack

| Layer | Choice |
|---|---|
| STT | Deepgram v2, `flux-general-en`, streaming WebSocket (`AsyncDeepgramClient`) |
| LLM | Cerebras `qwen-3.8-27b`, streaming, `reasoning_effort="none"` |
| TTS | Deepgram `aura-2-hera-en`, persistent streaming WebSocket |
| Transport | LiveKit (rooms, tracks, WebRTC), Python SDK |
| VAD | Silero VAD, local (runs on CPU through PyTorch) |
| Calendar | Google Calendar API |
| Language | Python 3.12, asyncio |

## Project structure

```
voice_io/
  stt_stream_final.py    STTConnection: one instance per user (connect, send_audio, listener, reconnect, close)
  tts_stream.py          PersistentTTS: one instance, created at startup
  vad_stream.py          old detect_speech(); still drives barge-in today
  vad_session.py         new VADStream: per-user VAD with smoothing, hysteresis, START/END events
  vad_listener.py        standalone test script: joins the room and prints VAD / STT events
  test_vad_logic.py      deterministic test of the VAD state machine
transport/
  agent_connector_stream.py   entry point: creates the room, TTS, audio output, registers handlers
  livekit_session_stream.py   setup_audio_output, register_audio_handlers
  conversation_handler.py     handle_conversation, forward_audio, process_transcript, cancel_active_turn
agent_core/
  main_loop_stream.py    get_agent_reply_stream: streaming LLM loop with tool calls
  system_prompt.py       build_system_prompt(): persona + rules, with today's date
  tool_schema.py         tool definitions: check_availability, book_slot, cancel_booking, reschedule
  tool_registry.py       maps tool names to Python functions (Google Calendar)
```

## Key design decisions

- **No agent framework.** STT, LLM and TTS are orchestrated manually, for learning and full control.
- **Sentence-by-sentence TTS streaming.** Audio starts as soon as the first sentence is complete.
- **`turn_id` staleness guard.** Audio from a cancelled turn is dropped.
- **`STTConnection` is a class, one per user.** It replaced module-level globals that caused shared state between users.
- **`asyncio.TaskGroup`** instead of `gather`: if one task fails, the other is cancelled.
- **Reconnect loop around the STT TaskGroup.** On a dropped socket the loop catches the error, waits 1 s and reconnects. The audio stream is created inside the loop, because a LiveKit audio stream closes after one use.
- **Model calls run off the event loop.** The VAD runs via `asyncio.to_thread`, so it never blocks audio or sockets.
- **System prompt rebuilt every turn.** Static instructions come first and the date (no clock time) comes last, so the model always knows today's date and the prompt prefix stays stable for caching (`prompt_cache_key`).
- **Tool results are checked in code.** A tool failure becomes an error result for the model instead of crashing the turn, and a per-turn set records which tools actually succeeded.
- **Tool schemas are directive.** The descriptions say which tool is the only source of truth for availability or bookings, with no example dates that could anchor the model.

## Setup

**Prerequisites:** Python 3.12, a LiveKit Cloud project, Deepgram and Cerebras API keys, Google Calendar OAuth credentials.

```bash
python3 -m venv myenv
source myenv/bin/activate
pip install livekit livekit-api deepgram-sdk silero-vad torch numpy python-dotenv google-api-python-client
# plus the Cerebras SDK you use for the async client; pin everything in requirements.txt
```

**`.env`** (loaded with `python-dotenv`):

| Variable | Purpose |
|---|---|
| `LIVEKIT_URL` | LiveKit Cloud WebSocket URL |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit credentials |
| `DEEPGRAM_API_KEY` | STT and TTS |
| `CEREBRAS_API_KEY` | LLM |

The names for the Deepgram and Cerebras keys are the SDK defaults; check them against your own `.env`.

## Run

1. **Token server and browser UI.**  
   uvicorn  transport.token_server:app --reload'
2. **Browser UI**  
  cd frontend  
  npm run dev
2. Join the room `ava-booking-room` in the browser and allow the mic.
3. Start Ava:

```bash
python3 -m transport.agent_connector_stream
```

## The VAD module (`voice_io/vad_session.py`)

A per-user Silero VAD modelled on how LiveKit implements it. Every 32 ms window goes through this chain:

| Stage | What it does |
|---|---|
| Windowing | Cuts incoming frames into exact 512-sample windows (32 ms at 16 kHz), keeping leftover bytes |
| Model | Silero returns a speech probability per window; the model keeps its own memory between windows |
| Smoothing | `0.35 × previous + 0.65 × new`, so a single odd window doesn't flip the result |
| Hysteresis | Enter speech at 0.5, stay in it down to 0.35 |
| Start/end | START after 50 ms (2 windows) of speech; END after 0.55 s of silence |
| Record | One `VADResult` per window: probability, speaking flag, event, speech and silence time |
| Executor | `analyze_audio()` runs the sync pipeline in a worker thread |

Prefix padding is skipped on purpose, because every frame already goes to STT.

**Status:** merged into `forward_audio` in observe-only mode. It prints `[VAD ] START/END` while the old `detect_speech` logic still decides barge-in.

**Tests run so far:** silence, strict START/END alternation, short and long pauses, short words ("yes", "no", "five PM"), coughs, snaps, claps, desk taps and typing, an STT cross-check, and a deterministic state-machine test. Timing is about 0.4 to 0.5 ms per 10 ms mic frame. Very short or soft words ("hey") can stay below the 0.5 bar.

```bash
python3 -m voice_io.test_vad_logic      # deterministic state-machine test (no mic needed)
python3 -m voice_io.vad_listener        # live listener; stop Ava first so she doesn't answer
```

## Latency (measured)

| Stage | Time |
|---|---|
| LLM first token | 0.35 to 0.55 s |
| TTS first audio | about 0.25 to 0.30 s |
| Frame published | about 0.001 s |
| **End to end (no tool call)** | **about 0.6 to 0.9 s** |
| Turns with a Calendar tool call | about 1.4 to 3 s |

## Known issues / roadmap

**Turn handling and barge-in**
- Flux sometimes splits one utterance into two turns, and Ava answers the first half. Planned: debounce the turn commit.
- Barge-in still uses the old `detect_speech` (3 raw windows, 96 ms) and cancels the turn outright. Planned: pause playback first, cancel only when real words arrive, resume otherwise, using the VAD's speaking state and a minimum duration.
- `is_ava_speaking` follows the reply task, not actual playback. A short answer can finish sending while audio still plays, so the end of an answer can be uninterruptible. Planned: use `audio_source.queued_duration` and `wait_for_playout()`.
- Sometimes the last line of an answer is not heard after a cancel. A log line means "sent to TTS", not "played". Planned: log how each turn ends.
- Two audio tracks can reach the handlers (a double participant), which gives doubled replies. `participant_disconnected` doesn't cancel the old `handle_conversation` task yet.
- STT socket drops after a long idle. Planned: silent-audio fallback in `forward_audio`.
- Idle-user detection ("Are you still there?") is not built yet.

**Booking safety**
- The model can claim a booking it never made. Planned: confirmations generated by code from tool results, a session ledger of real bookings, short spoken booking codes instead of raw Google IDs, and a forced tool call once date, time and name are known.
- Add an eval loop (input → expected tool call) that runs on every change.

**Product**
- Per-user Google Calendar via OAuth, so Ava works as a personal assistant.
- Memory layer for user preferences and facts across sessions. Mem0 is the leading option, loaded at session start and written in the background so it never sits on the reply path.
- Deployment with its own frontend and token server.


## Upcoming updates
 
Two major parts are planned next. Neither is completely built yet  is built yet.
 
### 1. Observability
 
Goal: see exactly what happened in every turn, so problems like a missing last line or a doubled reply can be read off the logs instead of guessed at.
 
Planned:
- **Turn lifecycle log.** For each turn, record how it ended: finished, cancelled by barge-in, or cancelled by a new turn. Include `audio_source.queued_duration` at the moment of cancel to show how much audio was dropped.
- **Per-turn latency.** Keep the T0 to T4 breakdown (EndOfTurn, LLM first token, sentence to TTS, TTS first audio, frame published) as structured records, not only printed lines.
- **Event timeline.** One clock for VAD START/END, Flux EndOfTurn, tool calls, TTS start and playback end.
- **Tool-call trace.** Which tool ran, its arguments, its result, and whether it succeeded, to catch spoken claims with no tool behind them.
- **VAD health.** The existing per-call timing (about 0.4 to 0.5 ms) and a warning when inference falls behind real time.
- **Structured logs and a trace view.** Replace `print` with structured logging, then pick a tracing or dashboard tool.
### 2. Memory
 
Goal: Ava remembers a user's facts and preferences across sessions without slowing the reply.
 
Planned:
- **Mem0 as the first option.** It is a library called from our own code, so it doesn't take over the loop. Alternatives to revisit later: Graphiti or Zep (if facts need to change over time) and Letta (a full agent runtime, so a poor fit here).
- **Off the hot path.** Load a user's memories once at session start, and write new ones in a background task after the turn. No memory search inside the reply budget.
- **Bookings are not memory.** Exact IDs, dates and times stay in Google Calendar plus a session ledger, because LLM-extracted memories can't be trusted for them.
- **Booking lookup by description.** Let a user say "cancel my 5 PM" and have the harness find the ID, so the model never handles raw IDs.
- **Tool description update.** When memory lands, change the cancel and reschedule descriptions from "ID returned by book_slot" to "ID from a tool result or stored booking record".


### 3. Notifications
 
Goal: after a booking or cancellation succeeds, the user gets a confirmation outside the call.
 
Planned:
- **Send only after success.** The notification is triggered by a successful `book_slot`, `reschedule` or `cancel_booking` tool result, never by the model's own words.
- **Channel.** To be decided (email, SMS or push).
- **Content.** Name, date, time and the booking code.
- **Delivery off the reply path.** Send it in a background task, so a slow or failed send never delays or breaks Ava's spoken answer.

## Notes

- Built layer by layer, and each layer is tested alone before it is merged.
- The VAD and turn-handling designs follow the open-source `livekit/agents` code, which I read directly.