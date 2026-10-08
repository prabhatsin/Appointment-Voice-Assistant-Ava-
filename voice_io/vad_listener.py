# import asyncio, os, time
# from livekit import rtc, api
# from voice_io.vad_session import VADStream, SAMPLE_RATE
# from voice_io.stt_stream_final import STTConnection
# from dotenv import load_dotenv
# load_dotenv()
# ROOM = "ava-booking-room"

# async def listen(track, t0):
#     vad, stt = VADStream(), STTConnection()
#     await stt.stt_connect()

#     async def on_turn(text):
#         print(f"[{time.perf_counter():.3f}] {time.perf_counter() - t0:7.2f}s  FLUX EndOfTurn: {text}")
#     stt.stt_on_turn_end(on_turn)

#     audio_stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1)

#     async def pump():
#         async for ev in audio_stream:
#             raw = bytes(ev.frame.data)
#             await stt.send_audio(raw)
#             for r in await vad.analyze_audio(raw):
#                 if r.event:
#                     print(f"{time.perf_counter() - t0:7.2f}s  VAD {r.event.upper():5} prob={r.probability:.2f}")

#     try:
#         async with asyncio.TaskGroup() as tg:
#             tg.create_task(pump())
#             tg.create_task(stt.stt_register_listener())
#     finally:
#         await stt.stt_close()

# async def main():
#     t0 = time.perf_counter()
#     room = rtc.Room()
#     started = set()

#     def start(track, participant):
#         print("audio track:", participant.identity, track.sid)
#         if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity not in started:
#             started.add(participant.identity)
#             print("listening to", participant.identity)
#             asyncio.create_task(listen(track, t0))

#     @room.on("track_subscribed")
#     def _(track, pub, participant):
#         start(track, participant)

#     token = (api.AccessToken()
#              .with_identity("vad-listener")
#              .with_grants(api.VideoGrants(room_join=True, room=ROOM))
#              .to_jwt())
#     await room.connect(os.environ["LIVEKIT_URL"], token)

#     # tracks of participants who were already in the room
#     for p in room.remote_participants.values():
#         for pub in p.track_publications.values():
#             if pub.track and pub.kind == rtc.TrackKind.KIND_AUDIO:
#                 start(pub.track, p)

#     await asyncio.Event().wait()

# asyncio.run(main())


from dotenv import load_dotenv
load_dotenv()
import asyncio, os, time
from livekit import rtc, api
from voice_io.vad_session import VADStream, SAMPLE_RATE

ROOM = "ava-booking-room"

from voice_io.stt_stream_final import STTConnection

async def listen(track, t0):
    vad, stt = VADStream(), STTConnection()
    await stt.stt_connect()

    async def on_turn(text):
        print(f"[STT ] {time.perf_counter() - t0:7.2f}s  turn ended: {text}")
    stt.stt_on_turn_end(on_turn)

    audio_stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1)

    async def pump():
        n, total, worst, last = 0, 0.0, 0.0, time.perf_counter()
        async for ev in audio_stream:
            raw = bytes(ev.frame.data)
            await stt.send_audio(raw)
            t = time.perf_counter()
            results = await vad.analyze_audio(raw)
            ms = (time.perf_counter() - t) * 1000
            n, total, worst = n + 1, total + ms, max(worst, ms)
            for r in results:
                if r.event:
                    print(f"[VAD ] {time.perf_counter() - t0:7.2f}s  {r.event.upper():5} prob={r.probability:.2f}")
            if time.perf_counter() - last >= 5:
                print(f"[perf] avg={total / n:.1f}ms  max={worst:.1f}ms  calls={n}")
                n, total, worst, last = 0, 0.0, 0.0, time.perf_counter()

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(pump())
            tg.create_task(stt.stt_register_listener())
    finally:
        await stt.stt_close()

async def main():
    t0 = time.perf_counter()
    room = rtc.Room()
    started = set()

    def start(track, participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        print("audio track:", participant.identity, track.sid)
        if participant.identity not in started:
            started.add(participant.identity)
            asyncio.create_task(listen(track, t0))

    @room.on("track_subscribed")
    def _(track, pub, participant):
        start(track, participant)

    token = (api.AccessToken()
             .with_identity("vad-listener")
             .with_grants(api.VideoGrants(room_join=True, room=ROOM))
             .to_jwt())
    await room.connect(os.environ["LIVEKIT_URL"], token)
    for p in room.remote_participants.values():
        for pub in p.track_publications.values():
            if pub.track:
                start(pub.track, p)
    await asyncio.Event().wait()

asyncio.run(main())





