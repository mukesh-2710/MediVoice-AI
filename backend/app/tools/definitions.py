"""LLM-facing tool schemas. Names of the three required tools must not change.

`call_session_id` is deliberately NOT a model argument: the server injects it from the live
call, so the model cannot act on (or leak data from) another call.
"""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "check_doctor_availability",
        "description": "Look up real available appointment slots. Provide a doctor name, doctor_id, or speciality. "
                       "requested_date may be words like 'tomorrow' or 'Friday' or YYYY-MM-DD. "
                       "Use earliest=true when the caller wants the first available appointment. Never state slots that this tool did not return.",
        "properties": {
            "doctor_name": {"type": "string", "description": "Doctor name as spoken, e.g. 'Sharma'."},
            "doctor_id": {"type": "integer", "description": "Doctor id from a previous result."},
            "speciality": {"type": "string", "description": "e.g. cardiologist, dermatologist, ENT, dentist."},
            "requested_date": {"type": "string", "description": "Date in the caller's words or YYYY-MM-DD. Omit to see the next available dates."},
            "preferred_time": {"type": "string", "description": "e.g. '11 am', 'morning', 'evening'."},
            "earliest": {"type": "boolean", "description": "True to find the earliest available slot."},
        },
        "required": [],
    },
    {
        "name": "record_phone_number",
        "description": "Call this as soon as the caller says their phone number. Pass exactly what they said. "
                       "It returns the normalised number you MUST read back digit by digit. Call again if they correct it.",
        "properties": {"spoken_phone": {"type": "string", "description": "The number exactly as the caller said it."}},
        "required": ["spoken_phone"],
    },
    {
        "name": "confirm_phone_number",
        "description": "Call this only AFTER you read the number back and the caller answered. is_correct=true if they said yes.",
        "properties": {"is_correct": {"type": "boolean"}},
        "required": ["is_correct"],
    },
    {
        "name": "find_my_appointments",
        "description": "List the confirmed phone number's active appointments. Requires a confirmed phone number.",
        "properties": {},
        "required": [],
    },
    {
        "name": "book_appointment",
        "description": "Two steps. Step 1: call with details_confirmed=false to validate and get a summary; read the summary to the caller and ask for a yes. "
                       "Step 2: after the caller says yes, call again with identical arguments and details_confirmed=true. "
                       "Only tell the caller it is booked if the result status is BOOKED or ALREADY_BOOKED; then quote appointment_ref.",
        "properties": {
            "doctor_id": {"type": "integer"},
            "patient_phone": {"type": "string", "description": "The confirmed phone number."},
            "appointment_date": {"type": "string", "description": "YYYY-MM-DD from a tool result."},
            "appointment_time": {"type": "string", "description": "HH:MM 24-hour from a tool result."},
            "details_confirmed": {"type": "boolean"},
        },
        "required": ["doctor_id", "patient_phone", "appointment_date", "appointment_time", "details_confirmed"],
    },
    {
        "name": "cancel_appointment",
        "description": "Two steps like booking. Step 1: details_confirmed=false (optionally with appointment_id) returns the appointment(s) or asks which one; "
                       "read it back and ask for a yes. Step 2: after yes, call again with the same appointment_id and details_confirmed=true. "
                       "Use cancel_all=true only if the caller asked to cancel everything. Only say it is cancelled if status is CANCELLED.",
        "properties": {
            "patient_phone": {"type": "string", "description": "The confirmed phone number."},
            "appointment_id": {"type": "string", "description": "Appointment id or reference such as MV-123456."},
            "cancel_all": {"type": "boolean"},
            "details_confirmed": {"type": "boolean"},
        },
        "required": ["patient_phone", "details_confirmed"],
    },
]
