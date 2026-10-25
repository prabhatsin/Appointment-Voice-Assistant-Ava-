"""Per-turn latency metrics for Ava.

While a turn runs, the hooks only store time.perf_counter() marks in memory. When the turn's reply task ends,
one row is handed to a background writer thread that inserts it into SQLite, so no hook does I/O on the event
loop. Every public function catches and logs its own errors: metrics must never break a call.
"""
import atexit
import contextvars
import functools
import json
import logging
import os
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone

DB_PATH = os.getenv("METRICS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics.db"))
SPEECH_END_MAX_AGE = 5.0   # a VAD speech end older than this at EndOfTurn belongs to an earlier utterance

log = logging.getLogger("metrics")

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT NOT NULL,
    room        TEXT,
    turn_index  INTEGER NOT NULL,
    ts          TEXT NOT NULL,       -- UTC time of the STT final transcript
    stt_ms      REAL,                -- end of user speech -> STT final transcript
    llm_ttft_ms REAL,                -- LLM request sent -> first text token
    tts_ttfa_ms REAL,                -- first sentence sent to TTS -> first audio chunk
    tool_ms     REAL,                -- sum of all tool calls in the turn
    total_ms    REAL,                -- end of user speech -> first audio chunk
    interrupted INTEGER NOT NULL,
    tools       TEXT                 -- JSON [{name, start_ms, end_ms}], relative to end of user speech
);
CREATE INDEX IF NOT EXISTS turns_call_id ON turns(call_id);
"""
INSERT = """INSERT INTO turns (call_id, room, turn_index, ts, stt_ms, llm_ttft_ms, tts_ttfa_ms, tool_ms,
            total_ms, interrupted, tools) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.exception("metrics: %s failed", fn.__name__)
            return None
    return wrapper


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")   # the agent writes while the API process reads
    conn.executescript(SCHEMA)
    return conn


class Call:
    def __init__(self, call_id: str, room: str | None):
        self.call_id = call_id
        self.room = room
        self.turns = 0
        self.turn = None              # latest turn, so a VAD end arriving after EndOfTurn can still attach to it
        self.last_speech_end = None   # perf_counter time the user last stopped speaking (VAD)


class Turn:
    def __init__(self, call: Call, index: int):
        self.call = call
        self.index = index
        self.ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.transcript_t = time.perf_counter()   # STT final transcript (Flux EndOfTurn)
        self.speech_end = None                   # end of user speech (VAD), if one was seen
        self.marks = {}                          # llm_request, llm_first_token, tts_request, tts_first_audio
        self.tools = []                          # [name, start, end] per tool call


# Holds the current turn's single Turn object. It is set once per turn, before the reply task is created, so
# the reply task (and threads started with asyncio.to_thread) inherit it and all mutate that same object.
_turn: contextvars.ContextVar[Turn | None] = contextvars.ContextVar("metrics_turn", default=None)


def _speech_end_fits(t: float, turn: Turn) -> bool:
    return 0 <= turn.transcript_t - t <= SPEECH_END_MAX_AGE


@_safe
def start_call(call_id: str, room: str | None = None) -> Call:
    return Call(call_id, room)


@_safe
def speech_ended(call: Call | None, t: float):
    """The VAD saw the user stop speaking at perf_counter time t (already backdated by the silence it waited for)."""
    if call is None:
        return
    call.last_speech_end = t
    turn = call.turn
    # Flux can end the turn before the VAD's silence timer runs out: attach the late speech end to that turn
    if turn and _speech_end_fits(t, turn) and (turn.speech_end is None or t > turn.speech_end):
        turn.speech_end = t


@_safe
def start_turn(call: Call | None) -> Turn | None:
    """STT final transcript arrived: create this turn's record and make it current for tasks created after this."""
    if call is None:
        return None
    prev = call.turn
    turn = Turn(call, call.turns)
    call.turns += 1
    t = call.last_speech_end
    if t is not None and _speech_end_fits(t, turn) and (prev is None or t > prev.transcript_t):
        turn.speech_end = t
    call.turn = turn
    _turn.set(turn)
    return turn


def current() -> Turn | None:
    return _turn.get()


@_safe
def mark(name: str, turn: Turn | None = None):
    """Record the first time `name` happens in the turn (the current one unless given). In memory only."""
    turn = turn or _turn.get()
    if turn is not None:
        turn.marks.setdefault(name, time.perf_counter())


@_safe
def llm_request():
    """LLM request sent. A turn with tool calls makes several; TTFT is measured from the one that yields the first text."""
    turn = _turn.get()
    if turn is not None and "llm_first_token" not in turn.marks:
        turn.marks["llm_request"] = time.perf_counter()


@_safe
def tool_start(name: str):
    turn = _turn.get()
    if turn is None:
        return None
    entry = [name, time.perf_counter(), None]
    turn.tools.append(entry)
    return entry


@_safe
def tool_end(entry):
    if entry is not None:
        entry[2] = time.perf_counter()


@_safe
def track_reply(turn: Turn | None, task):
    """Save the turn when its reply task ends; a cancelled reply means the turn was interrupted."""
    if turn is not None:
        task.add_done_callback(functools.partial(_finish, turn))


@_safe
def _finish(turn: Turn, task):
    if "llm_request" not in turn.marks:   # empty transcript: no reply was attempted
        return
    _enqueue(_row(turn, interrupted=task.cancelled()))


def _ms(start, end):
    return None if start is None or end is None else round((end - start) * 1000, 1)


def _row(turn: Turn, interrupted: bool) -> tuple:
    m = turn.marks
    origin = turn.speech_end if turn.speech_end is not None else turn.transcript_t
    tools = [{"name": n, "start_ms": _ms(origin, s), "end_ms": _ms(origin, e)} for n, s, e in turn.tools]
    tool_times = [_ms(s, e) for _, s, e in turn.tools if e is not None]
    return (
        turn.call.call_id, turn.call.room, turn.index, turn.ts,
        _ms(turn.speech_end, turn.transcript_t),
        _ms(m.get("llm_request"), m.get("llm_first_token")),
        _ms(m.get("tts_request"), m.get("tts_first_audio")),
        round(sum(tool_times), 1) if tool_times else None,
        _ms(origin, m.get("tts_first_audio")),
        int(interrupted), json.dumps(tools),
    )


# Background writer: the event loop only puts rows on the queue; one thread does all SQLite writes.
_queue: queue.SimpleQueue = queue.SimpleQueue()
_writer: threading.Thread | None = None


def _enqueue(row: tuple):
    global _writer
    if _writer is None:
        _writer = threading.Thread(target=_write_loop, name="metrics-writer", daemon=True)
        _writer.start()
        atexit.register(_flush)
    _queue.put(row)


def _write_loop():
    conn = None
    while (row := _queue.get()) is not None:
        try:
            conn = conn or connect()
            conn.execute(INSERT, row)
            conn.commit()
        except Exception:
            log.exception("metrics: failed to save turn %s of call %s", row[2], row[0])
            if conn:
                conn.close()
            conn = None   # reconnect on the next row
    if conn:
        conn.close()


def _flush():
    """At exit, give the writer a moment to save turns still queued."""
    _queue.put(None)
    _writer.join(timeout=2)
