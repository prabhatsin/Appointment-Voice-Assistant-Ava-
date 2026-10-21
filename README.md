# Ava: Voice Scheduling Assistant

Ava is a voice-based scheduling assistant. You talk to her in the browser, and she checks availability, books, reschedules and cancels appointments on Google Calendar, in natural conversation.

The STT → LLM → TTS pipeline is hand-built, with no agent framework. LiveKit is used only for rooms and WebRTC transport.

<!-- Demo video goes here -->

## Features

- Check available appointment slots for a date
- Book, reschedule and cancel appointments (Google Calendar)
- Stream her answer sentence by sentence, so speech starts while the LLM is still generating
- Be interrupted mid-sentence (barge-in)
- Reconnect automatically when the speech-to-text socket drops
- Answer general questions and chat, not only scheduling

## How it works

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
1. Mic audio arrives from the LiveKit room and is sent to speech-to-text and the VAD.
2. Deepgram Flux detects that the user has finished speaking and returns the transcript.
3. Ava starts a reply, cancelling any earlier reply still running.
4. The LLM streams its answer. If it calls a calendar tool, the tool runs and the result goes back to the model.
5. Each finished sentence is sent to text-to-speech immediately and played in the browser.

For design decisions, the VAD module and project structure, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

| Layer | Choice |
|---|---|
| Speech-to-text | Deepgram Flux (`flux-general-en`), streaming |
| LLM | Cerebras `qwen-3.8-27b`, streaming with tool calls |
| Text-to-speech | Deepgram Aura (`aura-2-hera-en`), streaming |
| Transport | LiveKit (rooms, WebRTC) |
| Voice activity detection | Silero VAD, runs locally |
| Calendar | Google Calendar API |
| Language | Python 3.12, asyncio |

## Installation

**Requirements:** Python 3.12, Node.js, a LiveKit Cloud project, Deepgram and Cerebras API keys, and a Google Cloud project with the Calendar API enabled.

```bash
git clone https://github.com/prabhatsin/Appointment-Voice-Assistant-Ava-.git
cd Appointment-Voice-Assistant-Ava-
python3 -m venv myenv
source myenv/bin/activate        # Windows: myenv\Scripts\activate
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

**Google Calendar (one-time setup):**
1. In Google Cloud, enable the Google Calendar API and create an OAuth client ID of type **Desktop app**.
2. Download it as `secrets/credentials.json`.
3. Run the auth script, open the URL it prints, and sign in with the Google account whose calendar Ava should use:
   ```bash
   python3 -m calendar_service.calendar_auth
   ```
   This saves `secrets/token.json`. Ava uses it from then on and refreshes it automatically.

Keep the `secrets/` folder out of git.

Then create a `.env` file in the project root (see [Configuration](#configuration)).

## Configuration

Set these in `.env`:

| Variable | Purpose |
|---|---|
| `LIVEKIT_URL` | LiveKit Cloud WebSocket URL |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit credentials |
| `DEEPGRAM_API_KEY` | Speech-to-text and text-to-speech |
| `CEREBRAS_API_KEY` | LLM |

## Usage

Run each in its own terminal, from the project root:

1. Start the token server:
   ```bash
   uvicorn transport.token_server:app --reload
   ```
2. Start the browser UI:
   ```bash
   cd frontend
   npm run dev
   ```
3. Start Ava:
   ```bash
   python3 -m transport.agent_connector_stream
   ```
4. Open the browser UI, join the room `ava-booking-room`, allow the mic, and start talking.

Things to try:

```
"What's free tomorrow afternoon?"
"Book me at 5 PM on Friday, my name is Prabhat."
"Move my Friday appointment to Monday at 10."
"Actually, cancel it."
```

## Latency

| Stage | Time |
|---|---|
| LLM first token | 0.35 to 0.55 s |
| End to end, no tool call | about 0.6 to 0.9 s |
| End to end, with a calendar tool call | about 1.4 to 3 s |

## Known limits

- If you pause mid-sentence, Ava may answer the first half before you finish.
- Interrupting near the end of an answer may not work, and the last line can be cut after an interruption.
- The speech-to-text connection can drop after a long idle period.
- Ava can occasionally say she booked something without actually booking it. Check your calendar for important bookings.
- One shared Google Calendar for everyone; no per-user accounts yet.
- Joining the room from two tabs can cause doubled replies.

## Future work

- Observability: per-turn logs, latency records and tool-call traces
- Memory: remember user preferences across sessions, without slowing replies
- Notifications: a confirmation after every successful booking, reschedule or cancellation
- Booking safety: confirmations generated from real tool results, plus an eval loop
- Per-user Google Calendar through OAuth

## Development

```bash
python3 -m voice_io.test_vad_logic      # VAD state-machine test, no mic needed
python3 -m voice_io.vad_listener        # live VAD/STT listener; stop Ava first
```

## License

MIT