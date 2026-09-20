# Ava — Voice Scheduling Assistant (Frontend)

Single-page React + Vite frontend that connects to a LiveKit room via `livekit-client`
and talks to the Ava voice agent in real time.

## Setup

```bash
npm install
```

By default the app fetches a token from `http://localhost:8000/token?identity=<name>`.
To point at a different token server, copy `.env.example` to `.env.local` and set
`VITE_TOKEN_ENDPOINT`.

## Run

```bash
npm run dev
```

Open the printed local URL, make sure the Python token server and the LiveKit agent
worker are both running, then click **Start Conversation** and allow microphone access.

## Build

```bash
npm run build
npm run preview
```
