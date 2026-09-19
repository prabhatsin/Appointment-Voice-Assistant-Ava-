
#! This file contains the ,  mapping of tool call and defined tools(functions)

from agent_core.tools import check_availability, book_slot, cancel_booking, reschedule

tool_registry = {
    "check_availability": check_availability,
    "book_slot": book_slot,
    "cancel_booking": cancel_booking,
    "reschedule": reschedule,
}