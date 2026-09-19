import asyncio
import os
import logging
from dotenv import load_dotenv
from livekit import rtc
from transport.token_server import generate_token, ROOM_NAME
from transport.livekit_session import register_audio_handlers
load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)

async def main():
    room = rtc.Room()
    register_audio_handlers(room)
    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant joined: {participant.identity}")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant left: {participant.identity}")

    token = generate_token(ROOM_NAME, "ava-agent")
    await room.connect(os.environ["LIVEKIT_URL"], token)
    logging.info(f"Ava connected to room: {room.name}")

    await asyncio.Event().wait()  # keep running

if __name__ == "__main__":
    asyncio.run(main())