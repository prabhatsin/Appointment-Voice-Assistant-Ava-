# import asyncio
# import sounddevice as sd
# import numpy as np
# from voice_io.tts_stream import stream_speech

# SAMPLE_RATE = 24000

# async def main():
#     stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
#     stream.start()

#     async def on_chunk(data):
#         samples = np.frombuffer(data, dtype=np.int16)
#         await asyncio.to_thread(stream.write, samples)

#     await stream_speech("Hello, this is a live test of streaming text to speech, spoken as it is generated.", on_chunk)

#     stream.stop()
#     stream.close()

# if __name__ == "__main__":
#     asyncio.run(main())