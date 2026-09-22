import asyncio
import os
import logging
from dotenv import load_dotenv
from livekit import rtc
from transport.token_server import generate_token, ROOM_NAME
from transport.livekit_session import register_audio_handlers,setup_audio_output
from transport.livekit_session import conversation_history
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

    audio_source = await setup_audio_output(room)
    register_audio_handlers(room, audio_source)

    await asyncio.Event().wait()  # keep running

if __name__ == "__main__":
    asyncio.run(main())
    






#! LEARNINGS

'''
#? 1
#?-->   " load_dotenv() vs load_dotenv(".env.local") "

Usually you have a .env file:
So when we write 

load_dotenv()

url = os.getenv("LIVEKIT_URL")

-> So load_dotenv() loads variables from the .env file into the environment.
--> But when we write load_dotenv(".env.local"), it will refer to this explicit file , alsways 

#?-->   os.getenv() vs os.environ[]
# url = os.getenv("LIVEKIT_URL")  vs  os.environ["LIVEKIT_URL"]

i) os.getenv("LIVEKIT_URL"),    If it doesn't exist → returns:  None

ii) os.environ["LIVEKIT_URL"] --> If it doesn't exist → raises:  KeyError: 'LIVEKIT_URL'

'''



#? logging.basicConfig(level=logging.INFO)
'''
1. First, what is logging?

Python has a built-in logging module:

import logging

logging.info("Server started")
logging.warning("Something looks wrong")
logging.error("Something failed")

Instead of using:
print("Server started")
you can use logging, which gives you different severity levels.



#!  2.What does level=logging.INFO mean?

Python logging has levels roughly like this:

DEBUG       ← most detailed
INFO
WARNING
ERROR
CRITICAL   ← most severe

When you write:

logging.basicConfig(level=logging.INFO)

you're saying:

"Display INFO and everything above INFO."

So:
logging.debug("Debug message")       # ❌ won't show
logging.info("Server started")       # ✅ shows
logging.warning("Something wrong")  # ✅ shows
logging.error("Request failed")     # ✅ shows
logging.critical("System crashed") # ✅ shows

'''