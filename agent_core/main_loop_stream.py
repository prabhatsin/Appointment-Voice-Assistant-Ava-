
#TODO: after compleeting the agent loop , learn how to make it model/ llm agnostic
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agent_core.tool_schema import (check_availability_function, book_slot_function,cancel_booking_function,
    reschedule_function)
from agent_core.tool_registry import tool_registry
from agent_core.system_prompt import SYSTEM_PROMPT

load_dotenv()

client=genai.Client()
booking_tool = types.Tool(function_declarations=[
    check_availability_function,
    book_slot_function,
    cancel_booking_function,
    reschedule_function,
])
tools = [booking_tool]

async def get_agent_reply_stream(input_msg: str, messages: list):
    '''Same logic as get_agent_reply, but yields text chunks as they're generated instead of returning one block.'''
    messages.append(
        types.Content(role="user", parts=[types.Part.from_text(text=input_msg)])
    )
    while True:
        stream = await client.aio.models.generate_content_stream(
            model="gemini-3.1-flash-lite",
            contents=messages,
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tools=tools,
                system_instruction=SYSTEM_PROMPT,
                thinking_config=types.ThinkingConfig(thinking_level='low'),
            ),
        )
        tool_call = None
        full_content_parts = []
        collected_text = ""

        async for chunk in stream:
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if part.function_call:
                    tool_call = part.function_call
                full_content_parts.append(part)
                if part.text:
                    collected_text += part.text
                    yield part.text   # stream text out immediately, chunk by chunk
        if tool_call:
            messages.append(types.Content(role="model", parts=full_content_parts))
            tool_name = tool_registry[tool_call.name]
            result = tool_name(**tool_call.args)
            tool_response = types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=tool_call.name, response={"result": result})],
            )
            messages.append(tool_response)
            continue   # loop again for the LLM's next response after the tool result
        else:
            messages.append(types.Content(role="model", parts=full_content_parts))
            return   # done, no more tool calls
