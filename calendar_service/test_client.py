# from calendar_service.client import get_service

# service = get_service()
# events = service.events().list(calendarId="primary", maxResults=3).execute()
# print([e.get("summary") for e in events.get("items", [])])

# from calendar_service.calendar_tools import check_availability
# print(check_availability("2026-10-05"))


# from calendar_service.calendar_tools import book_slot
# print(book_slot("2026-10-07", "15:00", "Prabhat"))


from calendar_service.calendar_tools import cancel_booking
print(cancel_booking("kv1g8266fjs4htkra1stqn7968"))


from calendar_service.calendar_tools import book_slot, reschedule
b = book_slot("2026-10-07", "15:00", "Prabhat")
print(b)

print(reschedule(b["booking_id"], "2026-10-08", "11:00"))