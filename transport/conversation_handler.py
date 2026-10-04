import asyncio
from livekit import rtc
from voice_io.stt_stream_final import STTConnection
from voice_io.vad_stream import detect_speech
# from agent_core.main_loop_stream import get_agent_reply_stream
from agent_core_cerebras.main_loop import get_agent_reply_stream
from agent_core_cerebras.main_loop_groq import get_agent_reply_stream

import re
import time
SAMPLE_RATE=16000
TTS_SAMPLE_RATE=24000 
SPEECH_CONFIRM_CHUNKS = 3
conversation_history=[]

async def process_transcript(transcript:str,audio_source,tts,active_turn):
    # print("DEBUG: process_transcript started")
    if not transcript.strip():
        return
    my_turn_id = active_turn["turn_id"]
    async def handle_tts_audio(data:bytes):
        if active_turn["turn_id"]!=my_turn_id:
            return
        if data:
            active_turn["audio_started"]=True  # Ava is now audibly speaking, barge-in detection is armed
        if data and "t3" not in active_turn and "t2" in active_turn:  # [LATENCY INSTRUMENTATION - added by claude code]
            active_turn["t3"] = time.perf_counter()  # [LATENCY INSTRUMENTATION - added by claude code]
            print(f"[LATENCY] T3-T2 TTS first audio: {active_turn['t3']-active_turn['t2']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
        samples_per_channel=len(data)//2
        frame=rtc.AudioFrame(
            data=data,
            sample_rate=TTS_SAMPLE_RATE,
            num_channels=1,
            samples_per_channel=samples_per_channel
        )
        await audio_source.capture_frame(frame)
        if "t4" not in active_turn and "t3" in active_turn and active_turn["turn_id"]==my_turn_id:  # [LATENCY INSTRUMENTATION - added by claude code]
            active_turn["t4"] = time.perf_counter()  # [LATENCY INSTRUMENTATION - added by claude code]
            print(f"[LATENCY] T4-T3 Frame published: {active_turn['t4']-active_turn['t3']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
            print(f"[LATENCY] T4-T0 TOTAL latency: {active_turn['t4']-active_turn['t0']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
    tts.set_chunk_handler(handle_tts_audio)
    sentence_queue=asyncio.Queue()

    async def speak_sentences():
        while True:
            sentence=await sentence_queue.get()
            if sentence is None:
                break
            if "t2" not in active_turn and "t1" in active_turn and active_turn["turn_id"]==my_turn_id:  # [LATENCY INSTRUMENTATION - added by claude code]
                active_turn["t2"] = time.perf_counter()  # [LATENCY INSTRUMENTATION - added by claude code]
                print(f"[LATENCY] T2-T1 Sentence to TTS: {active_turn['t2']-active_turn['t1']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
            await tts.send(sentence)
        await tts.wait_until_done()
    speaker_task=asyncio.create_task(speak_sentences())
    active_turn["speaker_task"]=speaker_task

    buffer=""
    first_chunk = True
    async for chunk in get_agent_reply_stream(transcript,conversation_history):
        if first_chunk:
            print(f"LLM first token: {time.perf_counter() - active_turn['t0']:.3f}s")
            first_chunk = False
        if chunk and "t1" not in active_turn and active_turn["turn_id"]==my_turn_id:  # [LATENCY INSTRUMENTATION - added by claude code]
            active_turn["t1"] = time.perf_counter()  # [LATENCY INSTRUMENTATION - added by claude code]
            print(f"[LATENCY] T1-T0 LLM first token: {active_turn['t1']-active_turn['t0']:.3f}s")  # [LATENCY INSTRUMENTATION - added by claude code]
        buffer+=chunk
        match = re.search(r'[.!?]\s', buffer)
        while match:
            sentence = buffer[:match.end()].strip()
            buffer=buffer[match.end():]
            if sentence:
                print("Ava:", sentence)
                await sentence_queue.put(sentence)
            match = re.search(r'[.!?]\s', buffer)
    if buffer.strip():
        print("Ava:", buffer.strip())
        await sentence_queue.put(buffer.strip())
    await sentence_queue.put(None)
    await speaker_task

async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts):
    active_turn={"process_task":None,"speaker_task":None,"turn_id":0,"audio_started":False}
    # audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)
    '''
    # Reconnect loop: if the Deepgram STT connection drops (NET-0003, 1011, or any error),
    # the except* catches it, sleeps 1 second, and this loop restarts from the top,
    # creating a fresh STTConnection — runs until the participant leaves (CancelledError exits it)
    '''
    while True:
        stt=STTConnection()
        await stt.stt_connect()
        print("STT connected",time.perf_counter())  
        audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)

        async def handle_turn(transcript):
            active_turn["t0"]=time.perf_counter()
            for k in ("t1", "t2", "t3", "t4"): active_turn.pop(k, None)  # [LATENCY INSTRUMENTATION - added by claude code]
            # print("DEBUG: handle_turn called with:", transcript)
            prev_task=active_turn["process_task"]
            if prev_task and not prev_task.done() and not active_turn["audio_started"]:
                # User kept talking before Ava said anything: treat both parts as one utterance
                # and drop the unanswered first part from history so the LLM sees a single user message.
                transcript=f'{active_turn["transcript"]} {transcript}'
                await cancel_active_turn(active_turn, audio_source, tts)
                await asyncio.gather(prev_task, return_exceptions=True)
                del conversation_history[active_turn["history_len"]:]
                print("Merged continuation:", transcript)
            else:
                await cancel_active_turn(active_turn, audio_source, tts)
            active_turn["transcript"]=transcript
            active_turn["history_len"]=len(conversation_history)
            active_turn["audio_started"]=False
            active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,tts,active_turn))
        stt.stt_on_turn_end(handle_turn)
        #! Yes. forward_audio takes the user's mic audio from the LiveKit track and sends it to Deepgram STT.
        # It also runs VAD on the same audio to detect barge-in.

        # async def keepalive():
        #     '''
        #     ## Sends a KeepAlive message to Deepgram every 8 seconds to prevent the STT socket from 
        #     closing due to inactivity
        #     '''
        #     print("keepalive started")
        #     while True:
        #         await asyncio.sleep(8)
        #         print("sending keepalive")
        #         await stt.send_keep_alive()

        async def forward_audio():
            print("forward_audio started")
            speech_streak=0
            # print("forward_audio alive")
            async for event in audio_stream:
                # print("forward_audio alive")
                raw=bytes(event.frame.data)
                await stt.send_audio(raw)
                # Only count as barge-in once Ava's audio has actually started, not while the LLM is still thinking
                is_ava_speaking=active_turn["audio_started"] and active_turn["process_task"] and not active_turn["process_task"].done()
                results = await asyncio.to_thread(detect_speech, raw)
                for is_speech in results:
                    if is_speech and is_ava_speaking:
                        speech_streak+=1
                        if speech_streak >= SPEECH_CONFIRM_CHUNKS:
                            await cancel_active_turn(active_turn,audio_source,tts)
                            print("speech confirmed")
                            speech_streak=0
                    else:
                        speech_streak=0
        try:
            async with asyncio.TaskGroup() as tg:

                tg.create_task(forward_audio())
                tg.create_task(stt.stt_register_listener())
                # tg.create_task(keepalive())
            # await asyncio.gather(forward_audio(),stt.stt_register_listener())
        except* Exception as e:
            #except* replaces except, because TaskGroup raises an ExceptionGroup, even for a single error. eg.exceptions is the tuple of actual errors.
            print("Errors:",e.exceptions,time.perf_counter())
            await asyncio.sleep(1)
        # finally: runs always, on success, error, or cancellation. That's where cleanup belongs.
        finally:
            await stt.stt_close()
            #We kepth this inside finally because , we want this line to execute irrespective of whether error occured or not 


async def cancel_active_turn(active_turn,audio_source,tts):
    active_turn["turn_id"] += 1
    for key in ("process_task","speaker_task"):
        task=active_turn[key]
        if task:
            task.cancel()
    audio_source.clear_queue()
    await tts.stop()



#!TODO: kal aate hi :
#!TODo Probnlem1: Sometimes when i speak / bnarge in while ava is speakinmg it worki properly that is , it keeps speaking
# when ever i barge in and terminal pe "speech confirmed" printed " then things work great otherwise not
#! Also i faced this issue of i didnt spoke for quite sometime , like few minutes and then spoke so Ava didnt responsed witgh some Error , ...... 



#TODO: 
# ! when i press start conversation on the UI if there is no , server ruuning or active room ity should be able to connect , not like this , 




















#!  Learning : Whem and Why to use TaskGroup

# await asyncio.gather(forward_audio(),stt.stt_register_listener())

# This gather() function is used mosly for tasks that are independent 
'''
=> asyncio.gather(forward_audio(), stt.stt_register_listener()) wraps each coroutine in its own Task. 
Both run independently on the event loop. gather just waits for the results.

#? What happens when one fails !

Say the listener dies (for example, the 1011 keepalive error):

1.stt_register_listener raises, so its Task ends with an error.
2.gather immediately re-raises that error to your handle_conversation.
3.Your except catches it, and finally runs stt_close().
4.But the forward_audio Task is still alive on the event loop. Nobody told it to stop, 
  and gather doesn't cancel it.

Why that's a problem

The orphaned forward_audio keeps looping: async for event in audio_stream, then await stt.send_audio(raw). 
The socket is now closed, so send_audio raises ConnectionClosedOK. Nobody is awaiting that Task anymore,
so you get the message you saw earlier: "Task exception was never retrieved."

It works the other way too: if forward_audio fails, the listener Task keeps running.
  
'''

#! Solution : Use asyncio.TaskGroup, which means "these tasks are one unit, so if one fails, cancel the rest."
#TaskGroups offers automatic cancellation of sibling tasks on failure,
#! Notes: Notes version: independent tasks → gather. Tasks that only make sense together → TaskGroup.