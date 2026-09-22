import asyncio
import time
import re
from livekit import rtc
from deepgram import AsyncDeepgramClient
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
    client = AsyncDeepgramClient()

    async with client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=str(SAMPLE_RATE),
    ) as connection:

        active_turn = {"process_task": None, "speaker_task": None}
        async def on_message(message):
            if message.type == "TurnInfo" and message.event == "EndOfTurn" and message.transcript:
                user_stopped_at = time.time()
                await cancel_active_turn(active_turn, audio_source, tts)
                active_turn["process_task"] = asyncio.ensure_future(
                    process_transcript(message.transcript, audio_source, user_stopped_at, tts, active_turn)
                )
        connection.on(EventType.MESSAGE, on_message)

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

def register_audio_handlers(room: rtc.Room, audio_source: rtc.AudioSource, tts):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_audio_track(track, audio_source, tts))


























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



