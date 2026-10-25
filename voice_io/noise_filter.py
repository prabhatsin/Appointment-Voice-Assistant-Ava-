import os

# Server-side noise filter for the user's mic audio, applied before VAD and STT.
# Off by default: the browser already does noise suppression, and the ai-coustics filter is
# billed through LiveKit Cloud. Turn it on with NOISE_FILTER=ai_coustics.
NOISE_FILTERS = ("off", "ai_coustics")


def make_noise_filter():
    """Return a fresh filter for rtc.AudioStream(noise_cancellation=...), or None when off.
    One per AudioStream: the stream closes its filter when the stream closes."""
    choice = os.environ.get("NOISE_FILTER", "off").strip().lower() or "off"
    if choice not in NOISE_FILTERS:
        raise ValueError(f"NOISE_FILTER must be one of {NOISE_FILTERS}, got {choice!r}")
    if choice == "off":
        return None
    from livekit.plugins import ai_coustics   # heavy import (pulls in livekit-agents), so only when used
    return ai_coustics.audio_enhancement()
