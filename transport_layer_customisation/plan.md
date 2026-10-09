

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

