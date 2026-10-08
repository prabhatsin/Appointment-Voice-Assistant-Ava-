from voice_io.vad_session import VADStream

def run(seq):
    v = VADStream()
    return [(i, e) for i, s in enumerate(seq, 1) if (e := v.detect_transition(s))]

print(run([False]*3 + [True]*5 + [False]*18))
print(run([True]*4 + [False]*10 + [True]*4 + [False]*18))
print(run([True] + [False]*30))

v = VADStream()
for _ in range(5):
    v.detect_transition(True)
print(v.speaking)
v.reset()
print(v.speaking, v.speech_time, v.silence_time)