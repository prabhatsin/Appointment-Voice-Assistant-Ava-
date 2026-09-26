from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
SAMPLE_RATE=16000


# TODO: convert this into class based , 
'''

With a class: each DeepgramSTT() instance has its own self.connection, self._on_turn_end — completely 
independent of any other instance. If you create one per participant, they don't interfere with each other 
at all, automatically, with zero extra effort.

The concrete advantage, stated plainly: a class gives you multiple independent copies of the same behavior
+ state, for free, just by calling DeepgramSTT() again. Plain functions with global variables only give 
you one shared copy — which breaks the moment you need more than one at a time.

'''
ctx=None
connection=None
on_turn_end=None
async def stt_connect():
    global ctx,connection # This telle the function the connection we are refererring to is the one defined outside the function , not creating a local variable , here 

    client =AsyncDeepgramClient()
    #note this is not wrapped in async with this time. We're manually managing the connection instead of using the context-manager block,
    ctx=client.listen.v2.connect(model="flux-general-en",
                                              encoding="linear16",
                                              sample_rate=str(SAMPLE_RATE),
                                              )
    connection=await ctx.__aenter__()
    # we will be using __aenter__() and .__aexit__() manually now 

#! Learning : Important ,

'''
always do ,ctx=client.listen.v2.connect()
Not , 
connection=client.listen.v2.connect( ).__aenter__()

-> Because   client.listen.v2.connect(...)   creates a context-manager object   and it should be assigned 
to a variable so that python does not garbage collect it ,                                 
                                         
'''


#sends one chunk of raw audio bytes over the already-open connection.
#Called repeatedly, once per audio chunk, from outside this file.
async def send_audio(data:bytes):
    await connection.send_media(data)
    # send_media is the primary function used to forward raw audio payloads over an active WebSocket connection to Deepgram's servers.

#! Question Why two seperate function (stt_connect and send_audio) why  simply one, 

'''
Separate function so :
-> stt_connect() (called once, at startup) and  

->stt_send_audio() (called repeatedly, every audio chunk) can each be called independently, 
whenever needed — not bundled into one call that would try todo both at once.

'''

def stt_on_turn_end(callback):
    '''
    Its entire purpose is letting some other file "hand in" a function to be stored here,
    for _on_message to call later.
    '''
    global on_turn_end 
    on_turn_end=callback 
    # take the module-level variable and set it to whatever function (in our case named handler)

async def on_message(message):
    '''
    1.runs automatically every time Deepgram sends back a transcript update
    2.when that update is the finalized end-of-turn text — passes it along to whatever function was registered 
    via stt_on_turn_end.
    '''

    # message is the object Deepgram sends back over the connection — has several fields on it (attributes),
    if message.type=="TurnInfo" and message.transcript:
        if message.event=="Update":
            print("Live:",message.transcript)
        elif message.event=="EndOfTurn":
            if on_turn_end:
                await on_turn_end(message.transcript)


'''
->message.type — tells you what kind of message this is overall. Deepgram sends different message types 
(Connected, TurnInfo, maybe others). We only care about "TurnInfo" ones — messages that carry actual 
speech/transcript info, not connection-status messages.

->message.event tells you which "stage" each individual message represents — specifically, whether it's 
  still growing/guessing, or whether it's the final, settled answer.

  "Update" — a work-in-progress message
  "EndOfTurn" — Deepgram's signal that says "I'm confident the person has finished their turn/sentence — here's the final, settled transcript, this won't change anymore."

->nessage.transcript - the actual text itself
the actual text itself. This check (and message.transcript) is just a safety check for "make sure it's not 
empty" — an EndOfTurn event could theoretically fire with empty text (e.g., background noise falsely 
detected as a turn), and you don't want to trigger a response to nothing.


'''
async def stt_register_listener():
    '''
    #! Summary:
    Registers on_message as the callback for incoming messages, then starts actively listening for them 
    (forever, until the connection closes).
    # Listening here means : Continuously watching the network connection for incoming messages, reacting the instant one arrives.
    '''

    # Event based trigger
    connection.on(EventType.MESSAGE,on_message)
    # whenever a MESSAGE event happens on this connection, call on_message
    await connection.start_listening()


'''
->start_listening() is the function inside Deepgram's SDK that actually reads incoming data off the 
  WebSocket connection, continuously, for as long as the connection stays open.

  
-->Every time a full message arrives from Deepgram's server (an Update, an EndOfTurn, etc.), it takes that 
  raw incoming data, parses it into a proper message object, and calls whatever function you registered 
  with .on(EventType.MESSAGE, ...) — in your case, on_message.

'''

#! Question message.event and EventType.MESSAGE ?? 
'''
# message.event — this is a field inside the actual message content, specific to TurnInfo messages.
#It's Deepgram telling you, within the content of one specific transcript-related message, whether that message is "Update" (in-progress) or "EndOfTurn" (final)

=>EventType.MESSAGE — this is about the connection itself,

=>EventType.MESSAGE is a constant used to register a callback function that handles incoming messages or real-time transcription data from a Deepgram WebSocket connection



#?Codewise:

#? step1
What connection.on(EventType.MESSAGE, on_message) does internally (conceptually, not the literal Deepgram source):

Somewhere inside Deepgram's SDK, the connection object has something like an internal dictionary, storing callbacks keyed by event type:

# inside Deepgram's own SDK code (not yours)
class SomeConnectionClass:
    def __init__(self):
        self._callbacks = {}   # e.g. {EventType.MESSAGE: [on_message]}

    def on(self, event_type, callback):
        self._callbacks[event_type] = callback   # just stores it

# Conceptually whats happening is ,
When you call connection.on(EventType.MESSAGE, on_message), all that's happening, concretely, is: your 
on_message function gets stored inside that internal dictionary, under the key EventType.MESSAGE. 
Nothing runs yet — it's pure storage/registration, exactly like room.on(...) was.


#? step2 

Now, separately, inside start_listening() (also SDK code, not yours), there's a loop reading raw data off the actual network socket. Roughly:


# inside Deepgram's SDK
async def start_listening(self):
    while connection_is_open:
        raw_data = await read_from_websocket()          # wait for real network data
        parsed_message = parse_into_message_object(raw_data)   # turn bytes into a usable object
        callback = self._callbacks.get(EventType.MESSAGE)      # look up what you registered
        if callback:
            await callback(parsed_message)                      # call YOUR on_message with it

#? In Simple words:
So putting it together: connection.on(...) is step 1 — just filing your function away in a lookup table. 
start_listening() is step 2 — the actual loop that reads real bytes off the network, turns them into a 
proper message object, looks up what's stored under EventType.MESSAGE in that internal table, and calls 
it — which is your on_message, receiving that freshly parsed message.


'''

async def stt_close():
    await ctx.__aexit__(None,None,None)

# async def __aexit__(self, exc_type, exc_value, traceback):

'''
These three parameters exist because async with (and its plain with cousin) is designed to handle errors 
that happen inside the block, not just clean exits. If something crashes inside an async with block, 
Python automatically calls __aexit__ and hands it information about that crash:

->exc_type — what kind of error occurred (e.g., ValueError, ConnectionError) — or None if nothing went wrong
->exc_value — the actual error object/message itself — or None if nothing went wrong
->traceback — the full stack trace of where the error happened — or None if nothing went wrong
'''

#In short: those three Nones are just Python's way of saying "everything's fine, I'm closing this on purpose, not because of an error"