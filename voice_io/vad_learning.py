

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


