import asyncio
from dotenv import load_dotenv
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text   # <-- add this import

load_dotenv(".env.local")

# async def stream_speech(text: str, on_chunk):
#     '''Streams TTS audio chunks as they're generated. Calls on_chunk(bytes) for each chunk as it arrives.'''
#     client = AsyncDeepgramClient()

#     async with client.speak.v1.connect(
#         model="aura-2-hera-en",
#         encoding="linear16",
#         sample_rate=24000,
#     ) as connection:

#         async def on_message(message):
#             if hasattr(message, "data") and message.data:
#                 await on_chunk(message.data)

#         connection.on(EventType.MESSAGE, on_message)

#         await connection.send_text(SpeakV1Text(text=text))   # <-- changed this line
#         await connection.send_flush()

#         await connection.start_listening()

async def stream_speech(text: str, on_chunk):
    client = AsyncDeepgramClient()

    async with client.speak.v1.connect(
        model="aura-2-hera-en",
        encoding="linear16",
        sample_rate=24000,
    ) as connection:

        done = asyncio.Event()

        async def on_message(message):
            if isinstance(message, bytes):
                await on_chunk(message)
            elif type(message).__name__ == "SpeakV1Flushed":
                done.set()   # signals we're finished receiving audio

        connection.on(EventType.MESSAGE, on_message)

        await connection.send_text(SpeakV1Text(text=text))
        await connection.send_flush()

        listen_task = asyncio.create_task(connection.start_listening())
        await done.wait()          # wait until Flushed arrives
        listen_task.cancel()       # then stop listening, don't hang forever