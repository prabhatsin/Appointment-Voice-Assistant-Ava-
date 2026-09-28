import sounddevice as sd
from voice_io.vad_stream import detect_speech, SAMPLE_RATE

def audio_callback(indata, frames, time_info, status):
    for is_speech in detect_speech(indata.tobytes()):
        print("#" if is_speech else ".", end="", flush=True)

with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                    blocksize=160, callback=audio_callback):
    print("Speak, then stay silent (Ctrl+C to stop)")
    while True:
        sd.sleep(1000)