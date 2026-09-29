import asyncio
# import time 
from livekit import rtc
# from transport.livekit_session_stream import setup_audio_output
from voice_io.stt_stream_final import  stt_connect, stt_on_turn_end, send_audio, stt_register_listener, stt_close
from voice_io.vad_stream import detect_speech
from agent_core.main_loop_stream import get_agent_reply_stream
import re
# from voice_io.tts_stream import PersistentTTS.set_

SAMPLE_RATE=16000
TTS_SAMPLE_RATE=24000 #? why and how is it deifferent fromn SAMPLE_RATE , ?? 
SPEECH_CONFIRM_CHUNKS = 3
conversation_history=[]
async def process_transcript(transcript:str,audio_source,tts,active_turn):
    '''
    it's the function that owns one full turn of Ava's reply, from raw transcript text to spoken audio, while 
    staying cancellable and safe against stale leftovers.
    '''
    # A safety check against EndOfTurn firing with empty/whitespace-only text (e.g. noise)
    print("DEBUG: process_transcript started")
    if not transcript.strip():
        return
    my_turn_id = active_turn["turn_id"]
    # Nested inside process_transcript, so it can see active_turn and my_turn_id as a closure,
    async def handle_tts_audio(data:bytes):
        #The staleness guard. my_turn_id was frozen at the start of this turn. active_turn["turn_id"] changes 
        # whenever cancel_active_turn runs. If they've drifted apart, this turn has been cancelled since it 
        # began, so we drop this chunk and do nothing with it.
        if active_turn["turn_id"]!=my_turn_id:
            return
        samples_per_channel=len(data)//2
        # data is raw audio bytes, and using the byte-to-sample relationship from earlier, 2 bytes per sample means the number of samples is half the byte count.
        # // is integer division, giving a whole number rather than something like 512.0.
        frame=rtc.AudioFrame(
            data=data,
            sample_rate=TTS_SAMPLE_RATE, # sample_rate decides the actual playback speed and pitch.
            num_channels=1,
            samples_per_channel=samples_per_channel
        )
        # This is what actually pushes the frame into Ava's outgoing pipe, the same AudioSource created in 
        # setup_audio_output.
        await audio_source.capture_frame(frame)

    # This line hands handle_tts_audio over to the tts object, so tts knows which function to call 
    # every time it generates a piece of audio
    tts.set_chunk_handler(handle_tts_audio)

    sentence_queue=asyncio.Queue()
    '''
    A queue built for producer/consumer situations exactly like this: one part of the code (the LLM loop, 
    coming next) will keep adding sentences as they become available, and a separate part (speak_sentences) 
    will keep taking them off and speaking them, without either side needing to know exactly when the other 
    is ready.
    '''
    async def speak_sentences():
        while True:
            sentence=await sentence_queue.get()
            # .get() waits until there's something in the queue, then removes and returns it. If the queue is empty, this line pauses here,
            if sentence is None:
                break
            await tts.send(sentence)
        await tts.wait_until_done()
        # It waits until Deepgram has actually finished generating the audio for every sentence you sent it, 
        # not just accepted the text. Sending text and getting its audio back are two separate steps, and this 
        # line makes sure the function doesn't move on until the second step is done for all of them.

    speaker_task=asyncio.create_task(speak_sentences)
    active_turn["speaker_task"]=speaker_task

    # Just an empty string, the running leftover of text that hasn't formed a full sentence yet.
    buffer=""
    
    async for chunk in get_agent_reply_stream(transcript,conversation_history):
        buffer+=chunk
        match = re.search(r'[.!?]\s', buffer)
        # Searching for these patterns 

        while match:# if something found , will strip of the sentence 
            sentence = buffer[:match.end()].strip()
            buffer=buffer[match.end():]
            if sentence:
                await sentence_queue.put(sentence)
            # run again on the now-shrunk buffer, checking whether another complete sentence exists in what's 
            # left. If yes, the while loop runs again with this new match. If no, match becomes None,
            match = re.search(r'[.!?]\s', buffer)

    # If the LLM's very last sentence doesn't end in ., !, or ? followed by whitespace, or ends the stream 
    # right at the punctuation with no trailing space, it never matches the pattern, so it sits in buffer 
    # forever and never gets pulled out inside the loop.
    if buffer.strip():
        await sentence_queue.put(buffer.stript())

    #? whats this line why puttting None in the queue , ?? 
    await sentence_queue.put(None)

    await speaker_task




#? whats this line why puttting None in the queue , ?? 

'''

=>The loop,(Inisde the speak_sentence function) on its own, has no way of knowing when the LLM has finished replying. Every time it calls .get(), 
all it knows is "something was put in the queue,"
=> this loop would run .get() forever, waiting on the queue after every sentence, since nothing tells it to stop.
=> None is the workaround:, The if sentence is None: break line is speak_sentences specifically watching for that marker,
=> So we purposefully put None in the quee as a marker / indicator that now break out of the loop , 

#!So the two sides only communicate through the queue itself:

1.process_transcript's own loop puts real sentences in, one at a time, as the LLM streams them.
2. Once it's certain there's nothing left, including that final leftover-buffer sentence, it puts None in, 
    as the very last item.
3. speak_sentences, reading from the same queue, eventually pulls that None out and recognizes it as "stop."

'''








async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts):
    await stt_connect()
    active_turn={"process_task":None,"speaker_task":None,"turn_id":0}
    #"process_task" — will hold the currently-running task that's generating the LLM response and driving the whole reply
    # "speaker_task" — will hold the currently-running task that's actually speaking the sentences out loud via TTS

    async def handle_turn(transcript):
        print("DEBUG: handle_turn called with:", transcript)
        await cancel_active_turn(active_turn, audio_source, tts)
        active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,tts,active_turn))

    stt_on_turn_end(handle_turn)

    audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)
    
    async def forward_audio():
        '''
        this function continuously pulls audio frames from the participant's microphone (via audio_stream) 
        and forwards each one to Deepgram for transcription
        '''
        speech_streak=0
        async for event in audio_stream:
            raw=bytes(event.frame.data)
            # print("DEBUG: got audio frame, size", len(raw))
            await send_audio(raw)
            # send_audio calls connection.send_media ,sending the raw bytes over the already-open WebSocket to
            #  Deepgram's servers.
            #? Question Why are we using "process_task" for the "is_ava_speaking" part ,not "speaker_task" 
            # Answer given below :
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
    # await asyncio.gather(a(), b()): starts a and b concurrently, but the await in front of it pauses your function until both finish.
    await stt_close()
    #TODO: If one of these ends by crashing, gather raises the exception and stt_close() is skipped, so the connection never gets closed cleanly. That's why a try/finally (or TaskGroup)


#! We could have defined this cancel_active_turn outside handle conversation not because of any reason its simply , design choice 
# We could have defined it inside also , and it would have worked same ,
async def cancel_active_turn(active_turn,audio_source,tts):
    #active_turn is the shared dict holding the two running tasks. We'll cancel whatever is stored in it.
    #audio_source is Ava's outgoing audio pipe. We'll empty its queue so old audio stops playing.
    #tts is the PersistentTTS object. We'll tell it to stop generating audio.
    active_turn["turn_id"] += 1
    for key in ("process_task","soeaker_task"):
        task=active_turn[key]
        if task:
            # It only tells you a task exists,not whether it's still running
            # A finished task is still a Task object, so it's still true. That's fine,because cancelling a finished task does nothing.
            task.cancel()
    audio_source.clear_queue() # wipes audio already handed to LiveKit but not yet played.
    await tts.stop() 
    # Sends Deepgram the Clear message so it stops generating audio for the old sentences.





#? Question Why are we using "process_task" for the "is_ava_speaking" part ,not "speaker_task" 
'''

=>process_task: true for the entire turn, from the moment it starts, including before any audio exists.
=>speaker_task: true only once speaking has actually begun, and only after it's been assigned for this turn.

If what you want is "cut her off the instant any part of her turn is active, even before she's said a word," 
process_task is correct, and that's what we used. If you specifically want "only interrupt once she's actually
producing audio," speaker_task is closer to that,

'''









#track: rtc.Track — the specific audio stream belonging to one participant's microphone.
'''
->represents one stream of media (audio or video) flowing through LiveKit.
->When a participant's microphone is active, their audio exists as a Track object - it's LiveKit's way of representing "here's a continuous stream of media data belonging to someone."
->You get one automatically handed to you via the "track_subscribed" event, whenever someone's audio becomes available to your agent.

What above sentence mean is , 

When LiveKit fires the track_subscribed event (someone's mic audio becomes available), it automatically 
passes a Track object as an argument into your registered handler (on_track_subscribed(track, publication, 
participant)) — you don't create it yourself,

'''

# audio_source: rtc.AudioSource — Ava's outgoing voice pipe (created once, in setup_audio_output, back in 
# agent_connector_stream.py). This function needs it to actually push TTS-generated audio out to the room, 
# and to call .clear_queue() when cancelling a turn.

#? What does ,stt_on_turn_end(handle_turn do , ?? 
'''
->This takes whatever you pass in — here, (your handle_turn)function — and stores it into that other file's 
(stt_stream_final) on_turn_end variable.
-> after this line runs ,stt_stream_final.py's on_turn_end variable now points at your function.
-> This on_turn_end refers to that file's own variable — which, after your registration call, now holds a
 reference to your function. So when a real EndOfTurn message arrives, Deepgram's SDK triggers 
 stt_stream_final.py's on_message, which then calls your handle_turn (the one in conversation_handler.py),
passing it the transcript

'''

#? Lets explore the line 'active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,user_stoppeda_at,tts,active_turn))' ??

'''
#! summary:
In one sentence: this line starts process_transcript running in the background (without blocking handle_turn), 
and saves a reference to that running task so it can be checked or cancelled later.
i) process_transcript()
    This creates a coroutine object by calling process_transcript (which is async def) with these five 
    arguments — but remember, from way earlier: calling an async function without await doesn't run it

ii) asyncio.ensure_future(...):
    Takes that coroutine object and says: "actually start running this, as an independent, separate task in 
    the event loop, right now — don't make me wait for it." This is the exact same pattern we covered with 
    on_track_subscribed earlier — ensure_future is used here for the same reason: we're inside an 
    async def function (handle_turn), but we deliberately don't want to await this, because process_transcript
    runs a whole conversation turn (LLM streaming + TTS speaking) that could take seconds — we don't want 
    handle_turn stuck waiting that whole time.
iii)active_turn["process_task"] = ...:
    ensure_future returns a Task object — a handle representing "this specific running background operation." 
    We store that Task object into active_turn["process_task"], so that other parts of the code 
    (the VAD check, cancel_active_turn) can later reference this specific task — to check if it's still running 
    (.done()), or to cancel it (.cancel()).

'''

#? Explore : audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)

'''
-> track (given to you by LiveKit via the track_subscribed event) is a fairly low-level representation of 
    the participant's audio ("Low-level" here means the track object is close to the raw WebRTC/networking 
    machinery — it's the thing WebRTC itself deals with, not something shaped for your convenience.)

-> rtc.AudioStream(track, ...) wraps it into a more usable object that you can actually loop over 
    (async for event in audio_stream:) to get individual audio frames, one at a time, instead of dealing 
    with the raw track directly.

-> An audio frame is just a small, discrete chunk of that digital audio data — a short slice of the continuous 
   sound stream, packaged as one unit you can process at a time.

'''


#? What is asyncio.Queue , ?? 

'''
=> asyncio.Queue is a first-in, first-out (FIFO) queue designed for coordinating producer and consumer 
coroutines in asynchronous Python code

'''