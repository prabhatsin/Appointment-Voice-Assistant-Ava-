

check_availability_function = {
    "name": "check_availability",
    "description": "The only source of truth for availability. Must be called before stating or refusing any slot for a date.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to check, in YYYY-MM-DD format. Convert relative dates like today or tomorrow using the date in the system prompt."
            },
        },
        "required": ["date"]
    }
}

book_slot_function = {
    "name": "book_slot",
    "description":"The only way to create a booking. Books an appointment for a given date, time, and name. Fails if the slot is already taken. Call only once date, time, and name are all known. Never claim a booking exists unless this tool returned success.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to book, in YYYY-MM-DD format. Convert relative dates using the date in the system prompt."
            },
            "time": {
                "type": "string",
                "description": "The time slot to book, in HH:MM 24-hour format."
            },
            "name": {
                "type": "string",
                "description": "The name of the person the appointment is for."
            },
        },
        "required": ["date", "time", "name"]
    }
}

# TODO:  The below Description will change a bit when we ll integrate a memory system in it 
cancel_booking_function = {
    "name": "cancel_booking",
    "description": "The only way to cancel a booking. Requires the exact booking ID returned by book_slot. Never guess an ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": "The exact booking ID returned by book_slot."
            },
        },
        "required": ["booking_id"]
    }
}


reschedule_function = {
    "name": "reschedule",
    "description": "Moves an existing appointment to a new date and time.",
    "parameters": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": "The unique booking ID of the appointment to reschedule, e.g. BK0001."
            },
            "new_date": {
                "type": "string",
                "description": "The new date, in YYYY-MM-DD format."
            },
            "new_time": {
                "type": "string",
                "description": "The new time slot, in HH:MM 24-hour format."
            },
        },
        "required": ["booking_id", "new_date", "new_time"]
    }
}
