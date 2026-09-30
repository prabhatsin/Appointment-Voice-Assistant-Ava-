import asyncio
from livekit import rtc
from transport.conversation_handler import handle_conversation

SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
TTS_NUM_CHANNELS = 1

async def setup_audio_output(room: rtc.Room) -> rtc.AudioSource:
    source = rtc.AudioSource(TTS_SAMPLE_RATE, TTS_NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("ava-voice", source)
    await room.local_participant.publish_track(track)
    return source

def register_audio_handlers(room: rtc.Room, audio_source: rtc.AudioSource, tts):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(handle_conversation(track, audio_source, tts))



