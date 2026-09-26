from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType



SAMPLE_RATE=16000
ctx=None
connection=None
on_turn_end=None


# TODO: convert this into class based , 
async def stt_connect():
    global ctx,connection 
    client =AsyncDeepgramClient()
   
    ctx=client.listen.v2.connect(model="flux-general-en",
                                              encoding="linear16",
                                              sample_rate=str(SAMPLE_RATE),
                                              )
    connection=await ctx.__aenter__()


async def send_audio(data:bytes):
    await connection.send_media(data)
    

def stt_on_turn_end(callback):
    global on_turn_end 
    on_turn_end=callback 


async def on_message(message):
    if message.type=="TurnInfo" and message.transcript:
        if message.event=="Update":
            pass
            # print("Live:",message.transcript)
        elif message.event=="EndOfTurn":
            if on_turn_end:
                await on_turn_end(message.transcript)

async def stt_register_listener():
    connection.on(EventType.MESSAGE,on_message)
    await connection.start_listening()

async def stt_close():
    await ctx.__aexit__(None,None,None)



#! The general rule, which you can apply broadly now: a function should be async def only if it needs to await something inside it