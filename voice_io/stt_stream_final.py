from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

#! When to use class based approach , and when to use normal function based approch , ?? 

# One-line rule: use a class when several functions share state that belongs to one "thing" and you may need 
# multiple independent copies of it. Use plain functions when there's no state to carry between calls.

# Your STT fits: ctx, connection, and on_turn_end are state, send_audio, stt_close, and the rest all use it, 
# and you need one copy per user.

SAMPLE_RATE=16000 # We are defining it outside the class because its a a variable that stays constant throughout
# import asyncio
class STTConnection:
    def __init__(self):
        self.ctx=None
        self.connection=None
        self.on_turn_end=None
        # self.SAMPLE_RATE=16000

    async def stt_connect(self):
        client =AsyncDeepgramClient()
        self.ctx=client.listen.v2.connect(model="flux-general-en",
                                                encoding="linear16",
                                                sample_rate=str(SAMPLE_RATE),
                                                )
        self.connection=await self.ctx.__aenter__()

    async def send_audio(self,data:bytes):
        await self.connection.send_media(data)

    def stt_on_turn_end(self,callback):
        self.on_turn_end=callback 

    async def on_message(self,message):
        # print("DEBUG: raw message type:", getattr(message, "type", None), getattr(message, "event", None))
        # print("on_message fired:", getattr(message, "type", None), getattr(message, "event", None))
        if message.type=="TurnInfo" and message.transcript:
            if message.event=="Update":
                print("You:", message.transcript)
            elif message.event=="EndOfTurn":
                if self.on_turn_end:
                    await self.on_turn_end(message.transcript)

    #! This function receives the transcripts Deepgram sends back for what the user said.
    async def stt_register_listener(self):
        '''
        It does two things:
        i) registers the callback (on_message)
        ii) keeps reading incoming messages and calls on_message for each one.

        '''
        # The SDK catches any exception raised inside on_message and emits it as ERROR,
        # then stops listening. Without this handler that failure is completely silent.
        self.connection.on(EventType.ERROR, lambda exc: print("STT listener error:", repr(exc)))
        self.connection.on(EventType.MESSAGE,self.on_message)
        await self.connection.start_listening()

    async def stt_close(self):
        if self.connection: # Guard :
            # we are useing this if self.ctx as a safeguard , in order to avoid error
            await self.ctx.__aexit__(None,None,None)




#! Notes: why stt_close needs a guard ? 
'''
stt_connect sets two things, in this order:

1. self.ctx = client.listen.v2.connect(...) only prepares the connection. The socket is not open yet.
2. self.connection = await self.ctx.__aenter__() actually opens the socket


=>So there are three possible situations when stt_close runs:

Situation	                  self.ctx	  self.connection
stt_connect never ran	        None	   None
stt_connect failed at step 2	set	       None
stt_connect worked	            set	       set

#?Problem: stt_close calls self.ctx.__aexit__(...).

In row 1, ctx is None, so calling __aexit__ on it crashes.
In row 2, ctx exists but the socket never opened, so there is nothing valid to close, and this can crash too.

#? Fix: check self.connection, because it is only set when the socket really opened (row 3 only).


'''




#? Why not self.client = AsyncDeepgramClient() ?? why we didnt use self here,?? 

'''
Use self. only for state that must outlive a single method call or be shared between methods. 
Everything else stays a plain local variable.

Ask of each variable: "Will another method (or a later call) need this?"

=> Yes → self.x. Example: self.connection, because send_audio and close use it after connect has finished.
=> No → local. Example: client, since it's only used inside connect and then forgotten.

'''
















#! The general rule, which you can apply broadly now: a function should be async def only if it needs to await something inside it

