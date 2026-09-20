# import sounddevice as sd
# print(sd.query_devices())


# import sounddevice as sd
# import numpy as np

# def callback(indata, frames, time, status):
#     volume = np.linalg.norm(indata)
#     print(f"Volume: {volume:.2f}")

# with sd.InputStream(samplerate=16000, channels=1, dtype="int16", callback=callback):
#     print("Listening... speak now (Ctrl+C to stop)")
#     sd.sleep(5000)


import asyncio
import time
from voice_io.tts_stream import stream_speech

async def main():
    chunks_received = []
    start = time.time()

    async def on_chunk(data):
        elapsed = time.time() - start
        print(f"Chunk received at {elapsed:.2f}s, size={len(data)} bytes")
        chunks_received.append(data)

    await stream_speech("Hello, this is a test of streaming text to speech, spoken over multiple chunks.", on_chunk)

    print(f"Total chunks: {len(chunks_received)}")

if __name__ == "__main__":
    asyncio.run(main())


import wave

async def main():
    chunks_received = []
    start = time.time()

    async def on_chunk(data):
        elapsed = time.time() - start
        print(f"Chunk received at {elapsed:.2f}s, size={len(data)} bytes")
        chunks_received.append(data)

    await stream_speech("Hello, this is a test of streaming text to speech, spoken over multiple chunks.", on_chunk)

    print(f"Total chunks: {len(chunks_received)}")

    # Save all chunks as one playable WAV file
    with wave.open("stream_test_output.wav", "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(24000)
        for chunk in chunks_received:
            wf.writeframes(chunk)

    print("Saved to stream_test_output.wav")