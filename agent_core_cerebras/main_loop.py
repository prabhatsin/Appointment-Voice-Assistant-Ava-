from cerebras.cloud.sdk import AsyncCerebras
from dotenv import load_dotenv
import json
from agent_core.tool_schema import (
    check_availability_function, book_slot_function, cancel_booking_function,
    reschedule_function
)
from agent_core.tool_registry import tool_registry
from agent_core.system_prompt import SYSTEM_PROMPT
load_dotenv()
client = AsyncCerebras()
tools = [
    {"type": "function", "function": check_availability_function},
    {"type": "function", "function": book_slot_function},
    {"type": "function", "function": cancel_booking_function},
    {"type": "function", "function": reschedule_function},
]

async def get_agent_reply_stream(input_msg: str, messages: list):
    '''Same logic as get_agent_reply, but yields text chunks as they're generated instead of returning one block.'''
    if not messages:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    messages.append({"role": "user", "content": input_msg})

    while True:
        stream = await client.chat.completions.create(
            model="qwen-3.8-27b",
            messages=messages,
            tools=tools,
            stream=True,
            reasoning_effort="none"
        )

        tool_calls = {}          # index -> {"id":..., "name":..., "arguments": "..."}
        collected_text = ""

        async for chunk in stream:
            # print("RAW CHUNK:", repr(chunk))
            delta = chunk.choices[0].delta

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": tc_delta.id, "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function.name:
                        tool_calls[idx]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls[idx]["arguments"] += tc_delta.function.arguments

            if delta.content:
                collected_text += delta.content
                yield delta.content   # stream text out immediately, chunk by chunk
        # print("tool_calls at end of stream:", tool_calls)
        if tool_calls:
            # Step 1: append the assistant turn that triggered the tool call(s)
            messages.append({
                "role": "assistant",
                "content": collected_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls.values()
                ],
            })

            # Step 2 & 3: execute each tool call, append its result
            for tc in tool_calls.values():
                tool_name = tool_registry[tc["name"]]
                args = json.loads(tc["arguments"])
                result = tool_name(**args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"result": result}),
                })

            continue   # loop again for the LLM's next response after the tool result
        else:
            messages.append({"role": "assistant", "content": collected_text})
            return   # done, no more tool calls