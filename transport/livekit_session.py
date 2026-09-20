
import asyncio
import wave
import numpy as np
from livekit import rtc

from voice_io.stt import transcribe_file
from agent_core.main_loop import get_agent_reply
from voice_io.tts import speak
from voice_io.tts import generate_speech
SILENCE_THRESHOLD = 300
SILENCE_FRAMES_TO_STOP = 60


SAMPLE_RATE = 24000
NUM_CHANNELS = 1

conversation_history = []   # persists across utterances for this session


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
                await process_utterance(buffer, frame.sample_rate, frame.num_channels,audio_source)
                buffer = []
                speaking = False
                silence_count = 0

async def process_utterance(frames, sample_rate, num_channels,audio_source):
    try:
        filename = "room_input.wav"
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for frame in frames:
                wf.writeframes(bytes(frame.data))

        transcript = transcribe_file(filename)
        print("User said:", transcript)
        if not transcript.strip():
            return

        reply_text = get_agent_reply(transcript, conversation_history)
        print("Ava:", reply_text)

        # speak(reply_text)   # currently plays on YOUR local speaker, not the room yet — next step fixes that
        # await asyncio.to_thread(speak, reply_text)
        audio_bytes = generate_speech(reply_text)
        await play_audio_bytes(audio_source, audio_bytes)
    except Exception as e:
        print(f"Error handling utterance :{e}")

def register_audio_handlers(room: rtc.Room,audio_source: rtc.AudioSource):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_audio_track(track,audio_source))


 

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

