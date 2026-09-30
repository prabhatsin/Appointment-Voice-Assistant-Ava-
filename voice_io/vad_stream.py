
#? This file will only answer "is this chunk speech?".

import numpy as np # we'll use to turn raw bytes into numbers.
import torch # Is what that model runs on, so audio has to be converted into a torch tensor before it can be fed in
from silero_vad import load_silero_vad
# silero_vad provides the pretrained model

SAMPLE_RATE=16000 # The value has to match what LiveKit and Deepgram are using.
VAD_CHUNK_SAMPLES=512
VAD_THRESHOLD=0.5
SPEECH_CONFIRM_CHUNKS = 3

vad_model=load_silero_vad()

vad_buffer=b""
# Its a holding area for audio that has arrived but hasn't been analyzed yet.
#? What problem does vad_buffer solve ?? 

'''
#!The problem it solves:
Silero VAD only accepts audio in exact pieces of 512 samples (1024 bytes). LiveKit 
doesn't deliver audio in that size. It sends small frames, often about 10ms each, which is 160 samples 
#? Question : How does livekit came in the picture here , i mean  

(320 bytes). Those numbers don't divide evenly, so you can't hand each frame straight to the model.

'''
#! How the buffer fixes it:
'''
append every incoming frame to the buffer, and whenever it holds at least 1024 bytes, cut off a full piece 
for the model. Whatever is left over stays in the buffer until the next frame arrives.
'''

#TODO: Explore 
'''
=> Audio is a stream of samples, and the sample rate says how many arrive per second. 
=> Bytes and milliseconds are two ways of measuring the same amount of audio.

#? How to conver this in millisecond ,?
We know 16000 sample is 1 seconds
so 512 samples= 512/16000 =32 ms of data 
160 sample= 160/16000=10ms of data

#? How to convert into bytes ?
since in deepgram settings we mentioned depth of 16 bits which is 2 bytes per sample 

'''



def detect_speech(raw:bytes)->list[bool]:
    global vad_buffer
    vad_buffer+=raw
    chunk_bytes=VAD_CHUNK_SAMPLES *2 # 2 bytes per 16 bit sample 

    results =[]

    while len(vad_buffer) >=chunk_bytes:
        chunk=vad_buffer[:chunk_bytes] # slices off the first 1024 bytes. That's the piece we'll give to the model.
        vad_buffer=vad_buffer[chunk_bytes:] # keeps everything after the first 1024 bytes and drops the part we just took.
        
        samples=np.frombuffer(chunk,dtype=np.int16).astype(np.float32)/32768.0

        #np.frombuffer(chunk, dtype=np.int16): chunk is 1024 raw bytes with no structure. This tells numpy to read them as a sequence of 16-bit integers,
        # .astype(np.float32) converts those integers into decimal (floating-point) numbers.
        # / 32768.0 rescales them. A 16-bit integer ranges from -32768 to 32767, so dividing by 32768 puts every sample in the range -1.0 to 1.0.

        prob=vad_model(torch.from_numpy(samples),SAMPLE_RATE)
        # torch.from_numpy(samples) wraps the numpy array as a torch tensor.
        # vad_model(tensor, SAMPLE_RATE)     calls the model like a function. It looks at the 512 samples 
        # and returns a speech probability. It needs the sample rate because the model behaves differently at 8kHz and 16kHz, so you tell it which one this is.   
        #.item() turns the result into a plain Python float

        results.append(prob>VAD_THRESHOLD)
        # prob > VAD_THRESHOLD is a comparison that evaluates to True or False
    return results