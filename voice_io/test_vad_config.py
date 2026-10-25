"""VADConfig tests: defaults match the old constants, env overrides, validation, and the min_volume gate.
Uses the synthetic speech from test_vad_barge_in (weaker evidence than a real recording).

Run: python -m voice_io.test_vad_config   (or pytest, if installed)
"""
import os
import numpy as np
from voice_io.vad_session import VADConfig, VADStream
from voice_io.test_vad_barge_in import silence, synth_speech, run, window_end_sec, frames

ENV_KEYS = ("VAD_ACTIVATION", "VAD_DEACTIVATION", "VAD_SMOOTH_ALPHA", "VAD_MIN_SPEECH", "VAD_MIN_SILENCE", "VAD_MIN_VOLUME")


def clean_env():
    for k in ENV_KEYS:
        os.environ.pop(k, None)


def utterance(peak=0.5, tail=1.0):
    speech = synth_speech(1.5) * (peak / 0.5)
    return np.concatenate([silence(0.5), speech, silence(tail)]).astype(np.float32)


def test_defaults_match_previous_constants():
    clean_env()
    assert VADConfig.from_env() == VADConfig(activation=0.5, deactivation=0.35, smooth_alpha=0.35,
                                             min_speech=0.05, min_silence=0.55, min_volume=0.0)


def test_env_overrides():
    clean_env()
    os.environ["VAD_MIN_SILENCE"] = "0.8"
    os.environ["VAD_MIN_VOLUME"] = "0.01"
    try:
        cfg = VADStream().cfg
        assert cfg.min_silence == 0.8 and cfg.min_volume == 0.01 and cfg.activation == 0.5
    finally:
        clean_env()


def test_invalid_values_rejected():
    for bad in (dict(activation=0.3, deactivation=0.4), dict(smooth_alpha=1.0), dict(min_volume=-0.1)):
        try:
            VADConfig(**bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_min_silence_changes_end_time():
    default_end = run(VADStream(VADConfig()), utterance(tail=2.0))[1][1]
    long_end = run(VADStream(VADConfig(min_silence=0.9)), utterance(tail=2.0))[1][1]
    gap = window_end_sec(long_end) - window_end_sec(default_end)
    assert 0.3 <= gap <= 0.4, gap   # 0.9 - 0.55 = 0.35 s later


def rms_of(audio):
    return float(np.sqrt(np.mean(audio ** 2)))


def test_volume_gate_blocks_quiet_speech_only():
    quiet = utterance(peak=0.01)
    speech_rms = rms_of(synth_speech(1.5) * (0.01 / 0.5))
    gate = speech_rms * 3          # well above the quiet speech, well below normal speech
    assert [e for e, _ in run(VADStream(VADConfig()), quiet)] == ["start", "end"]   # gate off: model alone fires
    assert run(VADStream(VADConfig(min_volume=gate)), quiet) == []                   # gate on: blocked
    assert [e for e, _ in run(VADStream(VADConfig(min_volume=gate)), utterance())] == ["start", "end"]


def test_rms_reported():
    vad = VADStream(VADConfig())
    results = [r for f in frames(utterance()) for r in vad.analyze_frame(f)]
    assert results[0].rms == 0.0                      # leading digital silence
    assert max(r.rms for r in results) > 0.05         # speech


def config_with_env(**env):
    """VADConfig.from_env() with exactly these VAD_* variables set."""
    clean_env()
    os.environ.update(env)
    try:
        return VADConfig.from_env()
    finally:
        clean_env()


def test_no_env_keeps_default_thresholds():
    cfg = config_with_env()
    assert cfg.activation == 0.5 and cfg.deactivation == 0.35, cfg


def test_activation_only_moves_deactivation():
    cfg = config_with_env(VAD_ACTIVATION="0.3")
    assert cfg.activation == 0.3 and abs(cfg.deactivation - 0.15) < 1e-9, cfg


def test_explicit_deactivation_used_as_given():
    cfg = config_with_env(VAD_ACTIVATION="0.3", VAD_DEACTIVATION="0.2")
    assert cfg.activation == 0.3 and cfg.deactivation == 0.2, cfg


def test_derived_deactivation_clamps_at_zero():
    cfg = config_with_env(VAD_ACTIVATION="0.1")
    assert cfg.activation == 0.1 and cfg.deactivation == 0.0, cfg


def test_bad_min_volume_rejected():
    try:
        config_with_env(VAD_MIN_VOLUME="abc")
    except ValueError as e:
        assert "VAD_MIN_VOLUME" in str(e) and "abc" in str(e), e
    else:
        raise AssertionError("accepted VAD_MIN_VOLUME=abc")
    try:
        config_with_env(VAD_MIN_VOLUME="1.5")
    except ValueError as e:
        assert "min_volume" in str(e), e
    else:
        raise AssertionError("accepted VAD_MIN_VOLUME=1.5")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
