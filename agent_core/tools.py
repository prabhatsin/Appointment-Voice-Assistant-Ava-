
from agent_core.booking_store import BookingStore

# Single shared instance — all tool calls operate on the same in-memory store,
# so bookings persist across turns within one conversation/run.

store = BookingStore()

def check_availability(date: str) -> dict:
    '''
    Calls the store to get free slots for a date, then wraps the result
    in a dict so it's in a clean, LLM-readable shape.
    '''
    # slots is a list 
    slots = store.check_availability(date)
    return {"available_slots": slots}

def book_slot(date: str, time: str, name: str) -> dict:
    '''
    Tries to book a slot via the store. If the store raises an error
    (invalid time, already booked), catch it and return a clean error
    dict instead of letting the exception crash the agent loop.
    '''
    try:
        booking = store.book_slot(date, time, name)
        return {
            "status": "success", 
            "booking_id": booking.booking_id,
            "date": booking.date, 
            "time": booking.time
            }
    except ValueError as e:
        return {"status": "error", "message": str(e)}

def cancel_booking(booking_id: str) -> dict:
    '''
    Asks the store to cancel a booking by ID. The store returns a plain
    True/False here (not an exception), so we just branch on that.
    '''
    success = store.cancel_booking(booking_id)
    if success:
        return {"status": "success"}
    return {"status": "error", "message": f"No booking found with id {booking_id}"}

def reschedule(booking_id: str, new_date: str, new_time: str) -> dict:
    '''
    Tries to move an existing booking to a new date/time via the store.
    Same pattern as book_slot: catch the store's ValueError and turn it
    into a clean error dict.
    '''
    try:
        booking = store.reschedule(booking_id, new_date, new_time)
        return {
            "status": "success", 
            "date": booking.date, 
            "time": booking.time
            }
    except ValueError as e:
        return {"status": "error", "message": str(e)}

