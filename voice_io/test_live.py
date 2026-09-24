# import asyncio
# import sounddevice as sd
# import numpy as np
# from voice_io.tts_stream import stream_speech

# SAMPLE_RATE = 24000

# async def main():
#     stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
#     stream.start()

#     async def on_chunk(data):
#         samples = np.frombuffer(data, dtype=np.int16)
#         await asyncio.to_thread(stream.write, samples)

#     await stream_speech("Hello, this is a live test of streaming text to speech, spoken as it is generated.", on_chunk)

#     stream.stop()
#     stream.close()

# if __name__ == "__main__":
#     asyncio.run(main())

import math
import os
import time

WIDTH = 100
HEIGHT = 35


def clear_screen():
    os.system("clear")


def make_heart(scale):
    canvas = [[" " for _ in range(WIDTH)] for _ in range(HEIGHT)]

    # Parametric heart curve
    points = []

    for i in range(500):
        t = 2 * math.pi * i / 500

        x = 16 * math.sin(t) ** 3
        y = (
            13 * math.cos(t)
            - 5 * math.cos(2 * t)
            - 2 * math.cos(3 * t)
            - math.cos(4 * t)
        )

        # Stretch/shrink
        x *= scale
        y *= scale

        # Terminal coordinate conversion
        screen_x = int(WIDTH / 2 + x * 2)
        screen_y = int(HEIGHT / 2 - y * 0.75)

        points.append((screen_x, screen_y))

    # Put "sorry" along the outline
    word = "sorry_kuchu_puchu"
    used = set()

    for x, y in points:

        # Don't put words outside terminal
        if x < 0 or x + len(word) >= WIDTH:
            continue

        if y < 0 or y >= HEIGHT:
            continue

        # Prevent words from overlapping too much
        key = (x // 5, y)

        if key in used:
            continue

        used.add(key)

        for i, char in enumerate(word):
            if 0 <= x + i < WIDTH:
                canvas[y][x + i] = char

    return "\n".join("".join(row) for row in canvas)


# Animation
scale = 1.0
direction = 1

while True:

    clear_screen()

    print(make_heart(scale))

    # Pulse
    scale += 0.015 * direction

    if scale >= 1.08:
        direction = -1

    if scale <= 0.92:
        direction = 1

    time.sleep(0.05)