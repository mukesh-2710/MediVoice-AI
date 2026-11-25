"""Spoken phone-number normalisation and validation (untrusted input)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
# common speech-to-text homophones; only accepted when sandwiched between real digits
_SLIPS = {"to": "2", "too": "2", "for": "4", "ate": "8", "won": "1"}
_MULT = {"double": 2, "triple": 3}
_IGNORE = {"plus", "country", "code", "number", "is", "my", "its", "it's", "the", "and", "uh", "um", "dash", "hyphen"}


@dataclass(frozen=True)
class PhoneResult:
    ok: bool
    digits: str = ""
    reason: str = ""          # EMPTY | TOO_SHORT | TOO_LONG | INVALID_PREFIX | UNCLEAR
    message: str = ""
    unrecognised: int = 0

    @property
    def readback(self) -> str:
        return speak_digits(self.digits)


def speak_digits(digits: str) -> str:
    """'9876543210' -> '9 8 7 6 5, 4 3 2 1 0' so TTS reads digit by digit with a pause."""
    if len(digits) == 10:
        return " ".join(digits[:5]) + ", " + " ".join(digits[5:])
    return " ".join(digits)


def extract_digits(text: str) -> tuple[str, int]:
    """Return (digits, unrecognised_token_count) from digits or spoken-digit words."""
    tokens = re.findall(r"[a-zA-Z']+|\d+", text.lower())
    out: list[str] = []
    unknown = 0
    mult = 1

    def digit_like(tok: str) -> bool:
        return tok.isdigit() or tok in _WORDS

    for i, tok in enumerate(tokens):
        if tok.isdigit():
            out.append(tok * mult)
            mult = 1
        elif tok in _MULT:
            mult = _MULT[tok]
        elif tok in _WORDS:
            out.append(_WORDS[tok] * mult)
            mult = 1
        elif tok in _SLIPS and 0 < i < len(tokens) - 1 and digit_like(tokens[i - 1]) and digit_like(tokens[i + 1]):
            out.append(_SLIPS[tok] * mult)
            mult = 1
        elif tok in _IGNORE:
            continue
        else:
            unknown += 1
    return "".join(out), unknown


def validate_phone(text: str, region: str = "IN") -> PhoneResult:
    """Normalise whatever the caller said into a canonical 10-digit national number."""
    if not isinstance(text, str) or not text.strip():
        return PhoneResult(False, reason="EMPTY", message="No phone number was heard. Ask the caller to say their number.")
    digits, unknown = extract_digits(text)
    if region == "IN":
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 13 and digits.startswith("091"):
            digits = digits[3:]
        elif len(digits) == 14 and digits.startswith("0091"):
            digits = digits[4:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
    if not digits:
        return PhoneResult(False, reason="UNCLEAR", unrecognised=unknown,
                           message="No digits were recognised. Ask the caller to repeat the number slowly.")
    if len(digits) < 10:
        return PhoneResult(False, digits, "TOO_SHORT", unrecognised=unknown,
                           message=f"Only {len(digits)} digits were heard; a valid number has 10. Ask the caller to repeat the full number.")
    if len(digits) > 10:
        return PhoneResult(False, digits, "TOO_LONG", unrecognised=unknown,
                           message=f"{len(digits)} digits were heard; a valid number has 10. Ask the caller to repeat the number.")
    if region == "IN" and digits[0] not in "6789":
        return PhoneResult(False, digits, "INVALID_PREFIX", unrecognised=unknown,
                           message="Mobile numbers here start with 6, 7, 8 or 9. Ask the caller to repeat the number.")
    return PhoneResult(True, digits, unrecognised=unknown)


def mask_phone(digits: str) -> str:
    return digits[:2] + "\u2022" * (len(digits) - 5) + digits[-3:] if len(digits) >= 7 else digits
