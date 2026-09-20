
import os
from livekit import api
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(".env.local")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def generate_token(room_name: str, identity: str) -> str:
    token = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
    )
    return token.to_jwt()



ROOM_NAME = "ava-booking-room"

@app.get("/token")
def get_token(identity: str = "user"):
    token = generate_token(ROOM_NAME, identity)
    return {"token": token, "url": os.environ["LIVEKIT_URL"], "room": ROOM_NAME}




#? What exactly is this token and what will be its use case , ?? 

'''
The problem this script solves

You now have three pieces built separately:

1.Your STT+LLM+TTS brain (agent_core/ + voice_io/) — works, but only via your terminal mic/speaker.

2.LiveKit — a service that lets two things talk over the internet in real time, inside something 
called a "room."

3.Eventually, a browser page — what your interviewer will actually open and click.


#! THE GAP:
The gap: a browser can't just connect to a LiveKit room for free. LiveKit needs proof that whoever's 
connecting is allowed to. That proof is a token — a signed piece of data saying "this specific person, 
is allowed to join this specific room, right now."

#? What token_server.py actually is ??

It's a tiny middleman web server, whose only job is: browser asks it "hey, give me permission to join the
room" → it uses your secret keys (safely, on the server side) to generate a token → sends just the token 
(not the secrets) back to the browser. The browser then uses that token to connect to LiveKit directly.

'''

