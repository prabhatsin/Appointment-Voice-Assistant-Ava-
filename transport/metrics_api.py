"""Read-only endpoints over the per-turn latency records the agent writes (see observability/metrics.py)."""
import json
import sqlite3
from fastapi import APIRouter, HTTPException
from observability import metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = metrics.connect()
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


# Plain `def` endpoints: FastAPI runs them in its threadpool, so SQLite reads don't block the event loop
@router.get("/calls")
def list_calls():
    return _query("""
        SELECT call_id, room, MIN(ts) AS started_at, COUNT(*) AS turns, SUM(interrupted) AS interrupted_turns,
               ROUND(AVG(total_ms), 1)    AS avg_total_ms,
               ROUND(AVG(stt_ms), 1)      AS avg_stt_ms,
               ROUND(AVG(llm_ttft_ms), 1) AS avg_llm_ttft_ms,
               ROUND(AVG(tts_ttfa_ms), 1) AS avg_tts_ttfa_ms,
               ROUND(AVG(tool_ms), 1)     AS avg_tool_ms
        FROM turns GROUP BY call_id ORDER BY started_at DESC
    """)


@router.get("/calls/{call_id}")
def get_call(call_id: str):
    turns = _query("SELECT * FROM turns WHERE call_id = ? ORDER BY turn_index", (call_id,))
    if not turns:
        raise HTTPException(status_code=404, detail=f"No turns recorded for call {call_id}")
    for turn in turns:
        turn["interrupted"] = bool(turn["interrupted"])
        turn["tools"] = json.loads(turn["tools"] or "[]")
    return {"call_id": call_id, "turns": turns}
