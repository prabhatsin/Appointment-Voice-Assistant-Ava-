
# import os
# from dotenv import load_dotenv
# from livekit import api

# load_dotenv(".env.local")

# async def main():
#     lkapi = api.LiveKitAPI(
#         url=os.environ["LIVEKIT_URL"],
#         api_key=os.environ["LIVEKIT_API_KEY"],
#         api_secret=os.environ["LIVEKIT_API_SECRET"],
#     )
#     rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
#     print("Connected! Rooms:", rooms)
#     await lkapi.aclose()

# import asyncio
# asyncio.run(main())


# import os
# from dotenv import load_dotenv
# load_dotenv(".env.local")

# url = os.environ.get("LIVEKIT_URL")
# key = os.environ.get("LIVEKIT_API_KEY")
# secret = os.environ.get("LIVEKIT_API_SECRET")

# print("URL:", repr(url))
# print("KEY:", repr(key))
# print("SECRET len:", len(secret) if secret else None)
# print("SECRET repr (masked):", repr(secret[:3] + "..." + secret[-3:]) if secret else None)

import os
import requests
from dotenv import load_dotenv

load_dotenv(".env.local")

headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
resp = requests.get("https://api.deepgram.com/v1/projects", headers=headers)
print(resp.status_code)
print(resp.json())