
import asyncio
import wave
import numpy as np
from livekit import rtc

from voice_io.stt import transcribe_file
from agent_core.main_loop import get_agent_reply
from voice_io.tts import speak
from voice_io.tts import generate_speech
import time

SILENCE_THRESHOLD = 300
SILENCE_FRAMES_TO_STOP = 60


SAMPLE_RATE = 24000
NUM_CHANNELS = 1

conversation_history = []   # persists across utterances for this session


#? Explore Coroutene, Future , Task , ensure_future, create_task

async def setup_audio_output(room: rtc.Room) -> rtc.AudioSource:
    '''Creates an outgoing audio track and publishes it into the room, so Ava can be heard.'''
    source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("ava-voice", source)
    await room.local_participant.publish_track(track)
    return source

async def play_audio_bytes(source: rtc.AudioSource, audio_bytes: bytes):
    '''Pushes raw PCM audio bytes into the outgoing track, in small frame-sized chunks.'''
    frame_duration_ms = 20
    samples_per_frame = int(SAMPLE_RATE * frame_duration_ms / 1000)
    bytes_per_frame = samples_per_frame * 2  # 2 bytes per int16 sample

    for i in range(0, len(audio_bytes), bytes_per_frame):
        chunk = audio_bytes[i:i + bytes_per_frame]
        if len(chunk) < bytes_per_frame:
            chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))  # pad last frame with silence
        frame = rtc.AudioFrame(
            data=chunk,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            samples_per_channel=samples_per_frame,
        )
        await source.capture_frame(frame)


async def handle_audio_track(track: rtc.Track,audio_source: rtc.AudioSource):
    audio_stream = rtc.AudioStream(track)
    buffer = []
    silence_count = 0
    speaking = False

    async for event in audio_stream:
        frame = event.frame
        samples = np.frombuffer(frame.data, dtype=np.int16)
        amplitude = np.abs(samples).mean()

        if amplitude > SILENCE_THRESHOLD:
            speaking = True
            silence_count = 0
            buffer.append(frame)
        elif speaking:
            silence_count += 1
            buffer.append(frame)
            if silence_count > SILENCE_FRAMES_TO_STOP:
                user_stopped_at = time.time()
                await process_utterance(buffer, frame.sample_rate, frame.num_channels,audio_source,user_stopped_at)
                buffer = []
                speaking = False
                silence_count = 0

async def process_utterance(frames, sample_rate, num_channels,audio_source,user_stopped_at):
    try:
        filename = "room_input.wav"
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for frame in frames:
                wf.writeframes(bytes(frame.data))

        stt_start = time.time()
        transcript = transcribe_file(filename)
        stt_time = time.time() - stt_start
        print("User said:", transcript)
        if not transcript.strip():
            return
        
        llm_start = time.time()
        reply_text = get_agent_reply(transcript, conversation_history)
        llm_time = time.time() - llm_start
        print("Ava:", reply_text)

        # speak(reply_text)   # currently plays on YOUR local speaker, not the room yet — next step fixes that
        # await asyncio.to_thread(speak, reply_text)
        tts_start = time.time()
        audio_bytes = generate_speech(reply_text)
        tts_time = time.time() - tts_start

        total_latency = time.time() - user_stopped_at
        print(f"STT: {stt_time:.2f}s | LLM: {llm_time:.2f}s | TTS: {tts_time:.2f}s | Total: {total_latency:.2f}s")
        await play_audio_bytes(audio_source, audio_bytes)
    except Exception as e:
        print(f"Error handling utterance :{e}")


# Whats this function inside function , ?? 
def register_audio_handlers(room: rtc.Room,audio_source: rtc.AudioSource):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_audio_track(track,audio_source))


#! Why ensure_Future, 
'''
handle_audio_track is async def, so now we have options like await, create_task/ensure_future

1.You can't await inside a plain def.( But even if it was a async funtion we would await )
2. What ensure_future does: it takes that waiting job and hands it to the event loop, saying "run this in 
the background, when you get a chance." It returns immediately, so the handler finishes right away.

# ? Small notes
1.asyncio.create_task(...) is the modern, preferred way to do the same thing here. ensure_future works, but create_task is clearer for a coroutine.

In one line: ensure_future starts the async job in the background from a non-async handler, without blocking the event loop.
'''

#! Can we use create_task under a synchronous code, 

'''
Yes, but only if an event loop is already running

create_task doesn't care whether the function you call it from is def or async def. It only cares that an 
event loop is running in that thread right now.

Two cases
1. Sync function called by the event loop: works.
Your on_track_subscribed is a plain def, but LiveKit's event loop is what calls it. So a loop is running at 
that moment, and create_task works fine. This is why your handler can use it.

2. Sync function called from plain top-level code with no loop: fails.
If you call create_task in a normal script where no loop has started, Python raises RuntimeError: no running
event loop. The task has nowhere to be scheduled.

#? Both the above statements are true for , create_task and ensure_future as well , with the difference that
#? ensure_future may not raise the erorr , it may crash silently 

'''



'''

The handler function itself. Notice it's defined inside register_audio_handlers — this is a nested function
(a function defined inside another function). Why nested, specifically? Because on_track_subscribed needs 
access to audio_source and tts — the parameters of the outer function. By defining it inside, it can just 
use those variables directly (this is called a closure — the inner function "closes over" / remembers the 
outer function's variables, even after the outer function itself has already finished running). If 
on_track_subscribed were defined outside, you'd have no clean way to hand it audio_source and tts, 
since LiveKit itself is the one calling this function later (via the event system) — you don't control 
what arguments get passed to it; LiveKit decides that (track, publication, participant).

'''


 

'''
#! Learning
Right now, speak(reply_text) runs mpv on the machine your agent_connect.py script is running on — which is
your laptop. Since your earphones are plugged into that same laptop, of course you hear it — you're both 
the person testing and the machine running the worker.

The actual problem shows up once these are two different machines/people: imagine your interviewer opens 
your deployed frontend on their laptop. Your worker (running Ava) is on a server somewhere, not their 
laptop. If speak() still just plays via mpv on the worker's machine, the interviewer's browser gets 
nothing — the audio plays on your server, which nobody is sitting in front of.

For them to hear anything, the audio needs to travel over the network, through the room, into their 
browser — same as how their voice reaches your worker as a room audio track right now. That's what 
"publish into the room" means: instead of mpv playing sound locally, we take the TTS audio and inject 
it as an outgoing audio track in the LiveKit room, which LiveKit then streams to every other participant's 
browser — including someone on a completely different device.

'''

