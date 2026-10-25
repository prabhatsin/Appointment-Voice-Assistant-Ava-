

'''
Voice AI Observability — Tools / Libraries
Tool / Library	One-line purpose
OpenTelemetry (OTel)	Standard framework for collecting traces, metrics, and telemetry across the entire voice pipeline.
Prometheus	Collects and stores time-series metrics such as latency, active sessions, errors, packet loss, etc.
Grafana	Creates dashboards and visualizations from metrics such as Prometheus data.
Jaeger	Distributed tracing backend for visualizing end-to-end voice turns and service latency.
Grafana Tempo	Distributed tracing backend designed to store and query OpenTelemetry traces.
Loki	Log aggregation system for collecting and querying structured application logs.
ELK Stack	Elasticsearch + Logstash + Kibana for centralized log collection, search, and visualization.
Sentry	Tracks application errors, exceptions, crashes, and performance issues.
Langfuse	LLM/agent observability for prompts, generations, tokens, tool calls, latency, and costs.
LiveKit Agent Observability	Voice-specific observability providing STT/LLM/TTS latency, transcripts, traces, recordings, turns, and tool metrics.
Pipecat	Voice-agent pipeline framework that can be instrumented for STT → LLM → TTS pipeline telemetry.
Vapi Observability	Voice-agent platform observability covering transcriber, model, voice, endpointing, tools, transport, latency, and calls.
Python logging	Built-in Python logging system for creating structured application/event logs.

'''

