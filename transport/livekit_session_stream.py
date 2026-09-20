import asyncio
import time
from livekit import rtc
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

from agent_core.main_loop import get_agent_reply
from voice_io.tts import generate_speech

SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
TTS_NUM_CHANNELS = 1

conversation_history = []

async def setup_audio_output(room: rtc.Room) -> rtc.AudioSource:
    source = rtc.AudioSource(TTS_SAMPLE_RATE, TTS_NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("ava-voice", source)
    await room.local_participant.publish_track(track)
    return source

async def play_audio_bytes(source: rtc.AudioSource, audio_bytes: bytes):
    frame_duration_ms = 20
    samples_per_frame = int(TTS_SAMPLE_RATE * frame_duration_ms / 1000)
    bytes_per_frame = samples_per_frame * 2

    for i in range(0, len(audio_bytes), bytes_per_frame):
        chunk = audio_bytes[i:i + bytes_per_frame]
        if len(chunk) < bytes_per_frame:
            chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
        frame = rtc.AudioFrame(
            data=chunk, sample_rate=TTS_SAMPLE_RATE,
            num_channels=TTS_NUM_CHANNELS, samples_per_channel=samples_per_frame,
        )
        await source.capture_frame(frame)

async def process_transcript(transcript: str, audio_source: rtc.AudioSource, user_stopped_at: float):
    try:
        if not transcript.strip():
            return
        print("User said:", transcript)

        llm_start = time.time()
        reply_text = get_agent_reply(transcript, conversation_history)
        llm_time = time.time() - llm_start
        print("Ava:", reply_text)

        tts_start = time.time()
        audio_bytes = generate_speech(reply_text)
        tts_time = time.time() - tts_start

        total_latency = time.time() - user_stopped_at
        print(f"LLM: {llm_time:.2f}s | TTS: {tts_time:.2f}s | Total (post-STT): {total_latency:.2f}s")

        await play_audio_bytes(audio_source, audio_bytes)
    except Exception as e:
        print(f"Error handling utterance: {e}")

async def handle_audio_track(track: rtc.Track, audio_source: rtc.AudioSource):
    client = AsyncDeepgramClient()

    async with client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=str(SAMPLE_RATE),
    ) as connection:

        async def on_message(message):
            if message.type == "TurnInfo" and message.event == "EndOfTurn" and message.transcript:
                user_stopped_at = time.time()
                asyncio.ensure_future(process_transcript(message.transcript, audio_source, user_stopped_at))

        connection.on(EventType.MESSAGE, on_message)

        audio_stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1)

        async def forward_audio():
            async for event in audio_stream:
                await connection.send_media(bytes(event.frame.data))

        await asyncio.gather(forward_audio(), connection.start_listening())

def register_audio_handlers(room: rtc.Room, audio_source: rtc.AudioSource):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_audio_track(track, audio_source))