import asyncio
from agent_core.main_loop_stream import get_agent_reply_stream

# async def main():
#     messages = []

#     print("Ava: ", end="", flush=True)
#     async for chunk in get_agent_reply_stream("Hi, can you tell me the available slots on September 20th?", messages):
#         print(chunk, end="", flush=True)
#     print()  # newline after full response

# if __name__ == "__main__":
#     asyncio.run(main())



async def main():
    messages = []

    print("Ava: ", end="", flush=True)
    async for chunk in get_agent_reply_stream("Tell me about India's history in detail, at least five sentences.", messages):
        print(chunk, end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(main())