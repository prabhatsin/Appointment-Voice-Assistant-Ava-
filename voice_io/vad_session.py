
import numpy as np
#we'll use to turn raw bytes into numbers.
import torch 
#Is what that model runs on, so audio has to be converted into a torch tensor before it can be fed in
from silero_vad import load_silero_vad

SAMPLE_RATE = 16000
WINDOW_SAMPLES = 512
WINDOW_BYTES = WINDOW_SAMPLES * 2   # 16-bit audio = 2 bytes per sample

# Each  sample is represented by the 16 bits(bit depth) i.e 2 bytes

class VADStream:

    def __init__(self):
        self.model=load_silero_vad() # returns a fresh model each call.
        self.buffer=b""

    def reset(self):
        self.model.reset_states() # forget the model's memory
        self.buffer=b""           # drop leftover audio
    def get_probabilities(self, frame:bytes):
        # Frame	:A group of consecutive samples processed/transmitted together
        # Here its that frame its just in bytes , 
        '''
        Add raw  audio bytes( with 16-bit bith depth), run the model on every complete 512-sample window, and 
        return one speech probability per window.
        '''
        
        self.buffer+=frame
        print(self.buffer)
        # print(frame)
        probs=[]
        while len(self.buffer)>=WINDOW_BYTES:
            chunk=self.buffer[:WINDOW_BYTES]
            self.buffer=self.buffer[WINDOW_BYTES:]
            samples=np.frombuffer(chunk,dtype=np.int16).astype(np.float32)/32768.0
            prob=self.model(torch.from_numpy(samples),SAMPLE_RATE).item()
            # .item(): turns the model's one-number tensor into a plain Python float
            probs.append(prob)
        return probs




#? Why not make it async def when eventually we will use , to_thread to execute it , ?? 

'''
Because async def doesn't move work to another thread. An async function still runs on the event loop's 
own thread, and it only gives control back at an await. Silero's model call is plain CPU work with nothing 
to await, so inside an async def it would block the whole loop just the same. The thread is what frees 
the loop, and to_thread provides that.

'''









#!----------------------------------------------------test---------------------------------




v = VADStream()
print(v.get_probabilities(bytes(1024 * 3)))      # 3 windows of silence
# print(v.get_probabilities(bytes(500)))           # not a full window yet
# print(v.get_probabilities(bytes(524)))           # 500 + 524 = 1024, so exactly 1 window