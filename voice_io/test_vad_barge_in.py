"""VADStream tests for barge-in: start/end events, per-instance isolation, trigger latency.

There is no speech recording in the repo, so this uses synthetic formant speech (a pulse train through
vowel formant filters). Silero scores it as speech, but it is weaker evidence than a real recording.

Run: python -m voice_io.test_vad_barge_in   (or pytest, if installed)
"""
import asyncio
import time
import numpy as np
from scipy.signal import lfilter
from voice_io.vad_session import VADStream, SAMPLE_RATE, WINDOW_SAMPLES

FRAME_SAMPLES = 160   # LiveKit delivers 10 ms frames


def silence(sec):
    return np.zeros(int(sec * SAMPLE_RATE), dtype=np.float32)


def noise(sec, level=0.003, seed=1):
    return (level * np.random.default_rng(seed).standard_normal(int(sec * SAMPLE_RATE))).astype(np.float32)


def _formant(x, f, bw):
    r = np.exp(-np.pi * bw / SAMPLE_RATE)
    th = 2 * np.pi * f / SAMPLE_RATE
    return lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)


def synth_speech(sec, seed=0):
    """Voiced, vowel-like audio: glottal pulses at a wandering pitch, through changing formants."""
    rng = np.random.default_rng(seed)
    n = int(sec * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    f0 = 130 + 30 * np.sin(2 * np.pi * 0.7 * t)
    pulses = (np.diff(np.floor(np.cumsum(f0 / SAMPLE_RATE)), prepend=0) > 0).astype(float)
    pulses += 0.02 * rng.standard_normal(n)
    vowels = [(700, 1220, 2600), (300, 2300, 3000), (500, 900, 2500), (400, 1900, 2550)]
    out = np.zeros(n)
    seg = int(0.18 * SAMPLE_RATE)
    for i in range(0, n, seg):
        s = pulses[i:i + seg]
        y = sum(_formant(s, f, 80 + 40 * k) for k, f in enumerate(vowels[rng.integers(4)]))
        out[i:i + seg] = y * np.hanning(len(s)) ** 0.5
    return (out / np.abs(out).max() * 0.5).astype(np.float32)


def frames(audio):
    """Split float audio into 16-bit PCM byte frames, the way forward_audio receives them."""
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    return [pcm[i:i + FRAME_SAMPLES].tobytes() for i in range(0, len(pcm), FRAME_SAMPLES)]


def run(vad, audio):
    """Feed audio frame by frame; return [(event, window_index)]."""
    events, window = [], 0
    for f in frames(audio):
        for r in vad.analyze_frame(f):
            if r.event:
                events.append((r.event, window))
            window += 1
    return events


def window_end_sec(window):
    return (window + 1) * WINDOW_SAMPLES / SAMPLE_RATE


def test_silence_has_no_events():
    vad = VADStream()
    assert run(vad, silence(2.0)) == []
    vad.reset()
    assert run(vad, noise(2.0)) == []


def test_speech_fires_start():
    events = run(VADStream(), synth_speech(1.5))
    assert [e for e, _ in events] == ["start"], events


def test_speech_then_silence_fires_start_then_end():
    audio = np.concatenate([silence(0.5), synth_speech(1.5), silence(1.0)])
    events = run(VADStream(), audio)
    assert [e for e, _ in events] == ["start", "end"], events
    start_t, end_t = window_end_sec(events[0][1]), window_end_sec(events[1][1])
    assert 0.5 < start_t < 0.8, start_t
    assert 2.0 < end_t < 2.0 + 1.0, end_t   # end comes after MIN_SILENCE of silence


def test_instances_are_isolated():
    """Two connections fed concurrently must not affect each other (the old detect_speech shared one buffer and model)."""
    speech_audio = np.concatenate([silence(0.5), synth_speech(1.5), silence(1.0)])
    quiet_audio = silence(len(speech_audio) / SAMPLE_RATE)
    expected = run(VADStream(), speech_audio)

    async def feed(vad, audio):
        events, window = [], 0
        for f in frames(audio):
            for r in await vad.analyze_audio(f):
                if r.event:
                    events.append((r.event, window))
                window += 1
            await asyncio.sleep(0)   # interleave with the other connection
        return events

    async def both():
        return await asyncio.gather(feed(VADStream(), speech_audio), feed(VADStream(), quiet_audio))

    speech_events, quiet_events = asyncio.run(both())
    assert speech_events == expected, (speech_events, expected)
    assert quiet_events == [], quiet_events


def measure_trigger_latency(onset_sec=0.5):
    """Audio time from true speech onset to the window where "start" fires, plus per-frame processing time."""
    audio = np.concatenate([silence(onset_sec), synth_speech(1.5)])
    vad = VADStream()
    window, trigger, frame_ms = 0, None, []
    for f in frames(audio):
        t = time.perf_counter()
        results = vad.analyze_frame(f)
        frame_ms.append((time.perf_counter() - t) * 1000)
        for r in results:
            if r.event == "start" and trigger is None:
                trigger = (window_end_sec(window) - onset_sec, r.speech_time)
            window += 1
    return trigger, max(frame_ms)


def test_trigger_latency_is_bounded():
    (latency, _), _ = measure_trigger_latency()
    assert latency < 0.2, latency


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    (latency, speech_run), worst_frame = measure_trigger_latency()
    print(f"onset -> barge-in trigger: {latency * 1000:.0f} ms of audio "
          f"(speech_run at trigger {speech_run * 1000:.0f} ms), worst frame processing {worst_frame:.1f} ms")
