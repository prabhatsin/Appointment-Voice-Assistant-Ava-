
get_weather_function={
    "name":"get_weather",
    "description":"Returns the current temperature for the specified city.",
    "parameters":{
        "type":"object",
        "properties":{
            "city":{
                  "type":"string",
                   "description":"The city whose current weather you want to know, e.g. Delhi."
            },
          
        },
        "required":["city"]
    }
}



fehrenheit_temp={
    "name":"fahrenheit_calculator",
    "description":"Returns  temperature in Fahrenheit given temp in degree celsius as input",
    "parameters":{
        "type":"object",
        "properties":{
            "temperature":{
                  "type":"integer",
                   "description":"The temperature in degree celsius."
            },
          
        },
        "required":["temperature"]
    }
}


