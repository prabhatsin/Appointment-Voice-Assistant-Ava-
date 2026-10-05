
from groq import AsyncGroq
from dotenv import load_dotenv
import json

from agent_core.tool_schema import (
    check_availability_function,
    book_slot_function,
    cancel_booking_function,
    reschedule_function,
)
from agent_core.tool_registry import tool_registry
from agent_core.system_prompt import SYSTEM_PROMPT
import asyncio

load_dotenv()

client = AsyncGroq()

tools = [
    {"type": "function", "function": check_availability_function},
    {"type": "function", "function": book_slot_function},
    {"type": "function", "function": cancel_booking_function},
    {"type": "function", "function": reschedule_function},
]


async def get_agent_reply_stream(input_msg: str, messages: list):
    prompt = build_system_prompt()
    if messages:
        # Non-empty list: overwrite messages[0] with a fresh prompt, so the date stays current.
        messages[0] = {"role": "system", "content": prompt}
    else:
        messages.append({"role": "system", "content": prompt})

    while True:

        stream = await client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            tools=tools,
            stream=True,
        )

        tool_calls = {}
        collected_text = ""

        async for chunk in stream:

            delta = chunk.choices[0].delta

            # Collect tool calls
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:

                    idx = tc_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id,
                            "name": "",
                            "arguments": "",
                        }

                    if tc_delta.id:
                        tool_calls[idx]["id"] = tc_delta.id

                    if tc_delta.function.name:
                        tool_calls[idx]["name"] += tc_delta.function.name

                    if tc_delta.function.arguments:
                        tool_calls[idx]["arguments"] += tc_delta.function.arguments

            # Stream normal text
            if delta.content:
                collected_text += delta.content
                yield delta.content

        # -------------------------------
        # Tool call requested
        # -------------------------------

        if tool_calls:

            messages.append({
                "role": "assistant",
                "content": collected_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in tool_calls.values()
                ],
            })

            # Execute tools
            for tc in tool_calls.values():

                tool = tool_registry[tc["name"]]

                args = json.loads(tc["arguments"])

                # result = tool(**args) # Works for the demo data
                result = await asyncio.to_thread(tool, **args) # This one is for the calender api

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({
                        "result": result
                    }),
                })

            # Ask model again with tool results
            continue

        # -------------------------------
        # No tool call → finished
        # -------------------------------

        messages.append({
            "role": "assistant",
            "content": collected_text
        })

        return
