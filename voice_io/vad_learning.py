
#? This file used to answer "is this chunk speech?" with detect_speech(). Removed: barge-in now uses
#? the per-connection VADStream in voice_io/vad_session.py. The notes below on buffering still apply there.






#? Don't think: Silero = VAD !!



'''

                 ┌─────────────────┐
Audio frames ───►│      VAD        │
                 │                 │
                 │ Silero          │
                 │ WebRTC          │
                 │ Cobra           │
                 │ custom/RMS      │
                 └────────┬────────┘
                          │
                   speech probability
                          │
                          ▼
                 VAD STATE MACHINE
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
       START SPEECH               END SPEECH
             │                         │
             └──────────┬──────────────┘
                        ▼
                 TURN DETECTION
                        │
                        ▼
                       STT

'''

#! Learn State machine implementation , in chat "EC2 Vite UI Access",







# how many milliseconds of data if 512 in samples , 
'''
16000 sample -- 1 sec or 1000 miliseconds

512 == (1/16 ) * 512 =32 ms 

'''



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
'''vad_stream
=> Audio is a stream of samples, and the sample rate says how many arrive per second. 
=> Bytes and milliseconds are two ways of measuring the same amount of audio.

#? How to conver this in millisecond ,?
We know 16000 sample is 1 seconds
so 512 samples= 512/16000 =32 ms of data 
160 sample= 160/16000=10ms of data

#? How to convert into bytes ?
since in deepgram settings we mentioned depth of 16 bits which is 2 bytes per sample 

'''



