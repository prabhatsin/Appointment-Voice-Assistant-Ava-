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

def get_agent_reply(input_msg:str,messages:list)-> str:
    messages.append(
        types.Content(role="user",parts=[types.Part.from_text(text=input_msg)])
    )
    while True:
        response=client.models.generate_content(
            model="gemini-3.8-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
                tools=tools,
                system_instruction=SYSTEM_PROMPT,
                thinking_config=types.ThinkingConfig(thinking_level='low')
            )
        )
        parts=response.candidates[0].content.parts
        tool_call=None
        for part in parts:
            if part.function_call:
                tool_call=part.function_call
                #! This break statement takes out of the above for loop not the main while loop
                break
        if tool_call: # check if tool call present in the response
            #step1:# 1. Append Gemini's model response containing the function call
            messages.append(response.candidates[0].content)
            # step2:Execute the actual Python function
            tool_name=tool_registry[tool_call.name]
            result=tool_name(**tool_call.args)
            # Step3: Append the functions result
            tool_response = types.Content(
                role="user",
                parts=[types.Part.from_function_response( name=tool_call.name,response={"result": result})]
            )
            messages.append(tool_response)
            # Continue AGENT LOOP
            continue
        else:
            # Append final model response
            messages.append(response.candidates[0].content)
            # Agent is finished
            return response.text
