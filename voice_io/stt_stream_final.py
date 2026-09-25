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
connection=None
on_turn_end=None
async def stt_connect():
    global connection # This telle the function the connection we are refererring to is the one defined outside the function , not creating a local variable , here 

    client =AsyncDeepgramClient()
    #note this is not wrapped in async with this time. We're manually managing the connection instead of using the context-manager block,
    connection=await client.listen.v2.connect(model="flux-general-en",
                                              encoding="linear16",
                                              sample_rate=str(SAMPLE_RATE),
                                              ).__aenter__()
    # we will be using __aenter__() and .__aexit__() manually now 


async def send_audio(data:bytes):
    await connection.send_media(data)
    # send_media is the primary function used to forward raw audio payloads over an active WebSocket connection to Deepgram's servers.

#! Question Why two seperate function one notv simply on e, 

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
    if message.type=="TurnInfo" and message.event=="EndofTurn" and message.transcript:
        if message.event=="Update":
            print("Live:",message.transcript)
        elif message.event=="EndofTurn":
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


# TODO: Kal aate hi startwriting iske aage ka , and , how are all above defined functions related to each other 
# how / are they ried together 