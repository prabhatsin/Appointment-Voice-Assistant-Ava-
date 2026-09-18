import sounddevice as sd
from scipy.io.wavfile import write as wav_write
from deepgram import DeepgramClient
from dotenv import load_dotenv
load_dotenv(".env.local")

client = DeepgramClient()
SAMPLE_RATE = 16000

#!: Explore what exactly this function does , in detail 
def listen(duration=5) -> str:
    print(f"Recording {duration}s...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    wav_write("mic_input.wav", SAMPLE_RATE, audio)

    with open("mic_input.wav", "rb") as f:
        response = client.listen.v1.media.transcribe_file(request=f.read(), model="nova-3")
    return response.results.channels[0].alternatives[0].transcript




#TODO: We should change it from the fixed 5 seconds to silence based ,that is it should stop when i stop asking not after 5 seconds
#! this is VAD(Voice activity detection)
#  or VAD-based turn detection

#TODO: There is no real time thing happening here currency , its pre-recoreded/RESt endpoint 

'''
1.Good catch — no, your current stt.py does not use websockets. It's using Deepgram's pre-recorded/REST 
endpoint: record 5 seconds → save as a complete .wav file → send the whole file in one HTTP POST → get one 
transcript back. That's a single request-response, not a persistent connection.

#? Its not real time streaming

2. Your current approach (record fixed duration → send as one file) is simpler and fine for what you're 
doing right now (proving the STT layer works), but it's not real-time streaming — there's an inherent 
"wait for the full clip, then transcribe" delay. Moving to real silence-based turn detection later will 
naturally push you toward the websocket/streaming approach too,

'''

