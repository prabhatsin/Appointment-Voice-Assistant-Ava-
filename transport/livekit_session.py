
import asyncio
import wave
import numpy as np
from livekit import rtc

from voice_io.stt import transcribe_file
from agent_core.main_loop import get_agent_reply
from voice_io.tts import speak

SILENCE_THRESHOLD = 300
SILENCE_FRAMES_TO_STOP = 60
conversation_history = []   # persists across utterances for this session

async def handle_audio_track(track: rtc.Track):
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
                await process_utterance(buffer, frame.sample_rate, frame.num_channels)
                buffer = []
                speaking = False
                silence_count = 0

async def process_utterance(frames, sample_rate, num_channels):
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
        await asyncio.to_thread(speak, reply_text)
    except Exception as e:
        print(f"Error handling utterance :{e}")

def register_audio_handlers(room: rtc.Room):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_audio_track(track))

