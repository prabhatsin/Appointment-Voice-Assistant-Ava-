
#!It's your in-memory "database": a plain Python class that holds the actual appointment data
#! In the below give case it will be in memory dictionary named "bookings"

#? Read the end of the file to know more  about datclass 

from dataclasses import dataclass
@dataclass
class Booking:
    booking_id: str
    date: str      # "2026-09-20"
    time: str      # "15:00"
    name: str



class BookingStore:
    def __init__(self):
        self.slots = ["10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]
        self.bookings: dict[str, Booking] = {}   # booking_id -> Booking
        # dict[str, Booking], Just a type hint saying "this variable will be a dictionary where 
        # keys are strings and values are Booking objects."
        
        '''
        #eg
        self.bookings = {
            "BK0001": Booking(booking_id="BK0001", date="2026-09-20", time="15:00", name="Prabhat"),
            "BK0002": Booking(booking_id="BK0002", date="2026-09-20", time="10:00", name="Riya"),
        }
        '''
        self._next_id = 1

    def check_availability(self, date: str) -> list[str]:
        '''
        "Takes a date, looks through all existing bookings to find which of the fixed time slots are 
        already taken on that date, and returns the list of slots that are still free."
        '''

        booked_times = set() # eg booked_times = {"15:00", "10:00"}
        for b in self.bookings.values():
            if b.date == date:
                booked_times.add(b.time)
        available = []
        for t in self.slots:
            if t not in booked_times:
                available.append(t)
        return available


    def book_slot(self, date: str, time: str, name: str) -> Booking:
        '''
        Takes a date, time, and name. Checks that the time is a valid slot and not already
        booked on that date, then creates a new booking with a generated ID, stores it,
        and returns it.
        '''
        # Guard 1: reject times that aren't in our fixed slot list at all
        if time not in self.slots:
            raise ValueError(f"{time} is not a valid slot time")
        
        # Guard 2: build the set of already-booked times for this date, same as check_availability
        booked_times = set()
        for b in self.bookings.values():
            if b.date == date:
                booked_times.add(b.time)
        if time in booked_times:
            raise ValueError(f"{time} on {date} is already booked")

        # Generate a new unique ID, e.g. "BK0001", "BK0002", ...
        booking_id = f"BK{self._next_id:04d}"
        self._next_id += 1

        # Create the booking object and store it
        booking = Booking(booking_id, date, time, name)
        self.bookings[booking_id] = booking

        return booking

    def cancel_booking(self, booking_id: str) -> bool:
        '''
        Takes a booking ID. If a booking with that ID exists, removes it from storage
        and returns True. If no such booking exists, returns False without changing anything.
        '''
        # Check if this ID actually exists in our bookings dictionary
        if booking_id in self.bookings:
            # del removes the key-value pair from the dictionary entirely
            del self.bookings[booking_id]
            return True

        # ID wasn't found — nothing to cancel
        return False

    
    def reschedule(self, booking_id: str, new_date: str, new_time: str) -> Booking:
        '''
        Takes an existing booking ID and a new date/time. Checks the booking exists and that
        the new slot isn't already taken by some other booking, then updates that same booking
        in place and returns it.
        '''

        # Guard 1: the booking must actually exist
        if booking_id not in self.bookings:
            raise ValueError(f"No booking found with id {booking_id}")

        # standard dictionary lookup
        old = self.bookings[booking_id]

        # Guard 2: build the set of times already booked on the NEW date,
        # Note: this set excludes the booking's own current slot — that shouldn't count as a conflict."
        # Because this function allows to reschedule at its own time ,
        #rescheduling a booking to its own current slot isn't actually double-booking anything
        conflicting_times = set()
        for b in self.bookings.values():
            if b.date == new_date and b.booking_id != booking_id:
                conflicting_times.add(b.time)

        if new_time in conflicting_times:
            raise ValueError(f"{new_time} on {new_date} is already booked")

        # Update the existing Booking object's fields directly (in place)
        old.date = new_date
        old.time = new_time

        return old




# @dataclass is a shortcut — it auto-generates a constructor(__init__) for you. ?? 
# What the above line means it 
'''
=>Normally in Python, you have to write the __init__ method (the constructor) yourself to set up an object's
attributes. @dataclass writes that __init__ for you automatically,

Concretely, this:

@dataclass
class Point:
    x: int
    y: int

is equivalent to writing this by hand:

class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
'''
#? One line summary is the JHAMELA of writing __inti__ and self for defining data is removed using the @dataclass decorator


#! Question: When do we use @dataclass ?? ,
'''

# 1.So: Booking = data container → good fit for @dataclass
# 2.Use @dataclass when the class's only job is to hold and transport data — not manage state or do work.

'''