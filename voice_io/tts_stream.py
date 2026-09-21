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

# async def stream_speech(text: str, on_chunk):
#     client = AsyncDeepgramClient()

#     async with client.speak.v1.connect(
#         model="aura-2-hera-en",
#         encoding="linear16",
#         sample_rate=24000,
#     ) as connection:

#         done = asyncio.Event()

#         async def on_message(message):
#             if isinstance(message, bytes):
#                 await on_chunk(message)
#             elif type(message).__name__ == "SpeakV1Flushed":
#                 done.set()   # signals we're finished receiving audio

#         connection.on(EventType.MESSAGE, on_message)

#         await connection.send_text(SpeakV1Text(text=text))
#         await connection.send_flush()

#         listen_task = asyncio.create_task(connection.start_listening())
#         await done.wait()          # wait until Flushed arrives
#         listen_task.cancel()       # then stop listening, don't hang forever


from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text
import asyncio

# class PersistentTTS:
#     def __init__(self):
#         self.client = AsyncDeepgramClient()
#         self.connection = None
#         self._current_done = None
#         self._current_on_chunk = None

#     async def connect(self):
#         self._ctx = self.client.speak.v1.connect(
#             model="aura-2-hera-en", encoding="linear16", sample_rate=24000,
#         )
#         self.connection = await self._ctx.__aenter__()

#         async def on_message(message):
#             if isinstance(message, bytes):
#                 if self._current_on_chunk:
#                     await self._current_on_chunk(message)
#             elif type(message).__name__ == "SpeakV1Flushed":
#                 if self._current_done:
#                     self._current_done.set()

#         self.connection.on(EventType.MESSAGE, on_message)
#         self._listen_task = asyncio.create_task(self.connection.start_listening())

#     async def speak(self, text: str, on_chunk):
#         self._current_on_chunk = on_chunk
#         self._current_done = asyncio.Event()

#         await self.connection.send_text(SpeakV1Text(text=text))
#         await self.connection.send_flush()
#         await self._current_done.wait()

#     async def close(self):
#         self._listen_task.cancel()
#         await self._ctx.__aexit__(None, None, None)



class PersistentTTS:
    def __init__(self):
        self.client = AsyncDeepgramClient()
        self.connection = None
        self._current_on_chunk = None
        self._pending_flushes = 0
        self._flush_event = asyncio.Event()

    async def connect(self):
        self._ctx = self.client.speak.v1.connect(
            model="aura-2-hera-en", encoding="linear16", sample_rate=24000,
        )
        self.connection = await self._ctx.__aenter__()

        async def on_message(message):
            if isinstance(message, bytes):
                if self._current_on_chunk:
                    await self._current_on_chunk(message)
            elif type(message).__name__ == "SpeakV1Flushed":
                self._pending_flushes -= 1
                if self._pending_flushes <= 0:
                    self._flush_event.set()

        self.connection.on(EventType.MESSAGE, on_message)
        self._listen_task = asyncio.create_task(self.connection.start_listening())

    def set_chunk_handler(self, on_chunk):
        self._current_on_chunk = on_chunk

    async def send(self, text: str):
        self._pending_flushes += 1
        self._flush_event.clear()
        await self.connection.send_text(SpeakV1Text(text=text))
        await self.connection.send_flush()

    async def wait_until_done(self):
        if self._pending_flushes > 0:
            await self._flush_event.wait()

    async def stop(self):
        self._pending_flushes = 0
        self._flush_event.set()
        await self.connection.send_clear()

    async def close(self):
        self._listen_task.cancel()
        await self._ctx.__aexit__(None, None, None)