### **Voice AI Observability --- Tools / Libraries**

  -----------------------------------------------------------------------
  **Tool / Library** **One-line purpose**
  ------------------ ----------------------------------------------------
  **OpenTelemetry    Standard framework for collecting **traces, metrics,
  (OTel)**           and telemetry** across the entire voice pipeline.

  **Prometheus**     Collects and stores **time-series metrics** such as
                     latency, active sessions, errors, packet loss, etc.

  **Grafana**        Creates **dashboards and visualizations** from
                     metrics such as Prometheus data.

  **Jaeger**         Distributed tracing backend for visualizing
                     **end-to-end voice turns and service latency**.

  **Grafana Tempo**  Distributed tracing backend designed to store and
                     query **OpenTelemetry traces**.

  **Loki**           Log aggregation system for collecting and querying
                     **structured application logs**.

  **ELK Stack**      Elasticsearch + Logstash + Kibana for **centralized
                     log collection, search, and visualization**.

  **Sentry**         Tracks **application errors, exceptions, crashes,
                     and performance issues**.

  **Langfuse**       LLM/agent observability for **prompts, generations,
                     tokens, tool calls, latency, and costs**.

  **LiveKit Agent    Voice-specific observability providing **STT/LLM/TTS
  Observability**    latency, transcripts, traces, recordings, turns, and
                     tool metrics**.

  **Pipecat**        Voice-agent pipeline framework that can be
                     instrumented for **STT → LLM → TTS pipeline
                     telemetry**.

  **Vapi             Voice-agent platform observability covering
  Observability**    **transcriber, model, voice, endpointing, tools,
                     transport, latency, and calls**.

  **Python logging** Built-in Python logging system for creating
                     **structured application/event logs**.
  -----------------------------------------------------------------------

### 

### 

### 

### **Core voice-specific metrics/events to track**

  -----------------------------------------------------------------------
  **Metric / Event**   **Purpose**
  -------------------- --------------------------------------------------
  **TTFT**             Time to first LLM token.

  **TTFB / TTS TTFB**  Time until the first synthesized audio is
                       available.

  **E2E latency**      Time from user finishing speech to Ava producing
                       first audio.

  **STT latency**      Time taken to produce transcription.

  **VAD latency**      Time taken to detect speech start/end.

  **EOU / End-of-turn  Time required to determine that the user has
  delay**              finished speaking.

  **Barge-in latency** How quickly Ava reacts when the user interrupts.

  **Packet loss**      Network/audio packets lost during realtime
                       communication.

  **Jitter**           Variation in packet arrival timing.

  **RTT**              Network round-trip time.

  **Audio frames       Number of audio frames lost/dropped by the
  dropped**            pipeline.

  **Buffer depth**     Amount of audio currently buffered.

  **Tool latency**     Time taken by agent tool calls.

  **Token usage**      LLM input/output token consumption.

  **Cost per           Tracks operational AI cost.
  turn/session**       

  **Session ID / Turn  Correlates all events belonging to a conversation
  ID**                 and individual turn.
  -----------------------------------------------------------------------

### 

### 

### 

### 

### 

### 

### **Recommended stack for your Ava**

OpenTelemetry

↓

┌────┼─────────┐

↓ ↓ ↓

Traces Metrics Logs

↓ ↓ ↓

Jaeger Prometheus Loki

↓

Grafana

Agent / LLM layer

↓

Langfuse

Errors

↓

Sentry

**Voice-specific reference systems to study:** **LiveKit Agents,
Pipecat, Vapi**.
