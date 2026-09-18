
#! This file contains the ,  mapping of tool call and defined tools(functions)

from agent_core.tools import get_weather,fahrenheit_calculator

tool_registry={
    "get_weather": get_weather,
    "fahrenheit_calculator": fahrenheit_calculator
}