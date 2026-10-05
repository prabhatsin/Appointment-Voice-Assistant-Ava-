# from calendar_service.client import get_service

# service = get_service()
# events = service.events().list(calendarId="primary", maxResults=3).execute()
# print([e.get("summary") for e in events.get("items", [])])

# from calendar_service.calendar_tools import check_availability
# print(check_availability("2026-10-05"))


# from calendar_service.calendar_tools import book_slot
# print(book_slot("2026-10-07", "15:00", "Prabhat"))


from calendar_service.calendar_tools import cancel_booking
print(cancel_booking("3hl9lo1363gpapp5ee3hh95750"))


# from calendar_service.calendar_tools import book_slot, reschedule
# b = book_slot("2026-10-07", "15:00", "Prabhat")
# print(b)

# print(reschedule(b["booking_id"], "2026-10-08", "11:00"))
# from calendar_service.client import get_service

# r = get_service().events().list(
#     calendarId="primary",
#     timeMin="2026-10-05T00:00:00+05:30",
#     timeMax="2026-10-06T00:00:00+05:30",
#     singleEvents=True,
# ).execute()
# for e in r["items"]:
#     print(e["id"], e.get("summary"), e["start"].get("dateTime"), e.get("created"))