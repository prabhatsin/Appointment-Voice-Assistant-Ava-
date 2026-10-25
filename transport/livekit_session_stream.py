import asyncio
from livekit import rtc
from transport.conversation_handler import handle_conversation

SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
TTS_NUM_CHANNELS = 1

# One conversation handler per participant: identity -> (track sid, handler task)
handlers: dict[str, tuple[str, asyncio.Task]] = {}

async def setup_audio_output(room: rtc.Room) -> rtc.AudioSource:
    source = rtc.AudioSource(TTS_SAMPLE_RATE, TTS_NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("ava-voice", source)
    await room.local_participant.publish_track(track)
    return source

def start_conversation(track: rtc.Track, identity: str, audio_source: rtc.AudioSource, tts):
    """Start the handler for this participant's audio track. Safe to call twice for the same track."""
    running = handlers.get(identity)
    if running and running[0] == track.sid and not running[1].done():
        return
    stop_conversation(identity)   # a different (new) track from the same participant replaces the old one
    print(f"Starting conversation handler for {identity} (track {track.sid})")
    handlers[identity] = (track.sid, asyncio.ensure_future(handle_conversation(track, audio_source, tts)))

def stop_conversation(identity: str, track_sid: str | None = None):
    """Cancel this participant's handler; its finally blocks close the STT socket and audio stream."""
    running = handlers.get(identity)
    if not running or (track_sid and running[0] != track_sid):
        return
    del handlers[identity]
    if not running[1].done():
        print(f"Stopping conversation handler for {identity}")
        running[1].cancel()

async def stop_all_conversations():
    tasks = [task for _, task in handlers.values()]
    for identity in list(handlers):
        stop_conversation(identity)
    await asyncio.gather(*tasks, return_exceptions=True)

def register_audio_handlers(room: rtc.Room, audio_source: rtc.AudioSource, tts):
    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track subscribed: kind={track.kind} from {participant.identity}")
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            start_conversation(track, participant.identity, audio_source, tts)

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            stop_conversation(participant.identity, track.sid)

    @room.on("participant_disconnected")
    def on_participant_gone(participant: rtc.RemoteParticipant):
        stop_conversation(participant.identity)
