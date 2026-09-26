import asyncio
from voice_io.stt_stream_final import stt_connect, stt_on_turn_end, send_audio, stt_register_listener, stt_close
import sounddevice as sd

SAMPLE_RATE = 16000

from dotenv import load_dotenv
load_dotenv(".env.local")


async def on_turn_end(transcript):
    print("Final transcript:", transcript)

async def main():
    await stt_connect()
    stt_on_turn_end(on_turn_end)

    loop = asyncio.get_event_loop()
    #Gets a reference to the currently running event loop

    def audio_callback(indata, frames, time_info, status):
        asyncio.run_coroutine_threadsafe(send_audio(indata.tobytes()), loop)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024, callback=audio_callback):
        print("Speak now (Ctrl+C to stop)")
        await stt_register_listener()

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