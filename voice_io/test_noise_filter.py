"""NOISE_FILTER switch tests (offline: the filter is only constructed, never run).
The live check, which needs LiveKit Cloud, is not part of this file.

Run: python -m voice_io.test_noise_filter   (or pytest, if installed)
"""
import os
from livekit import rtc
from voice_io.noise_filter import make_noise_filter


def with_env(value, fn):
    old = os.environ.pop("NOISE_FILTER", None)
    if value is not None:
        os.environ["NOISE_FILTER"] = value
    try:
        return fn()
    finally:
        os.environ.pop("NOISE_FILTER", None)
        if old is not None:
            os.environ["NOISE_FILTER"] = old


def test_off_by_default():
    assert with_env(None, make_noise_filter) is None
    assert with_env("", make_noise_filter) is None
    assert with_env("off", make_noise_filter) is None


def test_ai_coustics_gives_a_fresh_frame_processor():
    a = with_env("ai_coustics", make_noise_filter)
    b = with_env(" AI_Coustics ", make_noise_filter)
    assert isinstance(a, rtc.FrameProcessor) and isinstance(b, rtc.FrameProcessor)
    assert a is not b   # one per AudioStream


def test_unknown_value_rejected():
    try:
        with_env("krisp", make_noise_filter)
    except ValueError:
        return
    raise AssertionError("accepted an unknown NOISE_FILTER")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
