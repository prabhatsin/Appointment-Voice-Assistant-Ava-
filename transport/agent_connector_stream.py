import asyncio
import os
import logging
from dotenv import load_dotenv
from livekit import rtc
from transport.token_server import generate_token, ROOM_NAME
from transport.livekit_session_stream import register_audio_handlers,setup_audio_output
from transport.livekit_session_stream import conversation_history

from voice_io.tts_stream import PersistentTTS

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)

#!  Summary of this Script :
'''
connect to the LiveKit room → set up TTS and audio output → register handlers that will react to future 
events (participants joining, tracks appearing) → then sit and do nothing itself forever, letting those 
registered handlers drive everything from here on.
'''



async def main():

    # creates a plain Python object of the Room class 
    room = rtc.Room()  # Room class from LiveKit's rtc module.
    # room is your LiveKit Room object:

    @room.on("participant_connected")
    # LiveKit provides an .on() method that is used to say:
    #  "When this event happens, call this function."
    # That particular event is "participant_connected" here 
    # and the function be called is "on_participant_connected"
    # @room.on means roughly:"Give me a decorator that registers a function for "the participant_connected" event."

    def on_participant_connected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant joined: {participant.identity}")
        # conversation_history.clear()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logging.info(f"Participant left: {participant.identity}")


    token = generate_token(ROOM_NAME, "ava-agent")

    #room.connect(...) is async(a coroutine) — it has to actually talk to LiveKit's servers over the network
    #to establish a connection, which takes real time (unpredictable, maybe 100ms, maybe more)
    await room.connect(os.environ["LIVEKIT_URL"], token)
    # await here means: "pause this function (This function means "async def main()") right here, let other things run if needed, and resume exactly 
    # at this line once the connection is actually established."
    #Without await, you'd move on to the next line before the connection was even ready — and everything 
    # after it (setting up audio, registering handlers) would likely fail because the room isn't connected
    #  yet.
    logging.info(f"Ava connected to room: {room.name}")


    tts = PersistentTTS() #! explore this class PersistantTTS  in depth 
    # Creates the PersistentTTS object (just sets up empty state — no network yet, look at __init__ in 
    # that class, it's all instant assignments).

    await tts.connect()
    # Actual network connection to Deepgram's TTS server happens

    audio_source = await setup_audio_output(room)
    # So in one line: this line creates Ava's "voice output pipe" and publishes it to the room, so other 
    # participants can actually hear whatever gets pushed into it later.


    register_audio_handlers(room, audio_source,tts)
    # All it does is register another event handler (@room.on("track_subscribed")) — same pattern as the 
    # participant handlers above. It doesn't do the work itself; it just tells LiveKit "when a track shows
    # up, call this function" — the actual async work happens later, inside handle_audio_track, when that 
    # event actually fires.
    await asyncio.Event().wait()

    '''

    #! I understood whatever is written below but didnt felt it ,because i dont know internals of async await in python
    #! Explore Later 
    This is the most important line to understand, and it's a genuine async concept, not just "waiting for 
    a network call." asyncio.Event() creates a signal/flag object that starts as "not set." .wait() pauses 
    here forever — until something calls .set() on that exact event object, which never happens in this code.
    This is a deliberate, common pattern: "keep this program alive indefinitely, doing nothing itself, 
    while all the real work happens in the background via event handlers and tasks that were registered 
    earlier." Without this line, main() would finish immediately after register_audio_handlers, and — since 
    there's nothing left to awaitPython would consider the coroutine done and the program would exit, 
    closing the room connection before any real conversation could happen.

    '''


if __name__ == "__main__":
    asyncio.run(main()) #? The Bridge between sync and async world

#! Entry Point of the Event loop
# asyncio.run(...) is the standard entry point that starts the event loop and runs your top-level async 
# function inside it.
# This is the one place in a typical asyncio program where you're not inside an async def — it's the bridge 
# between plain, synchronous Python startup and the async world everything else lives in.







#? Learning 1:

#! Question: What is an event handler , ?? 
# "Event handler" is just a name/label for: a function that doesn't get called directly by your own code, 
# but instead gets called automatically by something else (here, room) whenever a specific event happens.
# In our case  the "function on_participant_connected " and others are the event handler"

#! 1. How does room actually know a participant connected??

'''

->You're right that "participant_connected" is just a plain string, and the function below it looks like an 
ordinary function. The magic isn't in your code — it's inside rtc.Room's own internal implementation 
(code you didn't write, living inside the livekit library).

Here's the mechanism, in plain terms:

i) room.connect(...) (the await line from before) opens a real network connection to LiveKit's server.

ii)Internally, Room is constantly listening on that connection for messages from the server — this is 
running in the background, hidden from you, likely its own async loop reading incoming network data continuously.

iii) When LiveKit's server detects a new participant joined, it sends a message down that connection saying 
"a participant just connected."

iv) Room's internal code receives that message, and — here's the key part — it keeps an internal list/dictionary of 
callbacks you've registered per event name. When it sees a "participant_connected" type message arrive, it 
looks up "who registered a callback for 'participant_connected'?" and calls those functions itself, passing
in the participant object


-->What @room.on("participant_connected") actually does: it's just registering your function into that 
internal list, under the key "participant_connected". Think of it like:

room._event_callbacks["participant_connected"].append(on_participant_connected)

(not the literal real code, but that's the concept). You're not calling your function — you're handing it 
to room, and room calls it later, whenever it internally detects that specific event happened. This is 
called the observer pattern or pub/sub (publish/subscribe) — extremely common in any library that reacts 
to real-time events (UI libraries, game engines, network libraries all do this).

'''



#! Question , how is a string "participant_connected", an event ?? 

# The important part is that LiveKit has given that string a special meaning inside room.on().
# event name / identifier
'''
room.on() is a normal Python method
LiveKit could internally have something conceptually like:

def on(self, event_name):
    ...

So when you write:
room.on("participant_connected")
Python simply passes the string: "participant_connected" to the method.

LiveKit's code then says, conceptually:
if event_name == "participant_connected":
    # treat this as the participant-connected event

So the string itself is not an event.
It's an identifier/name for an event.

'''

#! 2. participant: rtc.RemoteParticipant  ?? 

'''
=>This is a type hint, not a class definition or anything active — it's just documentation that Python 
(mostly) doesn't enforce at runtime. It's saying: "the participant parameter that gets passed into this 
function will be an object of type rtc.RemoteParticipant."

=>RemoteParticipant is a class defined inside the livekit library, representing "someone else connected to 
this room" (as opposed to LocalParticipant, which would represent your agent/Ava itself). When LiveKit calls 
your on_participant_connected function, it passes in an actual RemoteParticipant object — which is why you 
can do participant.identity inside the function (that's an attribute defined on that class).

=> Type hints like this don't do anything by themselves — they're purely there to help you (and tools like 
your editor) know what kind of object to expect, so you get autocomplete and can catch mistakes. If you 
removed : rtc.RemoteParticipant entirely, the code would run exactly the same.

'''


#! Summary of agent_connector_stream.py:


'''
This is your entry point / setup script — it doesn't handle any actual conversation logic itself. Its whole job, in order:

1.Create a Room object and register two event handlers (participant_connected, participant_disconnected) — 
these just log joins/leaves and reset conversation history on join

2.await room.connect(...) — actually connect to LiveKit's server (real network wait)

3.Create and connect PersistentTTS — sets up the Deepgram TTS WebSocket connection (real network wait)

4.await setup_audio_output(room) — creates Ava's outgoing audio pipe and publishes it to the room 
(real network wait)

5.register_audio_handlers(...) — registers a track_subscribed handler that will, in the future, kick off 
the whole STT→LLM→TTS pipeline whenever a participant's mic audio arrives (no work happens yet — just a 
registration)

6.await asyncio.Event().wait() — pause forever, keeping the event loop (and everything running inside it) 
alive indefinitely



In one sentence: this file connects to the room, wires up the voice output pipe, and arms the trigger for 
incoming audio — then goes to sleep forever, letting event handlers drive everything else.

'''




















