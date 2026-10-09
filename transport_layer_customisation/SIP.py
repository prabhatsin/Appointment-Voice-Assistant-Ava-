

#?1.What is SIP ,and what is it used for ??
#! Note : Explore it later for the Phone call part , ...

'''
SIP manages the call itself—it establishes the connection, negotiates communication parameters, and handles call termination.
Common use cases:
- Internet phone calls (VoIP).
- Business phone systems and call centers.
- Connecting AI voice agents to real telephone numbers.
- Transferring calls between a bot and a human agent.
- Starting and ending video or audio sessions.

'''


#?2. How does SIP work?
'''

Imagine someone calls Ava's phone number.

            Caller
        Mobile / telephone

                ↓

    Telephony provider / SIP trunk
        Routes the call to Ava

                ↓

            SIP signaling
        INVITE → 200 OK → ACK

                ↓

            Ava Voice Agent
            STT → LLM → TTS



Once the call is established, audio typically flows using RTP (Real-time Transport Protocol) or SRTP 
(Secure RTP). SIP handles signaling; it generally does not carry the actual audio.

'''
#? 3. The important SIP messages

'''
Message	       Meaning

INVITE   	  Requests to start a call.
100 Trying	  The request is being processed.
180 Ringing	  The destination is ringing.
200 OK	      The call request has been accepted.
ACK	          Confirms receipt of the successful response.
BYE	          Ends an established call.
CANCEL	      Cancels a call attempt that has not yet been established.

'''

#?A simplified call setup looks like this:
'''
Caller                 Ava / SIP server
  |                           |
  |-------- INVITE ---------->|
  |<------- 100 Trying -------|
  |<------- 180 Ringing ------|
  |<------- 200 OK -----------|
  |---------- ACK ----------->|
  |                           |
  |======= Audio (RTP) =======|
  |                           |
  |----------- BYE ---------->|
  |<---------- 200 OK --------|

'''

#?4. SIP vs WebRTC vs WebSocket
'''
These technologies serve different roles.

#!Technology	          Main responsibility

SIP	                  Establishes and manages telephone calls.
WebRTC	              Enables real-time audio/video communication, especially in browsers and realtime applications.
WebSocket	          Provides a persistent, bidirectional connection for exchanging application messages or streaming data.
RTP/SRTP	          Carries real-time audio/video packets.

'''

#?5. How SIP fits into Ava ??

'''
#! If Ava currently accepts microphone audio through a browser, you may not need SIP at all.
If you want people to call Ava using an ordinary phone number, SIP becomes important:

'''

'''
Phone call
    ↓
Phone number / telephony provider
    ↓
SIP trunk
    ↓
Ava's telephony integration
    ↓
Audio stream
    ↓
VAD → STT → LLM → TTS
    ↓
Audio back to caller

'''

