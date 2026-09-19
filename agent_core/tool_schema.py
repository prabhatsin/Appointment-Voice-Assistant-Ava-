
check_availability_function = {
    "name": "check_availability",
    "description": "Returns the list of available appointment time slots for a given date.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to check availability for, in YYYY-MM-DD format, e.g. 2026-09-20."
            },
        },
        "required": ["date"]
    }
}

book_slot_function = {
    "name": "book_slot",
    "description": "Books an appointment for a given date, time, and name. Fails if the slot is already taken.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to book, in YYYY-MM-DD format, e.g. 2026-09-20."
            },
            "time": {
                "type": "string",
                "description": "The time slot to book, in HH:MM 24-hour format, e.g. 15:00."
            },
            "name": {
                "type": "string",
                "description": "The name of the person the appointment is for."
            },
        },
        "required": ["date", "time", "name"]
    }
}

cancel_booking_function = {
    "name": "cancel_booking",
    "description": "Cancels an existing appointment using its booking ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": "The unique booking ID of the appointment to cancel, e.g. BK0001."
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
