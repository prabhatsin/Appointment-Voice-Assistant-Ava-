import asyncio
from dotenv import load_dotenv
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text   # <-- add this import

# load_dotenv(".env.local")
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


#TODO: Understand this well and then write 

#! Why this v1 thing here but not in , STT part , ?? 