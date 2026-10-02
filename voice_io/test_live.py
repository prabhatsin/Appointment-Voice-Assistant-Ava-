import asyncio
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from dotenv import load_dotenv
load_dotenv()

SAMPLE_RATE = 16000

async def main():
    client = AsyncDeepgramClient(api_key="8d4099fcafbd9d5e09786bad0096b82cf3e32ad7")
    ctx = client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=str(SAMPLE_RATE),
    )
    connection = await ctx.__aenter__()
    print("Connected")

    def on_any(message):
        print("EVENT:", repr(message))

    connection.on(EventType.MESSAGE, on_any)
    connection.on(EventType.OPEN, lambda m: print("OPEN"))
    connection.on(EventType.CLOSE, lambda m: print("CLOSE"))
    connection.on(EventType.ERROR, lambda m: print("ERROR", m))

    # Send 5 seconds of silence (zeros)
    async def send_silence():
        chunk = b'\x00' * (SAMPLE_RATE * 2 // 10)  # 100ms of silence
        for _ in range(50):  # 50 * 100ms = 5 seconds
            await connection.send_media(chunk)
            await asyncio.sleep(0.1)
        print("Done sending")

    await asyncio.gather(
        send_silence(),
        connection.start_listening()
    )
    await ctx.__aexit__(None, None, None)

asyncio.run(main())



'''
asyncio.run_coroutine_threadsafe(coro, loop) is a built-in Python function used to submit a coroutine to an 
event loop that is running in a different OS thread.

'''

'''
Putting it together, in one sentence: open the mic on a background thread, continuously bridge captured
audio chunks into the async world via send_audio, while simultaneously listening for Deepgram's 
responses — printing live partials and the final transcript once each sentence completes.
'''

#! Question why we using here synchronous function for mic audio, ?? 
'''
sounddevice is a library built entirely around a traditional, synchronous, thread-based callback model — 
it has no concept of asyncio at all. Internally, sd.InputStream calls your callback function using plain, 
synchronous Python function calls

'''

#? Contrast this with LiveKit's rtc.AudioStream in your real pipeline — that one is designed to work with asyncio natively (async for event in audio_stream:), which is exactly why your real forward_audio