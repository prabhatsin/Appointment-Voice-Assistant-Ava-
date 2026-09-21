import asyncio
import os
import logging
from dotenv import load_dotenv
from livekit import rtc
from transport.token_server import generate_token, ROOM_NAME
from transport.livekit_session_stream import register_audio_handlers,setup_audio_output
from transport.livekit_session_stream import conversation_history

from voice_io.tts_stream import PersistentTTS


load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)

async def main():
    room = rtc.Room()

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant joined: {participant.identity}")
        conversation_history.clear()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant left: {participant.identity}")

    token = generate_token(ROOM_NAME, "ava-agent")
    await room.connect(os.environ["LIVEKIT_URL"], token)
    logging.info(f"Ava connected to room: {room.name}")


    tts = PersistentTTS()
    await tts.connect()
    audio_source = await setup_audio_output(room)
    register_audio_handlers(room, audio_source,tts)

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())