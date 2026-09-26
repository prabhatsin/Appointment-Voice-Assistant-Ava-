import asyncio
import time
import re
from livekit import rtc
from voice_io.stt_stream_final import stt_connect, stt_on_turn_end, send_audio, stt_register_listener, stt_close
from deepgram.core.events import EventType

from agent_core.main_loop_stream import get_agent_reply_stream
import torch
import numpy as np
from silero_vad import load_silero_vad

vad_model = load_silero_vad()
VAD_CHUNK_SAMPLES = 512  # required chunk size for 16kHz
VAD_THRESHOLD = 0.5
SPEECH_CONFIRM_CHUNKS = 3  # ~96ms of sustained speech before triggering interrupt

SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
TTS_NUM_CHANNELS = 1

conversation_history = []

async def setup_audio_output(room: rtc.Room) -> rtc.AudioSource:
    source = rtc.AudioSource(TTS_SAMPLE_RATE, TTS_NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("ava-voice", source)
    await room.local_participant.publish_track(track)
    return source


async def process_transcript(transcript: str, audio_source: rtc.AudioSource, user_stopped_at: float, tts, active_turn: dict):
    try:
        if not transcript.strip():
            return
        print("User said:", transcript)

        sentence_queue = asyncio.Queue()
        first_audio_time = None
        first_sentence_ready_time = None

        async def on_chunk(data: bytes):
            nonlocal first_audio_time
            if first_audio_time is None:
                first_audio_time = time.time() - user_stopped_at
                print(f"TOTAL (stop -> first audio): {first_audio_time:.2f}s")
            samples_per_channel = len(data) // 2
            frame = rtc.AudioFrame(
                data=data, sample_rate=TTS_SAMPLE_RATE,
                num_channels=TTS_NUM_CHANNELS, samples_per_channel=samples_per_channel,
            )
            await audio_source.capture_frame(frame)

        tts.set_chunk_handler(on_chunk)

        async def speak_sentences():
            while True:
                sentence = await sentence_queue.get()
                if sentence is None:
                    break
                await tts.send(sentence)
            await tts.wait_until_done()

        speaker_task = asyncio.create_task(speak_sentences())
        active_turn["speaker_task"] = speaker_task

        buffer = ""
        full_reply = ""
        llm_start = time.time()
        async for chunk in get_agent_reply_stream(transcript, conversation_history):
            buffer += chunk
            full_reply += chunk
            while True:
                match = re.search(r'[.!?]\s', buffer)
                if not match:
                    break
                sentence = buffer[:match.end()].strip()
                buffer = buffer[match.end():]
                if sentence:
                    if first_sentence_ready_time is None:
                        first_sentence_ready_time = time.time() - llm_start
                        print(f"  -> LLM time to first sentence: {first_sentence_ready_time:.2f}s")
                    await sentence_queue.put(sentence)

        if buffer.strip():
            await sentence_queue.put(buffer.strip())

        await sentence_queue.put(None)
        print("Ava:", full_reply)
        await speaker_task

    except Exception as e:
        print(f"Error handling utterance: {e}")


async def handle_audio_track(track: rtc.Track, audio_source: rtc.AudioSource, tts):
        await stt_connect()

        active_turn = {"process_task": None, "speaker_task": None}

        async def on_turn_end(transcript):
            user_stopped_at = time.time()
            await cancel_active_turn(active_turn, audio_source, tts)
            active_turn["process_task"] = asyncio.ensure_future(
                process_transcript(transcript, audio_source, user_stopped_at, tts, active_turn)
            )

        stt_on_turn_end(on_turn_end)

        audio_stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1)

        async def forward_audio():
            vad_buffer = b""
            speech_streak = 0

            async for event in audio_stream:
                try:
                    raw = bytes(event.frame.data)
                    await connection.send_media(raw)

                    # --- VAD barge-in check ---
                    vad_buffer += raw
                    chunk_bytes = VAD_CHUNK_SAMPLES * 2  # 16-bit samples
                    while len(vad_buffer) >= chunk_bytes:
                        chunk = vad_buffer[:chunk_bytes]
                        vad_buffer = vad_buffer[chunk_bytes:]

                        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                        prob = vad_model(torch.from_numpy(samples), SAMPLE_RATE).item()

                        is_ava_speaking = (
                            active_turn["process_task"] and not active_turn["process_task"].done()
                        )

                        if prob > VAD_THRESHOLD and is_ava_speaking: 
                            speech_streak += 1
                            if speech_streak >= SPEECH_CONFIRM_CHUNKS:
                               
                               await cancel_active_turn(active_turn,audio_source,tts)
                               speech_streak = 0
                        else:
                            speech_streak = 0
                except Exception as e:
                    print(f"forward_audio error: {e}")
                    raise

        await asyncio.gather(forward_audio(), connection.start_listening())

async def cancel_active_turn(active_turn: dict, audio_source: rtc.AudioSource, tts):
    if active_turn["process_task"] and not active_turn["process_task"].done():
        active_turn["process_task"].cancel()
    if active_turn["speaker_task"] and not active_turn["speaker_task"].done():
        active_turn["speaker_task"].cancel()
    audio_source.clear_queue()
    await tts.stop()






# track: The actual live media stream (audio or video). This is what you read audio from.
'''
Why track and publication are separate

A publication exists as soon as the guest publishes, even before you receive anything. The track only exists 
after you subscribe. So LiveKit keeps them apart: the publication is "this exists and is available", and 
the track is "the live data is now flowing to you."

'''
# publication	The listing or description of that track: its name, kind, source (mic or camera), muted state.
#participant	The person or agent who published it: identity, name, metadata.
'''
Why participant matters
A room can hold many people. The participant tells you whose audio this is, so you can, for example,
respond only to the guest and ignore other tracks.
'''
def register_audio_handlers(room: rtc.Room, audio_source: rtc.AudioSource, tts):
    # "Track_subscribed :LiveKit fires this specifically when a new audio or video track becomes available to you 
    # (in your case: when the guest's browser starts sending their mic audio, and your agent — the "subscriber" — gets access to it)."
    @room.on("track_subscribed") # The below function gets fired when an "track_sbuscribed" event happens 
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        #A safety check — track_subscribed could theoretically fire for video tracks too
        if track.kind == rtc.TrackKind.KIND_AUDIO:

            asyncio.ensure_future(handle_audio_track(track, audio_source, tts))
            # Why ensure_future and what is it ??
            #! Ans: look at the livikit_session.py script 


#? Why is  on_track_susbscribed defined inside the register_audio_handlers function , ?? 


# step1 : What is a callback ?? 
'''
A callback is a function you hand to someone else so they can call it later, when something happens.

-> You don't call it yourself.
-> You pass it, and the other side decides when to run it.

#! Your "on_track_subscribed" is a callback: you gave it to room, and room calls it when the event fires. "Event handler", "listener", and "callback" are mostly the same thing seen from different angles.

'''
# step2 : Whats a closure , in python , 
# Ans: Closure is a workaround forn a problem 
'''
Closure = a nested function that actually uses the outer function's variables.
A closure needs two things:
1.A function defined inside another function (a nested function).
2.The inner function uses a variable that belongs to the outer function.
If either is missing, it's not a closure.

# In Summary : the closure is the inner function together with the variables it remembers bundled as one package.

'''

# why need a closure : ??

'''
#! The problem closure solves is ...
A closure lets a function carry extra data with it when someone else will call it later.
When you hand a function to another party (like room), that party decides when to call it and what arguments
to pass. You can't change that. LiveKit only passes track, publication, and participant, but your handler 
also needs audio_source and tts. A closure solves this: the function remembers those from where it was 
defined, so nothing extra has to be passed in.

'''

'''
# LiveKit itself decides what arguments get passed to your event handler when it calls it.
# Those three parameters — track, publication, participant — are fixed by LiveKit's event system.
# When LiveKit calls your handler, it calls it exactly like on_track_subscribed(some_track, some_publication, 
 some_participant) — you have zero control over that call; LiveKit's internals do it for you, using 
 whatever arguments it decides to pass.
# LiveKit doesn't know about your audio_source/tts — it will only ever call this function with the three arguments it provides.

# If you added extra required parameters, calling it would crash with a "missing argument" error, since LiveKit isn't passing them.
# This is exactly the problem a closure (nested function) solves. Because on_track_subscribed is defined 
  inside register_audio_handlers, it can still see and use audio_source and tts — not as parameters, but 
  as variables it "remembers" from the outer function's scope, even though nobody explicitly passes them 
  in when LiveKit calls it later.

#? A closure lets a function carry extra data with it when someone else will call it later.

'''























#! "when a track becomes available, fire an event called exactly 'track_subscribed'" —Use this exact string ,



'''
Notice: this function itself is a regular def, not async def, and you call it without await. Why? Because 
all it does is register another event handler — same exact pattern as on_participant_connected from before. 
It doesn't do any real work itself; it just tells room: "whenever a track gets subscribed (meaning: whenever
 your mic audio arrives, since the guest is publishing their mic track), call on_track_subscribed."

The real work happens later, inside on_track_subscribed, when that event actually fires — and specifically
in this line:

This is worth pausing on: handle_audio_track is async def, but here it's called without await.

#!Instead, it's wrapped in asyncio.ensure_future(...). 
This means: "start running this coroutine as an independent, separate background task, don't wait for 
it to finish, just let it run alongside everything else."

This is different from await (which pauses the current function until the awaited thing finishes)
#!  ensure_future says "kick this off in parallel, and I'm moving on immediately."

'''



