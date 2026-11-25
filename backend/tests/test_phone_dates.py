import unittest
from datetime import date

from app.utils.confirm import is_affirmative, is_negative
from app.utils.dates import normalize_spoken_date, parse_time_text, to_12h
from app.utils.phone import speak_digits, validate_phone

T = date(2026, 11, 24)  # Tuesday


class PhoneTests(unittest.TestCase):
    def test_plain_digits(self):
        self.assertEqual(validate_phone("9876543210").digits, "9876543210")

    def test_spoken_in_groups_and_words(self):
        self.assertEqual(validate_phone("98765 43210").digits, "9876543210")
        self.assertEqual(validate_phone("nine eight seven six five four three two one zero").digits, "9876543210")
        self.assertEqual(validate_phone("9 8 7 6 5 - 4 3 2 1 0").digits, "9876543210")

    def test_country_code_stripped(self):
        self.assertEqual(validate_phone("+91 98765 43210").digits, "9876543210")
        self.assertEqual(validate_phone("09876543210").digits, "9876543210")

    def test_double_and_triple(self):
        self.assertEqual(validate_phone("double nine eight seven six five four three two one").digits, "9987654321")

    def test_too_short_and_long(self):
        self.assertEqual(validate_phone("98765").reason, "TOO_SHORT")
        self.assertEqual(validate_phone("98765432101").reason, "TOO_LONG")

    def test_invalid_prefix_and_unclear_and_empty(self):
        self.assertEqual(validate_phone("5876543210").reason, "INVALID_PREFIX")
        self.assertEqual(validate_phone("hello there").reason, "UNCLEAR")
        self.assertEqual(validate_phone("   ").reason, "EMPTY")
        self.assertFalse(validate_phone(None).ok)  # type: ignore[arg-type]

    def test_stt_homophone_only_between_digits(self):
        self.assertEqual(validate_phone("nine eight seven six five to three two one zero").digits, "9876523210")
        self.assertFalse(validate_phone("to").ok)

    def test_readback(self):
        self.assertEqual(speak_digits("9876543210"), "9 8 7 6 5, 4 3 2 1 0")


class DateTests(unittest.TestCase):
    def test_relative(self):
        self.assertEqual(normalize_spoken_date("tomorrow", T).value, date(2026, 11, 25))
        self.assertEqual(normalize_spoken_date("today", T).value, T)
        self.assertEqual(normalize_spoken_date("day after tomorrow", T).value, date(2026, 11, 26))

    def test_past(self):
        r = normalize_spoken_date("yesterday", T)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "PAST")
        self.assertEqual(normalize_spoken_date("2026-11-01", T).reason, "PAST")

    def test_weekday_is_flagged_as_assumed(self):
        r = normalize_spoken_date("Friday", T)
        self.assertEqual(r.value, date(2026, 11, 27))
        self.assertTrue(r.assumed)
        self.assertEqual(normalize_spoken_date("next friday", T).value, date(2026, 12, 4))

    def test_named_month(self):
        self.assertEqual(normalize_spoken_date("27th November", T).value, date(2026, 11, 27))
        self.assertEqual(normalize_spoken_date("December 3", T).value, date(2026, 12, 3))

    def test_ambiguous_numeric(self):
        r = normalize_spoken_date("03/04/2026", T)
        self.assertEqual(r.reason, "AMBIGUOUS")
        self.assertEqual(len(r.options), 2)

    def test_invalid(self):
        self.assertEqual(normalize_spoken_date("31/02", T).reason, "INVALID")
        self.assertEqual(normalize_spoken_date("blah", T).reason, "INVALID")
        self.assertEqual(normalize_spoken_date("", T).reason, "EMPTY")

    def test_times(self):
        self.assertEqual(parse_time_text("11 am"), "11:00")
        self.assertEqual(parse_time_text("3 pm"), "15:00")
        self.assertEqual(parse_time_text("15:30"), "15:30")
        self.assertEqual(parse_time_text("25:00"), None)
        self.assertEqual(to_12h("15:30"), "3:30 PM")


class ConfirmTests(unittest.TestCase):
    def test_affirmative(self):
        for t in ["Yes", "yeah that's right", "Yes, please book it", "correct", "Okay"]:
            self.assertTrue(is_affirmative(t), t)

    def test_not_affirmative(self):
        for t in ["No", "no that's wrong", "yes but actually make it Friday", "wait", "9876543210", ""]:
            self.assertFalse(is_affirmative(t), t)
        self.assertTrue(is_negative("nope"))


if __name__ == "__main__":
    unittest.main()
