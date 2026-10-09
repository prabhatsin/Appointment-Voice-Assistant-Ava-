
#? BIGGER PICTURE:
#Think of Ava as having two separate flows:

#1. Connection setup: browsers exchange connection information and negotiate how media will work.

#2. Audio processing: once connected, audio flows through your realtime voice pipeline.

'''
A. Connection setup — before audio flows


                Browser A
            Creates SDP offer

                    ↓

    SDP offer sent via signaling server

                    ↓

            Signaling server
    Forwards messages; doesn't need to process audio

                    ↓

    Browser B receives offer and returns SDP answer

                    ↓

                Browser B
    Accepts compatible media parameters



#NOTE: Meanwhile, ICE candidates are exchanged to help the browsers find a usable network path. WebRTC then establishes the secure media connection.
'''



'''
B. Audio flow — after connection

            Browser A microphone

                    ↓

            WebRTC media transport
            Encrypted audio packets

                    ↓

            Browser B speaker

'''

#--------------------------------------------------------------------------------------------------------

#TODO: STEP1
#TODO The target is how does audio get send to server from the browser , ?? 


'''
Voice communication

1.WebRTC

2.SFUs

3.Pion

4.Livekit

5.Daily.co/Twilio

'''


'''

WebRTC (Web Real-Time Communication) is a protocol .that lets browsers and apps exchange audio, video, and
data directly with each other — in real time — without needing a plugin or a server to relay the actual media.

'''



#! Question: Is it really p2p? Can it be p2p? No server needed?

# Ans: No, a signalling server is needed for the peers to identify each other (get each others ips) 

#? Signaling Server ?? 
# New terms : SDP, codec, 

#! SDP (Session Description Protocol)
'''

SDP (Session Description Protocol) is a text-based format that describes the parameters of a multimedia 
communication session so that two endpoints can agree on how to communicate.

It describes things like:
- Media: Audio, video, or both.
- Codecs: Supported formats, such as Opus for audio.
- Transport information: Network addresses and ports, when included in the description.
- Security: Information used to establish encrypted media connections, such as DTLS fingerprints.
- Timing and direction: Whether media can be sent, received, or both

=>#NOTE: SDP does not transport your audio. It describes how the audio session should work.

'''

# What exactly does SDP do ???  
'''

Suppose Browser A wants to send audio to Browser B. Before they communicate, they need to agree on how that
audio will be transmitted.

SDP describes information such as:
- Which codecs they can use, such as Opus.
- Media capabilities and directions, such as send/receive.
- ICE credentials used during connectivity establishment.
- DTLS fingerprint information used to authenticate the secure connection.

=> NOTE:The browsers exchange this information through your signaling channel, commonly a WebSocket connection 
to your backend.

'''



'''
A codec is a hardware device or computer program that encodes(Compression) and decodes(Decompression) data streams,
particularly digital audio and video.

'''

