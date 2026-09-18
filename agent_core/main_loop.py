 #TODO: after compleeting the agent loop , learn how to make it model/ llm agnostic
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
from agent_core.tool_schema import get_weather_function,fehrenheit_temp
from agent_core.tools import get_weather,fahrenheit_calculator
from agent_core.tool_registry import tool_registry
from agent.stt import listen


load_dotenv()
client=genai.Client()
messages = []
while True:
    input_msg = listen()
    print("You:",input_msg)
    # This part handles the silences ,empty input should not go in gemini otherwise it adds error 
    if not input_msg.strip():
        print("(didn't catch that, try again)")
        continue


    if input_msg.lower().strip() == "exit":
        print("Goodbye!")
        break
    messages.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=input_msg)
            ]
        )
    )
    weather_tool=types.Tool(function_declarations=[get_weather_function])
    fahrenheit_tool=types.Tool(function_declarations=[fehrenheit_temp])
    tools=[weather_tool,fahrenheit_tool]
    while True:
        response=client.models.generate_content(
            model="gemini-3.8-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
                tools=tools,
                thinking_config=types.ThinkingConfig(
                    thinking_level='low'
                )
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
                parts=[
                    types.Part.from_function_response(
                        name=tool_call.name,
                        response={
                            "result": result
                        }
                    )
                ]
            )
            # print("TOOL RESULT:", result)
            messages.append(tool_response)
            # Continue AGENT LOOP
            continue
        else:
            print("Assistant:", response.text)
            # Append final model response
            messages.append(response.candidates[0].content)
            # Agent is finished
            break
