
import numpy as np
#we'll use to turn raw bytes into numbers.
import torch 
#Is what that model runs on, so audio has to be converted into a torch tensor before it can be fed in
from silero_vad import load_silero_vad
from dataclasses import dataclass
import asyncio



SAMPLE_RATE = 16000
WINDOW_SAMPLES = 512
WINDOW_BYTES = WINDOW_SAMPLES * 2   # 16-bit audio = 2 bytes per sample
SMOOTH_ALPHA=0.35
ACTIVATION = 0.5
DEACTIVATION = ACTIVATION - 0.15    # # LiveKit's default exit level: 0.35 
WINDOW_SEC=WINDOW_SAMPLES/SAMPLE_RATE # length of a window in seconds i.e 512 samples= 32 ms
MIN_SPEECH = 0.05    # speech in seconds needed in a row before START
MIN_SILENCE = 0.55   # silence in seconds needed in a row before END

# Each  sample is represented by the 16 bits(bit depth) i.e 2 bytes

#? What VAD does. ??
'''
# It answers one question over and over: "is a human voice present in this tiny slice of audio?" It doesn't 
know words.Silero is a small neural network that takes a slice of audio and outputs a probability from 0 to 1.
'''
# This is being used in the last method,analyze_frame
@dataclass 
class VADResult:
    probability:float    # # smoothed probability for this window
    speaking: bool       # inisde a speech segment after this window
    event:str | None     # "start","end",or None
    speech_time: float   # seconds of speech in a row
    silence_time : float # seconds of silence in a row

class VADStream:

    def __init__(self):
        self.model=load_silero_vad() # returns a fresh model each call.
        self.buffer=b""
        self.smoothed=None  # no previous value yet
        self.speaking = False   # are we currently inside a speech segment?
        self.speech_time = 0.0    # seconds of speech in a row
        self.silence_time = 0.0   # seconds of silence in a row

    def reset(self):
        self.model.reset_states() # forget the model's memory
        self.buffer=b""           # drop leftover audio
        self.smoothed = None
        self.speaking = False
        self.speech_time = 0.0
        self.silence_time = 0.0 

    # These two lines used to supress the warning from the loading the silero model
    import warnings
    warnings.filterwarnings("ignore", message=".*torch.jit.load.*", category=FutureWarning)
    def get_probabilities(self, frame:bytes):
        # Frame	:A group of consecutive samples processed/transmitted together
        # Here that frame is in bytes not number of samples, 
        '''
        Add raw  audio bytes( with 16-bit bit depth), run the model on every complete 512-sample window, and 
        return one speech probability per window.
        '''
        self.buffer+=frame
        # print(self.buffer)
        # print(frame)
        probs=[]
        while len(self.buffer)>=WINDOW_BYTES:
            chunk=self.buffer[:WINDOW_BYTES]
            self.buffer=self.buffer[WINDOW_BYTES:]
            # convert raw bytes into numbers ,
            samples=np.frombuffer(chunk,dtype=np.int16).astype(np.float32)/32768.0
            prob=self.model(torch.from_numpy(samples),SAMPLE_RATE).item()
            # .item(): turns the model's one-number tensor into a plain Python float
            probs.append(prob)
        return probs
    
    #! Step 4: Smoothing
    def smooth(self,prob:float)-> float:
        """Blend the new probability with the previous smoothed value."""

        if self.smoothed is None:
            # None at the start: with no history, the first value is used as it is, which is what LiveKit's filter does.
            self.smoothed=prob
        else:
            self.smoothed = SMOOTH_ALPHA*self.smoothed  + (1-SMOOTH_ALPHA)*prob
        return self.smoothed
        
    #!Step 5: Hysteresis
    '''
    In voice AI agents, hysteresis is a design technique that uses dual thresholds to prevent a system 
    from rapidly toggling or flickering between two states.
    '''
    def  is_speech(self, prob:float)-> bool:
        """Does this smoothed probability count as speech right now?"""
        # The codition to start
        # Strong signal: at or above the entry bar, it's speech.
        # This works in either state, silent or speaking.(i.e pahle se bol rhe hai or bolna start kiya in both case)
        if prob>= ACTIVATION:
            return True
        # Weak signal (below 0.5): only counts if we're already inside a
        # speech segment and the value hasn't dropped below the exit bar (0.35).
        # self.speaking is False until detect_transition fires "start", so
        # this branch can only return True after a start has happened.
        if self.speaking and prob > DEACTIVATION:
            return True

        # Everything else is silence: too weak to start speech, or too
        # weak to keep it going.
        return False
    

    #! Step 6: start/end state machine
    # A state machine is a program that is always in exactly one state and moves to another only when a specific event happens.
    # The name detect_transition because :A transition is a state machine's word for moving from silent to speaking or back, and 
    #the return value ("start", "end" or None) is exactly that.
    def detect_transition(self, speech_window:bool):

        """Track speech/silence runs. Returns "start", "end", or None."""
        if speech_window:
            # Speech window: speech run grows, silence run restarts.
            self.speech_time +=WINDOW_SEC
            self.silence_time=0.0
            # Not speaking yet, but 0.05 s of speech in a row: START.
            # (The "not speaking" check stops repeated STARTs mid-sentence.)
            if not self.speaking and self.speech_time>=MIN_SPEECH:
                self.speaking=True
                return "start"

        # This block will only make sense once speech started and then suddenly pause      
        else:
            # Silent window: silence run grows, speech run restarts.
            self.silence_time+= WINDOW_SEC
            self.speech_time=0.0
            # Was speaking, but 0.55 s of silence in a row: END.
            # (The "speaking" check stops repeated ENDs during long silence.)
            if self.speaking and self.silence_time >= MIN_SILENCE:
                self.speaking=False
                return "end"
        return None

    # Skipping step7 for now ,because : Ava sends every frame to STT, so it isn't needed.
    #! step 8: join the stages and return one record per window
    def analyze_frame(self,frame:bytes) -> list[VADResult]:
        """It takes one frame and analyzes every window in it,runs through full chain"""
        results=[]
        for raw_prob in self.get_probabilities(frame):
            prob=self.smooth(raw_prob)
            speech_windows=self.is_speech(prob)
            event=self.detect_transition(speech_windows) # may change the flag
            results.append(VADResult(prob,self.speaking,event,self.speech_time,self.silence_time)) # record

        return results

    async def analyze_audio(self, frame: bytes) -> list[VADResult]:
        """Run _analyze_frame in a worker thread so the event loop stays free."""
        return await asyncio.to_thread(self.analyze_frame, frame)


# v = VADStream()
# r = v.analyze_frame(bytes(1024 * 3))
# print([(round(x.probability, 3), x.speaking, x.event) for x in r])



#? Learning and Note :

#! Is_speech and detect_transion always run in cordination , 
'''
# How is_speech() and detect_transition() work together
# (both run once per 32 ms window, in this order, sharing self.speaking)

# 1. is_speech(prob)  -> "Is THIS window speech?"  (True / False)
#      - READS self.speaking, never changes it.
#      - Not speaking: strict bar, needs prob >= 0.5. to tell if its speach or not
#      - Speaking:     lenient bar, prob > 0.35 is enough.


2. detect_transition(verdict) -> "Did a segment just start or end?"
#      - Takes the True/False verdict from step 1 and counts runs in a row.
#      - The ONLY place that CHANGES self.speaking.
#      - Returns "start", "end", or None (None on most windows).
#
# self.speaking is the shared flag:
#   False -> is_speech is strict
#   2 speech windows in a row (0.05 s) -> detect_transition sets True, returns "start"
#   True  -> is_speech becomes lenient (soft sounds don't break the segment)
#   0.55 s of silence in a row -> detect_transition sets False, returns "end"
#   False -> strict again
#
# Order matters: is_speech runs first and sees the flag left by the PREVIOUS window.

'''

# Order matters: is_speech runs first and sees the flag left by the PREVIOUS window.
#  Question: PREVIOUS window means ??

'''
"Previous window" means the window processed just before the current one, 32 ms earlier. The flag is stored on self, so it carries over between windows.
Yes. A window is one 512-sample chunk (32 ms of audio) that the model scores. "Previous window" is the chunk right before the current one.
'''
# For each window, the order is:
'''
1. is_speech reads self.speaking. At this point, the flag still holds whatever detect_transition left 
  after the previous window.
2. detect_transition runs and may change the flag. That new value is what the next window's is_speech 
   will read.
'''



#! What happens at the first WINDOW ??
'''
#?Window 1: (Assueme silence as starting audio)

1.Buffer and model. Mic frames pile up in self.buffer until 1024 bytes are there. Then get_probabilities 
cuts the first window, runs the model, and gets raw 0.10. Until that point nothing happens, and the 
earlier calls returned [].

2._smooth(0.10). smoothed is None, so there's no history. The first value is used as is: smoothed = 0.10.

3.is_speech(0.10). 0.10 is below 0.5, so the first if fails. The second if needs self.speaking, which 
is False, so it fails too. The result is False.

4.detect_transition(False). This takes the else branch:
  silence_time becomes 0.032
  speech_time is set to 0.0
  the END check needs self.speaking, which is False, so it's skipped
  the method returns None

State after window 1: smoothed = 0.10, speaking = False, speech_time = 0.0, silence_time = 0.032. No event was fired.

Window 2 starts from exactly this state. It blends its raw value into smoothed = 0.10, and is_speech sees speaking = False again.

'''







#! # (The "not speaking" check stops repeated STARTs mid-sentence.)

# Explanation :

'''
Without that check, START would fire again on every speech window after the first one.
Once the user has been talking for 0.05 s, speech_time >= MIN_SPEECH is true. And it stays 
true on each following window, because speech_time keeps growing (0.064, 0.096, 0.128, ...). 
If the condition were only self.speech_time >= MIN_SPEECH, every window of the sentence would 
return "start". You'd get about 31 START events per second.

not self.speaking fixes that. The first time the condition passes, the code sets 
self.speaking = True. On the next window not self.speaking is False, so the whole condition fails 
and nothing fires.

'''




#? Why not make it(get_probabilities) async def when eventually we will use , to_thread to execute it , ?? 

'''
Because async def doesn't move work to another thread. An async function still runs on the event loop's 
own thread, and it only gives control back at an await. Silero's model call is plain CPU work with nothing 
to await, so inside an async def it would block the whole loop just the same. The thread is what frees 
the loop, and to_thread provides that.

'''

#! Doubt : eventually only one thread works  at a time right ,  so isnt it the case , that what a thread would do , a couroutene would have done same ??

'''
Not quite. "Only one thread works at a time" is true for pure Python code, because the GIL (a lock that lets 
only one thread run Python code at once) allows just one thread to execute Python at a time. But the 
model call isn't Python. PyTorch and ONNX Runtime release the GIL while they run their C++ code, as far 
as I know, so a worker thread really does run in parallel on another CPU core while the event loop 
keeps going.


The difference between a coroutine and a thread:
1.Coroutine: runs on the one event-loop thread and gives up control only at an await. It's great for waiting 
(sockets, Deepgram, Cerebras), where nothing is computing. It can't speed up CPU work, and it can't be 
interrupted partway through it.
2.Thread: the OS runs it independently, so heavy compute runs beside the loop and doesn't stall it.

'''
#The rule is that a function is async only if it awaits something: I/O, a queue, a sleep, or a to_thread call. Pure CPU logic stays sync.



#? What exactly is smoothing and why its even needed  , what value does this bring to the table ??


'''

What it is: the model gives a raw probability every 32 ms, and raw values are jumpy. 
Smoothing replaces each one with a blend of itself and the recent past 
#!(35% old, 65% new). 
It's a running average that leans toward the newest value.

#?Why the raw values jump ?

1.Dips inside real speech. In a word like "party", the "p" and "t" are tiny silences, and the model 
  may score 0.2 for one window although the user is still talking.
2.Spikes in noise. A click, a cough or a keyboard tap can score 0.9 for one window.


Two cases with the numbers (my own calculation from LiveKit's formula):

Case	               Raw	                Smoothed
Dip in speech	0.9, 0.9, 0.2, 0.9	    0.9, 0.9, 0.45, 0.74
Noise spike	     0.1, 0.1, 0.9, 0.1	     0.1, 0.1, 0.62, 0.28


The dip only falls to 0.45, so it stays above the 0.35 "stay speaking" bar. The spike jumps to 0.62, 
which crosses 0.5, but the next window falls straight back to 0.28. A start needs 2 windows in a row, 
so the spike is rejected. Smoothing is light, and it works together with the thresholds and 
the start rule.

'''


# ? Why smoothed is  in reset(): 
# a new session shouldn't inherit the last user's smoothed value.
        
# Question : what does it mean by  new session , ?? here is it when a user joins and leaves and rejoins
#  or whenever a new user joins , thats ?? 
# Ans: "New session" here means a new stretch of continuous audio,not strictly a new user 

#! Give it a read ?!

'''
1.A new user joins: you create a new VADStream, so everything is fresh from __init__. reset() isn't needed.

2.The same user leaves and rejoins: if you create a new object per handle_conversation, it's fresh again.
Reset only matters if you reuse the old object.

3.The STT reconnect loop (the case that matters in Ava): your audio_stream is recreated on each loop pass, 
so there's a gap in the audio. If the VAD object lives outside that loop, call reset() at the top of each
pass. Otherwise it keeps leftover bytes, model memory and a smoothed value that describe audio that is no 
longer adjacent to what's arriving.

4.Any hard break: LiveKit's flush() is exactly this. It's used when an out-of-band signal arrives, like 
an STT end-of-speech.

'''
#!The rule is that if the audio before and after a point isn't continuous, reset there.

#? Explore it in depth what does below two lines mean ,?? 
# For Ava, I'd create one VADStream per handle_conversation, before the reconnect loop, 
# and call reset() at the start of each loop pass.


#!----------------------------------------------------test---------------------------------


# test1
# v = VADStream()
# print(v.get_probabilities(bytes(1024 * 3)))      # 3 windows of silence
# print(v.get_probabilities(bytes(500)))           # not a full window yet
# print(v.get_probabilities(bytes(524)))           # 500 + 524 = 1024, so exactly 1 window


# test2
# v = VADStream()
# raw = [0.1, 0.2, 0.6, 0.9, 0.8, 0.4, 0.8, 0.9, 0.3, 0.2, 0.1]
# print([round(v.smooth(p), 2) for p in raw])


# test3
# v = VADStream()
# print([v.is_speech(p) for p in (0.49, 0.50, 0.36)])    # not speaking
# v.speaking = True
# print([v.is_speech(p) for p in (0.49, 0.36, 0.34)])    # speaking


# v = VADStream()
# seq = [False]*3 + [True]*5 + [False]*18
# print([(i, e) for i, s in enumerate(seq, 1) if (e := v.detect_transition(s))])

# v = VADStream()
# seq = [True]*4 + [False]*10 + [True]*4 + [False]*18
# print([(i, e) for i, s in enumerate(seq, 1) if (e := v.detect_transition(s))])