"""Spoken date / time parsing. All input is untrusted (it comes from speech and from the LLM)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_WEEKDAYS = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
_WEEKDAYS.update({k[:3]: v for k, v in list(_WEEKDAYS.items())})
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))


@dataclass(frozen=True)
class DateResult:
    ok: bool
    value: date | None = None
    reason: str = ""            # INVALID | PAST | AMBIGUOUS | EMPTY
    message: str = ""
    assumed: bool = False       # interpretation involved a guess -> agent should confirm aloud
    options: list[str] = field(default_factory=list)


def normalize_spoken_date(text: str, today: date, allow_past: bool = False) -> DateResult:
    if not isinstance(text, str) or not text.strip():
        return DateResult(False, reason="EMPTY", message="No date was given. Ask the caller which day they want.")
    t = re.sub(r"[,.]", " ", text.lower()).strip()
    t = re.sub(r"\s+", " ", t)

    def done(d: date, assumed: bool = False) -> DateResult:
        if d < today and not allow_past:
            return DateResult(False, d, "PAST", f"{d.isoformat()} is in the past. Ask for a future date.")
        return DateResult(True, d, assumed=assumed)

    # relative words
    if re.search(r"\bday after tomorrow\b", t):
        return done(today + timedelta(days=2))
    if re.search(r"\btomorrow\b", t):
        return done(today + timedelta(days=1))
    if re.search(r"\b(today|tonight|this evening|this afternoon|this morning)\b", t):
        return done(today)
    if re.search(r"\byesterday\b", t):
        return DateResult(False, today - timedelta(days=1), "PAST", "Yesterday is in the past. Ask for a future date.")
    m = re.search(r"\bin (\d{1,2}) days?\b", t)
    if m:
        return done(today + timedelta(days=int(m.group(1))))
    if re.search(r"\bnext week\b", t):
        return done(today + timedelta(days=7), assumed=True)

    # ISO yyyy-mm-dd
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return done(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            return DateResult(False, reason="INVALID", message="That date does not exist. Ask the caller to repeat it.")

    # numeric d/m[/y] or m/d[/y]
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y += 2000 if y < 100 else 0
        cands: list[date] = []
        for day, mon in ((a, b), (b, a)):
            try:
                cand = date(y, mon, day)
                if cand not in cands:
                    cands.append(cand)
            except ValueError:
                pass
        if not cands:
            return DateResult(False, reason="INVALID", message="That date does not exist. Ask the caller to repeat it.")
        if len(cands) == 2:
            return DateResult(False, reason="AMBIGUOUS",
                              message="The numeric date could mean two different days. Ask the caller which one.",
                              options=[c.isoformat() for c in cands])
        return done(cands[0])

    # '27 november [2026]' / '27th of november'
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? ({_MONTH_RE})\b(?: (\d{{4}}))?", t)
    m2 = re.search(rf"\b({_MONTH_RE}) (\d{{1,2}})(?:st|nd|rd|th)?\b(?: (\d{{4}}))?", t)
    if m or m2:
        if m:
            day, mon, yr = int(m.group(1)), _MONTHS[m.group(2)], m.group(3)
        else:
            mon, day, yr = _MONTHS[m2.group(1)], int(m2.group(2)), m2.group(3)
        try:
            return done(date(int(yr) if yr else today.year, mon, day))
        except ValueError:
            return DateResult(False, reason="INVALID", message="That date does not exist. Ask the caller to repeat it.")

    # weekday names
    m = re.search(rf"\b(next |this |coming )?({'|'.join(sorted(_WEEKDAYS, key=len, reverse=True))})\b", t)
    if m:
        target = _WEEKDAYS[m.group(2)]
        ahead = (target - today.weekday()) % 7
        if ahead == 0:
            ahead = 7
        if m.group(1) and m.group(1).strip() == "next" and ahead <= 6 - today.weekday():
            ahead += 7
        return done(today + timedelta(days=ahead), assumed=True)

    return DateResult(False, reason="INVALID", message="The date was not understood. Ask the caller for a day such as 'tomorrow' or 'Friday'.")


# ---------------------------------------------------------------- times
DAYPARTS = {"morning": ("08:00", "12:00"), "afternoon": ("12:00", "17:00"), "evening": ("17:00", "21:00")}


def parse_time_text(text: str) -> str | None:
    """'11 am' -> '11:00', '3:30 pm' -> '15:30', '15:00' -> '15:00', 'noon' -> '12:00'. None if unparseable."""
    if not isinstance(text, str):
        return None
    t = text.lower().strip().replace(".", "")
    if t == "noon":
        return "12:00"
    m = re.fullmatch(r"(?:at )?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?: o'?clock)?", t)
    if not m:
        m4 = re.fullmatch(r"(\d{2})(\d{2})", t)
        if m4 and int(m4.group(1)) < 24 and int(m4.group(2)) < 60:
            return f"{int(m4.group(1)):02d}:{m4.group(2)}"
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if mi > 59 or h > 23:
        return None
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    elif ap is None and h <= 12 and not m.group(2):
        # bare hour with no am/pm: clinic hours heuristic
        if 1 <= h <= 6 or h == 12:
            h = h + 12 if h < 12 else 12
    return f"{h:02d}:{mi:02d}"


def parse_time_window(text: str) -> tuple[str, str] | None:
    if not isinstance(text, str):
        return None
    t = text.lower()
    for k, v in DAYPARTS.items():
        if k in t:
            return v
    return None


def to_12h(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def speak_date(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return d.strftime("%A, %d %B").replace(" 0", " ")
