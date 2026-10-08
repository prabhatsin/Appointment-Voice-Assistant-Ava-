
#? Part 1: the three classes
#?  Explore and implement this 

'''
Think of a phone call center.

1.AgentSession is the whole call. One per conversation. It holds the configuration (which STT, LLM, TTS and VAD to use), the room connection, and the shared state ("user is speaking", "agent is speaking", "user is away"). In Ava, the closest equivalent is your handle_conversation plus the settings around it.
2.AgentActivity is the agent's brain during the call. It decides what to do when things happen: start a reply, interrupt, run a tool, queue speech. In Ava, it's roughly process_transcript, cancel_active_turn and your turn_id logic.
3.AudioRecognition is the ears. It takes raw microphone frames, sends them to STT, VAD and the turn detector at the same time, merges their signals into events ("user started speaking", "turn finished"), and calls AgentActivity with them. In Ava, it's roughly forward_audio plus your VAD call.

The flow is mic frames → AudioRecognition → events → AgentActivity → reply. The code confirms it: AgentActivity implements the hooks AudioRecognition calls.
'''




#?
#! Three things to implement in similar way livekit does is , 
#1. VAD (silero/vad.py)
'''

Windowing. It runs a small model on 32 ms windows (512 samples at 16 kHz) with a 64-sample context and carried-over recurrent state. Inference runs in an executor so the event loop isn't blocked, and a warning logs if a window takes over 200 ms.
Smoothing and hysteresis. Each probability is smoothed with an exponential filter. A window counts as speech at 0.5 or above, but once speaking it stays speech down to 0.35.
Start and end. Start fires after about 50 ms of consecutive speech windows. End fires after 0.55 s of consecutive silence. A single silent window resets the speech counter.
Prefix padding. It keeps 0.5 s of audio before speech onset, so a start event carries the lead-in syllable.
A continuous signal. It emits a probability event every window, with running speech and silence totals. AudioRecognition uses these as the earliest signal for timing and for scheduling end-of-turn work.

'''
#2 End of turn detection

'''

Signals. The mode is one of turn-detector model, VAD only, STT-native (like Flux), manual, or realtime LLM. All of them end up in the same _run_eou_detection.

Flow in VAD-based mode:

After only 200 ms of silence while the user was speaking, it already requests a prediction from the turn detector. That is well before VAD's 0.55 s end-of-speech, so the answer is often cached by the time it's needed. If speech resumes, the request is cancelled.
When VAD declares end of speech, a "bounce" task starts. It waits for the prediction (up to 1 s for the audio detector, 3 s for the text one).
If the end-of-turn probability is below a per-language "unlikely" threshold (0.36 for English on the local model), the wait is max_delay (about 3 s). Otherwise it's min_delay (about 0.5 s).
The wait is measured from the last moment of speech. New speech, a new transcript, or an STT start-of-speech cancels and restarts the task.
Only when the wait expires does the turn commit. Final transcripts accumulate into one string until then.

'''
'''
The two detector generations:

The older open-source plugin is a small text model. It sees the last 6 turns (at most 128 tokens), lowercased with punctuation stripped, and returns the probability of an end-of-utterance token.
The newer audio detector looks at the audio itself. v1 runs in the cloud and also returns a backchannel probability. v1-mini runs locally from a native binary and doesn't give backchannel scores.
The audio detector fails over from cloud to local. If both fail, the turn commits on the plain endpointing delay.

Dynamic endpointing learns the minimum delay from the user's own pauses. It treats an immediate interruption after a committed turn as evidence the cut-off was premature.

'''

#3 Barge-in 

'''

#!VAD-only path:

VAD speech lasting at least 0.5 s triggers _interrupt_by_audio_activity. Before that it checks several conditions: echo-cancellation warm-up, min_words (off by default) against the live transcript, and whether the current speech allows interruption.
If the audio output can pause, it pauses playback and sets the agent to listening, but does not cancel the generation.
The false-interruption timer (2 s) starts when the user stops speaking. A final transcript or a committed reply turn turns the pause into a real interruption, tagged with its source.
If the timer fires with no transcript, playback resumes where it stopped. If a turn decision is still open, the timer waits for that first.
If the user starts talking while the agent is still "thinking" (reply not yet audible), the pending reply is paused before it ever plays.
After an interruption, tasks are cancelled and the audio buffer is cleared. Playout position then determines what text goes into history. If the speech hasn't finished within 5 s of an interruption, it's cancelled forcibly.

#!Adaptive path (the audio model, reached over a WebSocket to LiveKit's inference gateway):

Once the agent is speaking, VAD-based interruption is turned off and only the model can interrupt.
STT events are held back while an overlap is unresolved.
During overlap it sends up to 3 s of audio (including a 1 s lead-in) every 0.1 s, needs at least two consecutive 25 ms frames, and times out after 0.7 s.
It scores the overlap conservatively (a high percentile of per-frame probabilities). If the verdict is "interruption", held transcripts are released and the normal pause-then-commit path runs. If it's a backchannel, the held transcript is trimmed and discarded, so "mm-hmm" never becomes a user turn.
Any detector error falls back to VAD-only.
Without explicit configuration it's off outside LiveKit-hosted or dev mode, and it needs LiveKit inference credentials.

'''

#? Go to the claude chat again and again , 

'''
#! Explore this 

How the pieces connect

The same audio frames feed three parallel consumers: Silero VAD, STT, and (when enabled) the turn-detector
and adaptive-interruption streams. AudioRecognition merges their signals into "speech started", 
"speech ended", "turn committed" and "overlap verdict", and AgentActivity reacts to those.

'''
