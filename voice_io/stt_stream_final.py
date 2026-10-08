from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
import time
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
        self.connected=False # a yes/no flag saying whether the connection is alive right now.
        self._running=False 
        #a flag meaning "keep the listener alive". It's on while the conversation runs and off 
        # when you close it, so the reconnect loop knows when to stop.
        # internal to this class 


    async def stt_connect(self):
        client =AsyncDeepgramClient()
        self.ctx=client.listen.v2.connect(model="flux-general-en",
                                                encoding="linear16",
                                                sample_rate=str(SAMPLE_RATE),
                                                )
        self.connection=await self.ctx.__aenter__()
        self.connected=True

    async def send_audio(self,data:bytes):
        if not self.connected:
            return # drop audio while reconnecting 
        try:
            await self.connection.send_media(data)
        except Exception:
            self.connected=False # listener loop will reconnect



    def stt_on_turn_end(self,callback):
        self.on_turn_end=callback 
    
    
    async def on_message(self,message):
        # print("DEBUG: raw message type:", getattr(message, "type", None), getattr(message, "event", None))
        # print("on_message fired:", getattr(message, "type", None), getattr(message, "event", None))
        if message.type=="TurnInfo" and message.transcript:
            if message.event=="Update":
                # print("You:", message.transcript)
                pass
                
            elif message.event=="EndOfTurn":
                # print(f"[{time.perf_counter():.3f}] EndofTurn",id(self) % 10000, getattr(message, "turn_index", None), message.transcript)
                print(f"[STT ] turn ended: {message.transcript}")
                if self.on_turn_end:
                    await self.on_turn_end(message.transcript)

    #! This function receives the transcripts Deepgram sends back for what the user said.
    async def stt_register_listener(self):
        print("listener started")
        '''
        It does two things:
        i) registers the callback (on_message)
        ii) keeps reading incoming messages and calls on_message for each one.

        '''
        self._running=True
        while self._running:
            try:
                self.connection.on(EventType.ERROR, lambda exc: print("STT listener error:", repr(exc)))
                # The SDK catches any exception raised inside on_message and emits it as ERROR,
                # then stops listening. Without this handler that failure is completely silent.
                self.connection.on(EventType.MESSAGE,self.on_message)
                await self.connection.start_listening()
            except Exception as e:
                print("STT listener error:",repr(e))
            #_running becomes False only when something else sets it, and that something is stt_close():
            if not self._running:
                break
            await self._reconnect()


    #! So there are two situations after start_listening() stops:
    '''
    So there are two situations after start_listening() stops:

    1.Connection dropped: _running is still True. The if not self._running check passes through,
    _reconnect() runs, and the loop starts over.

    2.You closed it: stt_close() set _running = False. start_listening() also stops because the 
    socket closed, so the code reaches if not self._running: break, which exits the loop instead of
    reconnecting.

    '''

    async def _reconnect(self):
        self.connected = False
        # marks the connection as down, so send_audio stops sending into a dead socket.
        for delay in (0.2, 0.5, 1, 2, 3):
            #if the conversation was closed in the meantime, don't reconnect.
            if not self._running:
                
                return
            try:
                await self.ctx.__aexit__(None, None, None) # cleans up the old, dead connection
            except Exception:
                pass
            try:
                await self.stt_connect() # opens a new connection and sets connected = True
                print("STT reconnected")
                return
            except Exception as e:
                print("STT reconnect failed:", repr(e))
                await asyncio.sleep(delay)
        raise RuntimeError("STT reconnect failed repeatedly")

    # async def send_keep_alive(self):
    #     '''
    #     It sends a {"type": "KeepAlive"} JSON message over the WebSocket to Deepgram, which 
    #     tells Deepgram "this connection is still active, don't close it."
    #     '''
    #     if self.connection:
    #         await self.connection._send({"type":"KeepAlive"})

    async def stt_close(self):
        self._running=False
        self.connected=False
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

