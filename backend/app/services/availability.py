"""check_doctor_availability business logic. Never invents slots: everything comes from SQLite."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..repositories import doctors as docs
from ..repositories import slots as slot_repo
from ..utils.clock import Clock
from ..utils.dates import parse_time_text, parse_time_window, to_12h
from .rules import Rules


def future_times(conn, clock: Clock, rules: Rules, doctor_id: int, iso: str) -> list[str]:
    times = slot_repo.available_times(conn, doctor_id, iso)
    if iso == clock.today().isoformat():
        cutoff = clock.now() + timedelta(minutes=rules.min_lead_minutes)
        times = [t for t in times if clock.slot_dt(iso, t) >= cutoff]
    return times


def next_dates(conn, clock: Clock, rules: Rules, doctor_id: int, after_iso: str | None = None, n: int = 5) -> list[str]:
    start = after_iso or clock.today().isoformat()
    out = []
    for iso in slot_repo.available_dates(conn, doctor_id, start, 60):
        if after_iso and iso <= after_iso:
            continue
        if future_times(conn, clock, rules, doctor_id, iso):
            out.append(iso)
        if len(out) >= n:
            break
    return out


def _rank(times: list[str], preferred: str | None, window: tuple[str, str] | None) -> tuple[list[str], bool]:
    """Order slots by closeness to a preferred time / inside a daypart. Returns (times, preference_met)."""
    if window:
        inside = [t for t in times if window[0] <= t < window[1]]
        return (inside or times), bool(inside)
    if preferred:
        key = lambda t: abs(int(t[:2]) * 60 + int(t[3:]) - (int(preferred[:2]) * 60 + int(preferred[3:])))
        return sorted(times, key=key), preferred in times
    return times, True


def check_availability(conn, clock: Clock, rules: Rules, *, doctor_id: int | None = None, doctor_name: str | None = None,
                       speciality: str | None = None, date_iso: str | None = None, preferred_time: str | None = None,
                       earliest: bool = False, max_slots: int = 6) -> dict:
    today = clock.today()
    # ---- who?
    candidates: list[dict]
    if doctor_id is not None:
        d = docs.get_doctor(conn, doctor_id)
        if not d or not d["active"]:
            return {"ok": False, "status": "INVALID_DOCTOR", "message": f"No doctor with id {doctor_id}.",
                    "available_specialities": docs.specialities(conn)}
        candidates = [d]
    elif doctor_name:
        candidates = docs.find_doctors_by_name(conn, doctor_name)
        if not candidates:
            return {"ok": False, "status": "DOCTOR_NOT_FOUND",
                    "message": f"No doctor matching '{doctor_name}'. Suggest the doctors listed.",
                    "doctors": [{"doctor_id": x["id"], "name": x["name"], "speciality": x["speciality"]} for x in docs.list_doctors(conn)]}
    elif speciality:
        spec = docs.resolve_speciality(conn, speciality)
        if not spec:
            return {"ok": False, "status": "SPECIALITY_NOT_FOUND",
                    "message": f"'{speciality}' is not a speciality we offer. Ask the caller to choose one.",
                    "available_specialities": docs.specialities(conn)}
        candidates = docs.doctors_in_speciality(conn, spec)
    else:
        return {"ok": False, "status": "NEED_DOCTOR_OR_SPECIALITY",
                "message": "Ask the caller which doctor or speciality they need.",
                "available_specialities": docs.specialities(conn)}

    pref = parse_time_text(preferred_time) if preferred_time else None
    window = parse_time_window(preferred_time) if preferred_time and not pref else None
    horizon_last = today + timedelta(days=rules.horizon_days - 1)

    # ---- earliest / no date: scan forward
    if earliest or not date_iso:
        results = []
        for d in candidates:
            dates = next_dates(conn, clock, rules, d["id"], n=5)
            if not dates:
                continue
            first = dates[0]
            ts, _ = _rank(future_times(conn, clock, rules, d["id"], first), pref, window)
            results.append(_doctor_block(d, first, ts, max_slots, dates))
        if not results:
            return {"ok": True, "status": "NO_SLOTS", "message": "No availability in the booking window for this selection.",
                    "doctors": [], "available_specialities": docs.specialities(conn)}
        results.sort(key=lambda r: (r["date"], r["slots"][0]["time"] if r["slots"] else "99"))
        if earliest:
            results = results[:1]
        return {"ok": True, "status": "OK", "message": "Earliest availability." if earliest else "Next available dates.",
                "doctors": results}

    # ---- specific date
    try:
        day = date.fromisoformat(date_iso)
    except ValueError:
        return {"ok": False, "status": "INVALID_DATE", "message": "Date must be YYYY-MM-DD."}
    if day < today:
        return {"ok": False, "status": "PAST_DATE", "message": "That date is in the past. Ask for a future date."}
    if day > horizon_last:
        return {"ok": False, "status": "DATE_OUT_OF_RANGE",
                "message": f"Bookings open up to {horizon_last.isoformat()}. Ask for an earlier date."}
    hol = docs.holiday_on(conn, date_iso)
    if hol:
        alt = [{"doctor_id": d["id"], "name": d["name"], "next_dates": next_dates(conn, clock, rules, d["id"], date_iso, 3)} for d in candidates]
        return {"ok": True, "status": "HOLIDAY", "message": f"The clinic is closed on {date_iso} ({hol}).", "doctors": [], "alternatives": alt}

    results, reasons = [], []
    for d in candidates:
        leave = docs.leave_on(conn, d["id"], date_iso)
        if leave:
            reasons.append(f"{d['name']} is unavailable on {date_iso} ({leave}).")
            continue
        if not docs.schedule_for(conn, d["id"], day.weekday()):
            reasons.append(f"{d['name']} does not work on {day.strftime('%A')}s.")
            continue
        times = future_times(conn, clock, rules, d["id"], date_iso)
        if not times:
            reasons.append(f"{d['name']} is fully booked on {date_iso}.")
            continue
        ranked, met = _rank(times, pref, window)
        block = _doctor_block(d, date_iso, ranked, max_slots, [])
        block["preferred_time_available"] = met
        results.append(block)
    if results:
        return {"ok": True, "status": "OK", "message": "Availability found.", "doctors": results, "notes": reasons}
    alt = [{"doctor_id": d["id"], "name": d["name"], "next_dates": next_dates(conn, clock, rules, d["id"], date_iso, 3)} for d in candidates]
    return {"ok": True, "status": "NO_SLOTS", "message": "No free slots on that date. Offer the alternatives.",
            "doctors": [], "notes": reasons, "alternatives": alt}


def _doctor_block(d: dict, iso: str, times: list[str], max_slots: int, dates: list[str]) -> dict:
    return {"doctor_id": d["id"], "name": d["name"], "speciality": d["speciality"],
            "experience_years": d["experience_years"], "consultation_fee": d["consultation_fee"],
            "date": iso, "total_free_slots": len(times),
            "slots": [{"time": t, "spoken": to_12h(t)} for t in times[:max_slots]],
            "available_dates": dates}
