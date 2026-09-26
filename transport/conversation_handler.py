import asyncio
import time 
from livekit import rtc
from voice_io.stt_stream_final import  stt_connect, stt_on_turn_end, send_audio, stt_register_listener, stt_close

SAMPLE_RATE=16000

async def handle_conversation(track:rtc.Track,audio_source: rtc.AudioSource,tts):
    await stt_connect()
    active_turn={"process_task":None,"speaker_task":None}
    #"process_task" — will hold the currently-running task that's generating the LLM response and driving the whole reply
    # "speaker_task" — will hold the currently-running task that's actually speaking the sentences out loud via TTS

    async def handle_turn(transcript):
        user_stoppeda_at=time.time()
        active_turn["process_task"]=asyncio.ensure_future(process_transcript(transcript,audio_source,user_stoppeda_at,tts,active_turn))

    stt_on_turn_end(handle_turn)

    audio_stream=rtc.AudioStream(track,sample_rate=SAMPLE_RATE,num_channels=1)
    async def forward_audio():
        '''
        this function continuously pulls audio frames from the participant's microphone (via audio_stream) 
        and forwards each one to Deepgram for transcription
        '''
        async for event in audio_stream:
            raw=bytes(event.frame.data)
            await send_audio(raw)
    # send_audio calls connection.send_media ,sending the raw bytes over the already-open WebSocket to Deepgram's servers.



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
->This takes whatever you pass in — here, (your handle_turn)function — and stores it into that other file's (stt_stream_final)
on_turn_end variable.
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