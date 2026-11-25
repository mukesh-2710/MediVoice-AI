"""Deterministic yes/no detection on the *transcribed caller utterance*.

The LLM is never trusted to say "the caller confirmed". Sensitive tool calls only run
when the server itself saw an affirmative caller utterance.
"""
from __future__ import annotations

import re

_NEG = re.compile(
    r"\b(no|nope|nah|not|don'?t|dont|wait|wrong|incorrect|actually|change|stop|hold on|never ?mind|negative|different)\b")
_POS = re.compile(
    r"\b(yes|yeah|yep|yup|yea|correct|right|sure|confirm(ed)?|go ahead|please do|do it|book it|cancel it|"
    r"that'?s right|that is right|that is correct|that'?s correct|okay|ok|absolutely|exactly|perfect|proceed)\b")


def _clean(text: str) -> str:
    return re.sub(r"[^a-z' ]+", " ", (text or "").lower()).strip()


def is_negative(text: str) -> bool:
    return bool(_NEG.search(_clean(text)))


def is_affirmative(text: str) -> bool:
    t = _clean(text)
    if not t or len(t.split()) > 12:   # long utterances are not a bare confirmation
        return False
    return bool(_POS.search(t)) and not _NEG.search(t)
