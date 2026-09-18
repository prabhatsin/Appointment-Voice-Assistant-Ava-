import os
from dotenv import load_dotenv
from deepgram import DeepgramClient
import subprocess
import re




load_dotenv(".env.local")

client = DeepgramClient()


def clean_for_speech(text: str) -> str:
    return re.sub(r'[*_#`]', '', text)

def speak(text: str, filename="reply.mp3"):
    text = clean_for_speech(text)
    response = client.speak.v1.audio.generate(text=text)
    with open(filename, "wb") as f:
        for chunk in response:
            f.write(chunk)
    subprocess.run(["mpv", filename, "--really-quiet"])



#TODO: Read and observe both , 

# 1. Since its pre recorded so ,when the assistant is speaking it doesnt stop even if u speak in between 

# Also add observability regarding the , latency in the whole pipeline 

#! learning-----------------


'''

1.mpv is just a lightweight command-line media player for Linux — it plays audio/video files from the 
terminal with no GUI needed,

Two ways to think about this:

i)For now (local testing): you need some player to hear the output, mpv is just a convenient one-line 
choice.


ii) In the real product (browser frontend + LiveKit later): this whole "play the file with mpv" step 
disappears entirely — the TTS audio gets published into the LiveKit room as a live audio track, and the 
browser plays it natively for the user, same as any audio/video call. mpv was only ever a stand-in for 
that, useful for testing this layer in isolation on your terminal before LiveKit enters the picture.


'''