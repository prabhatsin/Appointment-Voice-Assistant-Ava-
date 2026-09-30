import asyncio
from livekit import rtc
from voice_io.stt_stream_final import  stt_connect, stt_on_turn_end, send_audio, stt_register_listener, stt_close
from voice_io.vad_stream import detect_speech
from agent_core.main_loop_stream import get_agent_reply_stream
import re
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
        samples_per_channel=len(data)//2
        frame=rtc.AudioFrame(
            data=data,
            sample_rate=TTS_SAMPLE_RATE,
            num_channels=1,
            samples_per_channel=samples_per_channel
        )
        await audio_source.capture_frame(frame)
    tts.set_chunk_handler(handle_tts_audio)
    sentence_queue=asyncio.Queue()

    async def speak_sentences():
        while True:
            sentence=await sentence_queue.get()
            if sentence is None:
                break
            await tts.send(sentence)
        await tts.wait_until_done()
    speaker_task=asyncio.create_task(speak_sentences())
    active_turn["speaker_task"]=speaker_task

    buffer=""
    async for chunk in get_agent_reply_stream(transcript,conversation_history):
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
    await stt_connect()
    active_turn={"process_task":None,"speaker_task":None,"turn_id":0}
 
    async def handle_turn(transcript):
        # print("DEBUG: handle_turn called with:", transcript)
        await cancel_active_turn(active_turn, audio_source, tts)
        active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,tts,active_turn))
    stt_on_turn_end(handle_turn)
    audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)
    async def forward_audio():
        speech_streak=0
        async for event in audio_stream:
            raw=bytes(event.frame.data)
            await send_audio(raw)
            is_ava_speaking=active_turn["process_task"] and not active_turn["process_task"].done()
            for is_speech in detect_speech(raw):
                if is_speech and is_ava_speaking:
                    speech_streak+=1
                    if speech_streak >= SPEECH_CONFIRM_CHUNKS:
                        await cancel_active_turn(active_turn,audio_source,tts)
                        print("speech confirmed")
                        speech_streak=0
                else:
                    speech_streak=0
    await asyncio.gather(forward_audio(),stt_register_listener())
    await stt_close()

async def cancel_active_turn(active_turn,audio_source,tts):
    active_turn["turn_id"] += 1
    for key in ("process_task","speaker_task"):
        task=active_turn[key]
        if task:
            task.cancel()
    audio_source.clear_queue()
    await tts.stop() 


