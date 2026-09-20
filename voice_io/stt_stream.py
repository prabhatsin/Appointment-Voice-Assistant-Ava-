import asyncio
import sounddevice as sd
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from dotenv import load_dotenv

load_dotenv(".env.local")

SAMPLE_RATE = 16000
CHUNK_SIZE = 1024  # samples per chunk sent

async def stream_mic_to_deepgram():
    client = AsyncDeepgramClient()

#?  Question whats v1, v2 here in listen v1,v2
    async with client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=str(SAMPLE_RATE),
    ) as connection:

        async def on_message(message):
            if message.type == "TurnInfo" and message.event == "EndOfTurn" and message.transcript:
                print("Live transcript:", message.transcript)

        connection.on(EventType.MESSAGE, on_message)

        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time_info, status):
            asyncio.run_coroutine_threadsafe(
                connection.send_media(indata.tobytes()), loop
            )

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=CHUNK_SIZE, callback=audio_callback
        ):
            print("Streaming mic to Deepgram... speak now (Ctrl+C to stop)")
            await connection.start_listening()

if __name__ == "__main__":
    asyncio.run(stream_mic_to_deepgram())







#! Mistake and learning, 

'''
#? Earlier we used below given def on message 

async def on_message(message):
    if hasattr(message, "channel"):
        transcript = message.channel.alternatives[0].transcript
        if transcript:
            print("Live transcript:", transcript)
 
#?Mistake:

#Code checked hasattr(message, "channel") and read message.channel.alternatives[0].transcript
#This assumes Deepgram's v1 (older websocket) response shape
# Listen v2 / Flux (what we're using) has a different message structure — transcript is a direct attribute 
 on the message, not nested under .channel

# Since message never actually had .channel, hasattr(...) was always False → the block never ran → nothing 
  printed, even though the connection and mic were both working fine
 


=>hasattr(object, "name") checks whether an object has an attribute with that name, returning True or False 
— in your case, hasattr(message, "channel") was always False because message never had a .channel attribute 
at all.

'''

#! Lession

'''
Lesson: always verify the actual response object shape (print raw message) rather than assuming a fixed 
schema — SDK/API versions (v1 vs v2/Flux) can structure responses differently.
'''