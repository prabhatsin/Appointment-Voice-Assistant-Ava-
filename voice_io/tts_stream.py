import asyncio
import time
from dotenv import load_dotenv
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text   # <-- add this import

# load_dotenv(".env.local")
# After a Clear, audio is dropped until Deepgram's Cleared reply (normally ~0.2-0.5 s). If that reply never
# comes, playback resumes after this many seconds rather than staying muted.
CLEAR_TIMEOUT = 2.0

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
        # Deepgram numbers Flushed replies per socket, in the order the flushes were sent
        self._flushes_sent = 0
        self._first_live_flush = 0   # Flushed replies below this belong to text sent before the last Clear
        self._clears_pending = 0     # Clears sent whose Cleared reply hasn't arrived yet
        self._drop_until = 0.0

        async def on_message(message):
            if isinstance(message, bytes):
                # Deepgram answers a Clear before generating anything sent after it, so audio that arrives
                # between our Clear and its Cleared reply belongs to the cancelled reply
                if self._clears_pending and time.monotonic() < self._drop_until:
                    return
                if self._current_on_chunk:
                    await self._current_on_chunk(message)
            # The SDK also parses Cleared replies as SpeakV1Flushed, so check the type field
            elif getattr(message, "type", None) == "Flushed" and message.sequence_id >= self._first_live_flush:
                self._pending_flushes -= 1
                if self._pending_flushes <= 0:
                    self._flush_event.set()
            elif getattr(message, "type", None) == "Cleared":
                self._clears_pending = max(0, self._clears_pending - 1)

        self.connection.on(EventType.MESSAGE, on_message)
        self._listen_task = asyncio.create_task(self.connection.start_listening())

    def set_chunk_handler(self, on_chunk):
        self._current_on_chunk = on_chunk

    async def _ensure_connected(self):
        # Deepgram ends /v1/speak sockets after 60 min (1011 NET-0003); open a fresh one if it's gone
        if not self._listen_task.done():
            return
        try:
            await self._ctx.__aexit__(None, None, None)
        except Exception:
            pass
        self._pending_flushes = 0   # flushes owed by the dead socket will never arrive
        self._flush_event.set()
        await self.connect()

    async def send(self, text: str):
        await self._ensure_connected()
        self._pending_flushes += 1
        self._flushes_sent += 1
        self._flush_event.clear()
        await self.connection.send_text(SpeakV1Text(text=text))
        await self.connection.send_flush()

    async def wait_until_done(self):
        if self._pending_flushes > 0:
            await self._flush_event.wait()

    async def stop(self):
        await self._ensure_connected()
        self._pending_flushes = 0
        self._first_live_flush = self._flushes_sent   # replies to earlier flushes no longer count
        self._clears_pending += 1
        self._drop_until = time.monotonic() + CLEAR_TIMEOUT
        self._flush_event.set()
        await self.connection.send_clear()

    async def close(self):
        self._listen_task.cancel()
        await self._ctx.__aexit__(None, None, None)


#TODO: Understand this well and then write 

#! Why this v1 thing here but not in , STT part , ?? 