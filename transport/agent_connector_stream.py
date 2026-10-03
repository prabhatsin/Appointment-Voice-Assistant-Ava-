import asyncio
import os
import logging
from dotenv import load_dotenv
from livekit import rtc
from transport.token_server import generate_token, ROOM_NAME
from transport.livekit_session_stream import register_audio_handlers,setup_audio_output
from transport.conversation_handler import conversation_history, handle_conversation
import signal
from voice_io.tts_stream import PersistentTTS
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)

#!  Summary of this Script :
'''
connect to the LiveKit room → set up TTS and audio output → register handlers that will react to future 
events (participants joining, tracks appearing) → then sit and do nothing itself forever, letting those 
registered handlers drive everything from here on.
'''

async def main():
    room = rtc.Room() 
    shutdown_event = asyncio.Event()

    @room.on("participant_connected")

    def on_participant_connected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant joined: {participant.identity}")
        conversation_history.clear()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant left: {participant.identity}")
        conversation_history.clear()
        #TODO: Manage the Memory instead this clear history behavior , plug in a memory system , 


    token = generate_token(ROOM_NAME, "ava-agent")

    await room.connect(os.environ["LIVEKIT_URL"], token)

    logging.info(f"Ava connected to room: {room.name}")


    tts = PersistentTTS() #! explore this class PersistantTTS  in depth 

    await tts.connect()

    audio_source = await setup_audio_output(room)
    register_audio_handlers(room, audio_source,tts)

    if not room.remote_participants:
        logging.info("No participants currently in the room on restart")
     # --- NEW: handle participants already present before the agent joined ---
    for identity, participant in room.remote_participants.items():
        logging.info(f"Found already-connected participant: {identity}")
        conversation_history.clear()

        for track_pub in participant.track_publications.values():
            if track_pub.track is not None and track_pub.track.kind == rtc.TrackKind.KIND_AUDIO:
                logging.info(f"Manually starting conversation handler for existing track from {identity}")
                asyncio.ensure_future(handle_conversation(track_pub.track, audio_source, tts))

    # await asyncio.Event().wait()
    # --- NEW: handle Ctrl+C / kill ---
    loop = asyncio.get_running_loop()

    def handle_shutdown():
        logging.info("Shutdown signal received, disconnecting agent from room...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    await shutdown_event.wait()  # blocks here normally, releases on Ctrl+C/kill

    await tts.close()
    await room.disconnect()
    logging.info("Ava disconnected cleanly, exiting")




if __name__ == "__main__":
    asyncio.run(main()) #? The Bridge between sync and async world


#? Question : Why does a this script creates a Persistent tts connection but not stt one , ?? 
#!TTS belongs to Ava, STT belongs to each user.
'''
1. TTS is Ava's voice. There's one Ava, one outgoing audio track, and one TTS connection shared for the 
whole session. So it's created once at startup and stays open (that's what "Persistent" means).

#? what does it mean by "TS connection shared for the whole session " ? 
-> The TTS connection lives as long as the script is running,
-> It's opened once in main() and only ends when you stop the script.So it stays open across multiple users joining 
and leaving. (The conversation history is what resets per user, via conversation_history.clear().)


#? Doubt : In the production systems is the TTS connection connection persist forever , ?? because there the main scrip always runs ?

Real deployed agents are typically long-running workers, and the usual pattern is one of two:

i). Per-call/per-session connection: a worker gets assigned a room when a call starts, opens STT/TTS for that 
call, and closes them when it ends. This is the most common, since idle connections cost resources and servers
close them anyway.

ii). Persistent connection with reconnect logic: a connection is kept open, but with keepalives and 
auto-reconnect,because long-lived WebSockets eventually drop


2. STT is per listener. 

When Ava starts, the room may be empty. There is no user audio yet, so there is nothing to transcribe.
A user's audio only arrives when they join and turn on their mic, which fires track_subscribed.Each user's mic 
is its own separate audio stream, so each one needs its own STT connection to turn that speech into text.That's
why stt_connect() is called inside handle_conversation, which runs once per user track.

Contrast with TTS: there is only one Ava, so one TTS connection is enough. It is created once at startup in 
main() and stays open until you stop the script.

Short version:

TTS = Ava's voice → one, created at startup.
STT = Ava's ears for a specific user → one per user, created when that user's track arrives.

'''