# Changes made after "latency down to subsecond" (c64a4f5) — 2026-10-02

On 2026-10-02 the codebase was rolled back to commit `c64a4f5` ("latency down to subsecond").
This file records everything that changed after that commit, so it can be re-applied one piece at a time.

## Where the old state is saved

- Commit `5434dee` ("FDixing vad + END OF tURN DETECTION") is still in git history. HEAD was not moved.
- All uncommitted work from after `5434dee` (including the untracked `agent_core_cerebras/main_loop_groq.py`) is saved in the stash:
  `stash@{0}: pre-revert state 2026-10-02 (5434dee + uncommitted)`
- Get it all back: `git stash pop`
- Get back one file: `git checkout stash@{0} -- <path>`
  (for the untracked Groq file: `git checkout stash@{0}^3 -- agent_core_cerebras/main_loop_groq.py`)

## Summary of changes after c64a4f5

### 1. transport/agent_connector_stream.py  (commit 5434dee, indentation fixed later uncommitted)
- Imported `handle_conversation` and `signal`.
- `conversation_history.clear()` added on `participant_disconnected`.
- NEW block: when the agent starts and a participant is already in the room, it manually starts
  `handle_conversation` for their audio track (so restarting the script works without rejoining).
  - In 5434dee the inner `for track_pub ...` loop was mis-indented (outside the participant loop).
    The uncommitted version fixed the indentation and added a "No participants currently in the room" log.
- Replaced `await asyncio.Event().wait()` with a SIGINT/SIGTERM handler that closes TTS and
  disconnects from the room cleanly.

### 2. agent_core_cerebras/main_loop.py
- 5434dee: added `reasoning_effort="none"` to the Cerebras request.
- Uncommitted: added `prompt_cache_key="ava-system-prompt"` and a commented `# max_retries=0`.
- Commented out the `print("tool_calls at end of stream:", ...)` debug line.

### 3. transport/conversation_handler.py
- LLM import switched back and forth between Cerebras (`agent_core_cerebras.main_loop`),
  Gemini (`agent_core.main_loop_stream`) and Groq (`agent_core_cerebras.main_loop_groq`).
- Removed a TODO comment about the UI button not updating after the script is stopped.
- Uncommitted (applied by Claude Code, 2026-10-02) — "fix 1" and "fix 2":
  - Fix 1: added an `audio_started` flag, set when the first TTS audio chunk arrives. Barge-in
    (`is_ava_speaking`) now requires it, so VAD cannot cancel a turn while the LLM is still thinking.
  - Fix 2: if a new EndOfTurn arrives before Ava produced any audio, the previous turn is cancelled,
    its unanswered user message is removed from `conversation_history`, and both transcripts are
    merged into one message (prints `Merged continuation: ...`).
  - After these, the user reported their speech no longer printed in the terminal. The cause was not
    yet diagnosed when the rollback was made.

### 4. voice_io/stt_stream_final.py
- Added `print("EndofTurn", message.transcript)` when Deepgram sends EndOfTurn.

### 5. agent_core_cerebras/main_loop_groq.py  (new, never committed)
- Groq (`openai/gpt-oss-20b`) version of the streaming agent loop. Saved in the stash.

## Known issues found during analysis (not fixed in c64a4f5 either)
- `is_ava_speaking` is true during the whole LLM wait, not only while Ava speaks, so talking
  during that window counts as a barge-in (more visible with slower LLMs).
- `SPEECH_CONFIRM_CHUNKS = 3` is only ~96ms of speech.
- A cancelled turn leaves its user message (and possibly an unanswered tool call) in history.
- `PersistentTTS._pending_flushes` can go negative after `stop()`, which makes `wait_until_done()`
  return early and switches off barge-in for the following turn.

## Full diff: c64a4f5 → state before rollback (Python files)

```diff
diff --git a/agent_core_cerebras/main_loop.py b/agent_core_cerebras/main_loop.py
index 7d82e0e..57e0d9d 100644
--- a/agent_core_cerebras/main_loop.py
+++ b/agent_core_cerebras/main_loop.py
@@ -28,6 +28,10 @@ async def get_agent_reply_stream(input_msg: str, messages: list):
             messages=messages,
             tools=tools,
             stream=True,
+            reasoning_effort="none",
+            prompt_cache_key="ava-system-prompt",
+            
+            # max_retries=0
         )
 
         tool_calls = {}          # index -> {"id":..., "name":..., "arguments": "..."}
@@ -52,7 +56,7 @@ async def get_agent_reply_stream(input_msg: str, messages: list):
             if delta.content:
                 collected_text += delta.content
                 yield delta.content   # stream text out immediately, chunk by chunk
-        print("tool_calls at end of stream:", tool_calls)
+        # print("tool_calls at end of stream:", tool_calls)
         if tool_calls:
             # Step 1: append the assistant turn that triggered the tool call(s)
             messages.append({
diff --git a/transport/agent_connector_stream.py b/transport/agent_connector_stream.py
index bccad34..fbd10b6 100644
--- a/transport/agent_connector_stream.py
+++ b/transport/agent_connector_stream.py
@@ -5,8 +5,8 @@ from dotenv import load_dotenv
 from livekit import rtc
 from transport.token_server import generate_token, ROOM_NAME
 from transport.livekit_session_stream import register_audio_handlers,setup_audio_output
-from transport.conversation_handler import conversation_history
-
+from transport.conversation_handler import conversation_history, handle_conversation
+import signal
 from voice_io.tts_stream import PersistentTTS
 logging.getLogger("httpx").setLevel(logging.WARNING)
 
@@ -21,10 +21,9 @@ events (participants joining, tracks appearing) → then sit and do nothing itse
 registered handlers drive everything from here on.
 '''
 
-
-
 async def main():
     room = rtc.Room() 
+    shutdown_event = asyncio.Event()
 
     @room.on("participant_connected")
 
@@ -35,6 +34,8 @@ async def main():
     @room.on("participant_disconnected")
     def on_participant_disconnected(participant: rtc.RemoteParticipant):
         logging.info(f"Participant left: {participant.identity}")
+        conversation_history.clear()
+        #TODO: Manage the Memory instead this clear history behavior , plug in a memory system , 
 
 
     token = generate_token(ROOM_NAME, "ava-agent")
@@ -49,10 +50,38 @@ async def main():
     await tts.connect()
 
     audio_source = await setup_audio_output(room)
-
     register_audio_handlers(room, audio_source,tts)
 
-    await asyncio.Event().wait()
+    if not room.remote_participants:
+        logging.info("No participants currently in the room on restart")
+     # --- NEW: handle participants already present before the agent joined ---
+    for identity, participant in room.remote_participants.items():
+        logging.info(f"Found already-connected participant: {identity}")
+        conversation_history.clear()
+
+        for track_pub in participant.track_publications.values():
+            if track_pub.track is not None and track_pub.track.kind == rtc.TrackKind.KIND_AUDIO:
+                logging.info(f"Manually starting conversation handler for existing track from {identity}")
+                asyncio.ensure_future(handle_conversation(track_pub.track, audio_source, tts))
+
+    # await asyncio.Event().wait()
+    # --- NEW: handle Ctrl+C / kill ---
+    loop = asyncio.get_running_loop()
+
+    def handle_shutdown():
+        logging.info("Shutdown signal received, disconnecting agent from room...")
+        shutdown_event.set()
+
+    for sig in (signal.SIGINT, signal.SIGTERM):
+        loop.add_signal_handler(sig, handle_shutdown)
+
+    await shutdown_event.wait()  # blocks here normally, releases on Ctrl+C/kill
+
+    await tts.close()
+    await room.disconnect()
+    logging.info("Ava disconnected cleanly, exiting")
+
+
 
 
 if __name__ == "__main__":
diff --git a/transport/conversation_handler.py b/transport/conversation_handler.py
index 5f0dfd0..b61fcf8 100644
--- a/transport/conversation_handler.py
+++ b/transport/conversation_handler.py
@@ -4,6 +4,8 @@ from voice_io.stt_stream_final import STTConnection
 from voice_io.vad_stream import detect_speech
 # from agent_core.main_loop_stream import get_agent_reply_stream
 from agent_core_cerebras.main_loop import get_agent_reply_stream
+# from agent_core_cerebras.main_loop_groq import get_agent_reply_stream
+
 import re
 import time
 SAMPLE_RATE=16000
@@ -19,6 +21,8 @@ async def process_transcript(transcript:str,audio_source,tts,active_turn):
     async def handle_tts_audio(data:bytes):
         if active_turn["turn_id"]!=my_turn_id:
             return
+        if data:
+            active_turn["audio_started"]=True  # Ava is now audibly speaking, barge-in detection is armed
         if data and "t3" not in active_turn and "t2" in active_turn:  # [LATENCY INSTRUMENTATION - added by claude code]
             active_turn["t3"] = time.perf_counter()  # [LATENCY INSTRUMENTATION - added by claude code]
             print(f"[LATENCY] T3-T2 TTS first audio: {active_turn['t3']-active_turn['t2']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
@@ -75,7 +79,7 @@ async def process_transcript(transcript:str,audio_source,tts,active_turn):
     await speaker_task
 
 async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts):
-    active_turn={"process_task":None,"speaker_task":None,"turn_id":0}
+    active_turn={"process_task":None,"speaker_task":None,"turn_id":0,"audio_started":False}
     # audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)
     while True:
         stt=STTConnection()
@@ -86,7 +90,20 @@ async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts)
             active_turn["t0"]=time.perf_counter()
             for k in ("t1", "t2", "t3", "t4"): active_turn.pop(k, None)  # [LATENCY INSTRUMENTATION - added by claude code]
             # print("DEBUG: handle_turn called with:", transcript)
-            await cancel_active_turn(active_turn, audio_source, tts)
+            prev_task=active_turn["process_task"]
+            if prev_task and not prev_task.done() and not active_turn["audio_started"]:
+                # User kept talking before Ava said anything: treat both parts as one utterance
+                # and drop the unanswered first part from history so the LLM sees a single user message.
+                transcript=f'{active_turn["transcript"]} {transcript}'
+                await cancel_active_turn(active_turn, audio_source, tts)
+                await asyncio.gather(prev_task, return_exceptions=True)
+                del conversation_history[active_turn["history_len"]:]
+                print("Merged continuation:", transcript)
+            else:
+                await cancel_active_turn(active_turn, audio_source, tts)
+            active_turn["transcript"]=transcript
+            active_turn["history_len"]=len(conversation_history)
+            active_turn["audio_started"]=False
             active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,tts,active_turn))
         stt.stt_on_turn_end(handle_turn)
         #! Yes. forward_audio takes the user's mic audio from the LiveKit track and sends it to Deepgram STT.
@@ -102,7 +119,8 @@ async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts)
                     first = False
                 raw=bytes(event.frame.data)
                 await stt.send_audio(raw)
-                is_ava_speaking=active_turn["process_task"] and not active_turn["process_task"].done()
+                # Only count as barge-in once Ava's audio has actually started, not while the LLM is still thinking
+                is_ava_speaking=active_turn["audio_started"] and active_turn["process_task"] and not active_turn["process_task"].done()
                 results = await asyncio.to_thread(detect_speech, raw)
                 for is_speech in results:
                     if is_speech and is_ava_speaking:
@@ -145,8 +163,6 @@ async def cancel_active_turn(active_turn,audio_source,tts):
 # when ever i barge in and terminal pe "speech confirmed" printed " then things work great otherwise not
 #! Also i faced this issue of i didnt spoke for quite sometime , like few minutes and then spoke so Ava didnt responsed witgh some Error , ...... 
 
-# If i close my mqain script , UI pe button should changed not that i stopped the main script and noting changed , 
-# Because when i restart the script it doesnot work then i have to stop and then start conversation again , ..
 
 
 
diff --git a/voice_io/stt_stream_final.py b/voice_io/stt_stream_final.py
index 7e147f4..d7cba4a 100644
--- a/voice_io/stt_stream_final.py
+++ b/voice_io/stt_stream_final.py
@@ -38,7 +38,9 @@ class STTConnection:
         if message.type=="TurnInfo" and message.transcript:
             if message.event=="Update":
                 print("You:", message.transcript)
+                
             elif message.event=="EndOfTurn":
+                print("EndofTurn", message.transcript)
                 if self.on_turn_end:
                     await self.on_turn_end(message.transcript)
 
```
