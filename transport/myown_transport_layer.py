
#? Think of the transport layer as:


'''
                YOUR TRANSPORT LAYER
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
   Signaling         Media Transport    Connection
       │                 │                 │
 WebSocket/HTTP       WebRTC/RTP        ICE/STUN/TURN
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                    Audio Frames
                         │
              ┌──────────┴──────────┐
              │                     │
             VAD                   STT
'''





#? Journey of Sound data:


'''

                    AUDIO

                      │
              Physical sound
                      │
                      ▼
                 Microphone
                      │
                      ▼
              Analog waveform
                      │
                      ▼
                    ADC
                      │
                      ▼
              ┌──────────────┐
              │     PCM      │
              │              │
              │ samples      │
              │              │
              └──────────────┘
                      │
            ┌─────────┼─────────┐
            │         │         │
            ▼         ▼         ▼
        Sample      Bit       Channels
         Rate       Depth
        16 kHz      16-bit     Mono
            │         │         │
            └─────────┼─────────┘
                      │
                      ▼
              PCM byte stream
                      │
              ┌───────┴────────┐
              │                │
          process locally    encode
              │                │
              ▼                ▼
             STT              Opus


'''