
#! Step 1: Networking fundamentals
'''
First, understand these four concepts:
1. IP address — identifies a device or network interface.
2. Port — identifies a particular service or application endpoint on a device.
3. Client-server model — how two applications communicate.

4. Packets — how data travels across a network.

'''

#? Packets


'''
A network packet is a small, formatted unit of data created by breaking down a larger message so it can 
travel efficiently across a computer network


#!Structure of a Packet

A standard network packet contains three main parts:

1: Header: Control information at the start that tells the network where the packet came from (sender IP), 
where it is going (receiver IP), how long it should live, and its sequence number(not needed in udp)

NOTE:Important correction: A sequence number is not a standard IPv4 header field. TCP has sequence numbers
in its own header, while UDP does not.

2:The actual chunk of user data (like a piece of a photo, text message, or video file) being transported.

    For example, in our Voice AI project, a UDP datagram's payload might contain RTP packets carrying encoded Opus audio.

3:Trailer (or Footer): Extra bits at the end that signal the finish line and use error-checking codes 
(like a checksum) to make sure the data did not get corrupted during the trip

'''

#!Step 1.2

# TCP - TRANSMISSION CONTROL PROTOCOL(reliable, ordered delivery)

'''
- Establishes a connection.
- Retransmits lost data.
- Delivers data in order.
- Can introduce delays when waiting for lost data.
'''


# UDP - USER DATAGRAM PROTOCOL (low overhead, no delivery guarantee)
'''
-Sends independent datagrams without establishing a connection.
-Doesn't guarantee delivery or ordering.
-Allows applications to prioritize timeliness over retransmission.

'''  

#?Why does this matter for Ava?

'''
TCP — signaling
Used for WebSocket messages such as SDP offers, answers, and connection-control events.


UDP — real-time media
WebRTC commonly transports audio using RTP over UDP, avoiding TCP's retransmission-related head-of-line blocking.

'''

NOTE:
#One important detail: UDP itself doesn't make audio fast or reliable. WebRTC adds mechanisms for congestion control, packet-loss handling, and timing.



#?Question : Understand why a voice application might prefer a late or missing audio packet over waiting for retransmission of an older packet. ?
#! Ans:


'''
=>Real-time voice applications prioritize **low latency over perfect delivery of every audio packet**.

=>Audio is time-sensitive. Suppose we're streaming audio in 20 ms frames, and one frame gets lost. If we 
wait for TCP to retransmit that frame, the missing audio can delay the delivery of subsequent bytes because
TCP guarantees ordered delivery. This is called **head-of-line blocking**.

=>In a voice conversation, that delay can be more damaging than losing a small piece of audio. By the time 
the missing frame arrives, its playback deadline may have already passed.

=>With UDP, subsequent datagrams can arrive independently of the missing one. The application can use 
packet-loss concealment to estimate the missing audio, skip it, or use other recovery techniques, allowing 
playback to continue with less delay.

=>Therefore, real-time voice systems often prefer a small, tolerable audio glitch over increased 
conversational latency. The goal is to keep the conversation responsive rather than guarantee perfect 
delivery of every frame.

'''

#? Three terms worth remembering

'''
- Head-of-line blocking: Later data is held up because earlier data is missing.
- Packet-loss concealment (PLC): Techniques that make missing audio less noticeable.
- Latency: The time between speaking and the listener hearing the audio.

'''

#! Question : Who does the Packet-loss concealment part ?? 

'''
Packet-loss concealment (PLC) is handled by the audio processing or media stack, not by UDP itself. 

=>In WebRTC, this is generally handled by the audio codec and media pipeline.
=>Opus includes packet-loss concealment capabilities, and the WebRTC audio pipeline coordinates decoding and playback.

#? Who does what when an audio packet is lost?

    Imagine you're speaking to a Voice AI agent through WebRTC.


                    1. UDP
    Transports datagrams; doesn't automatically retransmit lost ones.

                        ⬇️

                2. RTP / WebRTC media pipeline
    Tracks media packets and their sequence numbers; detects gaps and manages timing.

                        ⬇️

                3. Jitter buffer + audio decoder
    Handles packet timing and feeds audio to the decoder.

                        ⬇️

                4. Packet-loss concealment (PLC)
    The decoder estimates or synthesizes missing audio so playback

'''

#!NOTE: PLC does not recover the original packet. It attempts to make the missing audio less noticeable.


# -----------------------------------------------------------------------------------------------------

#! Step 2: RTP and RTCP (These protocols are central to understanding how WebRTC transports audio.)



#? Doubt : At which layer in  OSI(OSI (Open Systems Interconnection) Model) does the RTP fits??


'''
# RTP is commonly associated with the application layer in the OSI model,

# UDP (Layer 4): Provides datagram delivery without guaranteeing reliability, ordering, or retransmission.

# RTP: Adds real-time media information, such as sequence numbers to detect loss and timestamps to help with playback timing.

# It typically runs over UDP, which operates at Layer

'''


#? 1. RTP — Real-time Transport Protocol

# RTP carries the actual media data, typically over UDP

'''
        Microphone audio

                ⬇️

        Audio frames

                ⬇️


            RTP packets
        Sequence number · Timestamp · Payload

                ⬇️

            UDP → Network


Three important RTP fields:
- Sequence number: identifies packet order and helps detect missing packets.
- Timestamp: indicates the media sampling time, helping the receiver schedule playback.
- Payload: contains the encoded audio data, such as Opus.


'''

#?2. RTCP — RTP Control Protocol


'''
RTCP complements RTP by providing feedback about media delivery.
It can report:
- Packet loss
- Jitter
- Round-trip time (RTT)
- Sender and receiver statistics

This feedback helps WebRTC monitor connection quality and adapt media transmission.



How they work together ?

        RTP	                          RTCP
Carries media	                  Reports media-delivery statistics
Contains audio payload	          Contains control and feedback information
Supports timing and ordering	  Helps monitor connection quality


For Ava: RTP transports the audio; RTCP helps the WebRTC stack understand how well that audio 
is travelling.

'''

#--------------------------------------------------------------------------------


#! Step3 : SDP - Session Desciption Protocol


'''
# SDP describes how two endpoints want to communicate media in a WebRTC session. It describes the session; 
it does not carry the audio itself.

# For Ava, SDP helps the browser and Python WebRTC endpoint agree on how audio will be exchanged.

What does SDP describe?
- Media type: audio or video.
- Codec: e.g., Opus for audio.
- IP address and port information: connection-related details.
- Direction: send, receive, or both.
- Security parameters and other media attributes.

'''



# What exactly does SDP do ???  ( BROWSER TO BROWSER )
'''
Suppose Browser A wants to send audio to Browser B. Before they communicate, they need 
to agree on how that audio will be transmitted.

SDP describes information such as:
- Which codecs they can use, such as Opus.
- Media capabilities and directions, such as send/receive.
- ICE credentials used during connectivity establishment.
- DTLS fingerprint information used to authenticate the secure connection.

=> NOTE:The browsers exchange this information through your signaling channel, commonly a WebSocket connection 
to your backend.

'''

# FOR browser-to-agent architecture

'''
For your browser-to-agent architecture, the flow looks like this:

1. Browser creates an SDP offer. Its RTCPeerConnection describes its audio capabilities and proposed media session.

2. The offer reaches your signaling server. The server forwards it to the agent service, or to the component responsible for establishing the media session.

3. The agent endpoint creates an SDP answer. It accepts or negotiates the media configuration and returns the answer through signaling.

4. ICE candidates are exchanged. The endpoints discover and test possible network paths. ICE checks happen between the endpoints, not through the signaling server as a media relay.

5. The media connection becomes usable. DTLS establishes the secure transport, and SRTP protects the media.

6. Audio flows in both directions. Browser microphone audio goes to the agent; generated assistant audio comes back to the browser.

One important detail: the signaling server does not necessarily terminate the WebRTC connection.
It usually just helps the two endpoints exchange setup information.

'''

#?NOTE:Where does your Python agent fit ???

#Your agent needs a way to participate in WebRTC. There are two broad approaches:

'''

    Approach	                                What it means
  Use LiveKit                         LiveKit manages much of the real-time media infrastructure, while your 
                                    Python agent joins a room and processes audio.
(your current setup)

Build your own transport	        Your browser connects to your own WebRTC-capable agent endpoint, using 
                                    your own signaling and media infrastructure.

'''

#!NOTE:
#?NOTE:

'''
For the second approach, a Python signaling server alone is not enough. It can exchange SDP and ICE 
candidates, but it does not automatically receive or transmit WebRTC audio. You also need a WebRTC 
implementation on the agent side, such as Python's aiortc, or a lower-level media stack.

'''


#?THE GAP IN MENTAL MODEL
'''

There are three separate pieces:
- Signaling: How endpoints exchange SDP offers, answers, and ICE candidates.
- Media transport: How audio packets travel securely between endpoints.
- Agent pipeline: What your application does with the audio: VAD → STT → LLM → TTS.

'''

#?For Ava, think of it this way: 

# The browser is the user's endpoint, the agent service is the AI's endpoint, the signaling server helps 
# them establish the connection, and your STT/LLM/TTS pipeline runs on the agent side.


#!Step 4: ICE — Interactive Connectivity Establishment

'''
# ICE helps the browser and your Python WebRTC endpoint find a network path that actually works, even when 
they're behind NATs or firewalls.

It gathers possible connection addresses, called candidates, and tests connectivity between them.
For Ava, the flow is:
1. Browser gathers possible network addresses.
2. Python endpoint gathers its candidates.
3. They exchange candidates through signaling.
4. ICE performs connectivity checks to find a working path.

Key distinction: SDP describes the session; ICE finds a viable network path.

'''


#? So, for Ava:

'''
- FastAPI WebSocket: signaling.
- Python aiortc endpoint: WebRTC connection and audio I/O.
- VAD → STT → LLM → TTS: agent intelligence and audio processing.

'''

#! Step 5: STUN and TURN 

#These help ICE establish connectivity when your browser and Python server are on different networks.


#?1. STUN (Session Traversal Utilities for NAT.)
# Purpose: Discover the public-facing IP address and port that a device's NAT maps to.

'''
Example:
Browser: 192.168.1.10:50000
             ↓ NAT
Public mapping: 49.x.x.x:62000

STUN helps the browser discover that public mapping.
'''

