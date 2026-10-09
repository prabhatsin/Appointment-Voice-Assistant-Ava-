

#! Level 1 — Custom transport abstraction

'''
Build:
Client
 ↓
WebSocket signaling
 ↓
WebRTC library
 ↓
Audio frames
 ↓
Ava

while using something like aiortc underneath.
'''


#! Level 2 — Your own voice transport server

'''
Build:
Signaling server
+
session management
+
WebRTC
+
audio tracks
+
RTP handling
+
jitter handling
+
reconnection
+
backpressure
+
metrics

using existing protocol implementations.

'''