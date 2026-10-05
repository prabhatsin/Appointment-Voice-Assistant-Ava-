from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from calendar_service.client import get_service
from calendar_service.config import (
    TIMEZONE, WORK_START, WORK_END, SLOT_MINUTES, CALENDAR_ID
)
from googleapiclient.errors import HttpError


TZ = ZoneInfo(TIMEZONE)

def check_availability(date: str) -> list:
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=TZ)
    day_start = day.replace(hour=WORK_START)
    day_end = day.replace(hour=WORK_END)

    result = get_service().events().list(
        calendarId=CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    busy = []
    for e in result.get("items", []):
        if e.get("status") == "cancelled" or e.get("transparency") == "transparent":
            continue
        start, end = e["start"].get("dateTime"), e["end"].get("dateTime")
        if not start:  # all-day event, ignored for now
            continue
        busy.append((datetime.fromisoformat(start).astimezone(TZ),
                     datetime.fromisoformat(end).astimezone(TZ)))

    now = datetime.now(TZ)
    slots = []
    slot = day_start
    while slot + timedelta(minutes=SLOT_MINUTES) <= day_end:
        slot_end = slot + timedelta(minutes=SLOT_MINUTES)
        overlaps = any(slot < b_end and slot_end > b_start for b_start, b_end in busy)
        if not overlaps and slot > now:
            slots.append(slot.strftime("%H:%M"))
        slot = slot_end
    return slots



PLACEHOLDER_NAMES = {"user", "guest", "unknown", "customer", "n/a", "na", "none", "anonymous", "name"}

def book_slot(date: str, time: str, name: str) -> dict:
    cleaned = (name or "").strip()
    if len(cleaned) < 2 or cleaned.lower() in PLACEHOLDER_NAMES:
        return {"status": "error", "message": "Name missing. Ask the user for their real name before booking."}

    try:
        start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except ValueError:
        return {"status": "error", "message": "Invalid date or time format. Use YYYY-MM-DD and HH:MM."}

    if start <= datetime.now(TZ):
        return {"status": "error", "message": "That time has already passed. Ask for a future time."}

    if time not in check_availability(date):
        return {"status": "error", "message": f"{time} on {date} is not available. Offer another slot."}

    start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    end = start + timedelta(minutes=SLOT_MINUTES)

    event = get_service().events().insert(
        calendarId=CALENDAR_ID,
        body={
            "summary": f"Appointment: {cleaned}",
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        },
    ).execute()

    return {"status": "success", "booking_id": event["id"], "date": date, "time": time}



def cancel_booking(booking_id: str) -> dict:
    try:
        get_service().events().delete(
            calendarId=CALENDAR_ID, eventId=booking_id
        ).execute()
        return {"status": "success", "booking_id": booking_id}
    except HttpError as e:
        if e.resp.status in (404, 410):
            return {"status": "error", "message": "No booking found with that ID."}
        raise


def reschedule(booking_id: str, new_date: str, new_time: str) -> dict:
    
    try:
        start = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except ValueError:
        return {"status": "error", "message": "Invalid date or time format. Use YYYY-MM-DD and HH:MM."}

    if new_time not in check_availability(new_date):
        return {"status": "error", "message": f"{new_time} on {new_date} is not available. Offer another slot."}

    start = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    end = start + timedelta(minutes=SLOT_MINUTES)

    try:
        get_service().events().patch(
            calendarId=CALENDAR_ID,
            eventId=booking_id,
            body={
                "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
            },
        ).execute()
        return {"status": "success", "booking_id": booking_id, "date": new_date, "time": new_time}
    except HttpError as e:
        if e.resp.status in (404, 410):
            return {"status": "error", "message": "No booking found with that ID."}
        raise


