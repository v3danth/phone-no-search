"""Tests for phonelookup.py and the data scripts.

Every number here is one of libphonenumber's published example numbers or
a fictional US 555-01xx number, never a real person's number.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import merge  # noqa: E402
import parse_wiki  # noqa: E402
import phonelookup  # noqa: E402

IN_MOBILE = "918123456789"   # libphonenumber example, prefix 8123 not in table
IN_SERIES = "917410410123"   # libphonenumber example, prefix 7410 in table
US_FICTIONAL = "12015550123"


class LookupTest(unittest.TestCase):
    def test_indian_mobile_uses_series_table(self):
        result = phonelookup.lookup(IN_SERIES)
        self.assertTrue(result["valid"])
        self.assertEqual(result["line_type"], "mobile")
        self.assertEqual(result["location"], "Rajasthan")
        self.assertEqual(result["carrier"], "Vodafone Idea (Vi)")
        self.assertEqual(result["series_source"], "wikipedia")

    def test_indian_mobile_outside_table_has_no_source(self):
        result = phonelookup.lookup(IN_MOBILE)
        self.assertTrue(result["valid"])
        self.assertNotIn("series_source", result)

    def test_formats(self):
        result = phonelookup.lookup("+" + US_FICTIONAL)
        self.assertEqual(result["number"], US_FICTIONAL)
        self.assertEqual(result["international_format"], "+" + US_FICTIONAL)
        self.assertEqual(result["local_format"], "2015550123")
        self.assertEqual(result["country_code"], "US")

    def test_invalid_inputs(self):
        unparsable = phonelookup.lookup(" 12 ")
        self.assertFalse(unparsable["valid"])
        self.assertEqual(unparsable["number"], "12")
        self.assertIn("error", unparsable)
        self.assertFalse(phonelookup.lookup("abc")["valid"])
        self.assertFalse(phonelookup.lookup("910000000000")["valid"])


class AgreementTest(unittest.TestCase):
    def test_partial_location_and_first_word_carrier_match(self):
        ours = {"valid": True, "line_type": "mobile",
                "location": "Andhra Pradesh & Telangana", "carrier": "Reliance Jio"}
        theirs = {"valid": True, "line_type": "mobile",
                  "location": "Telangana", "carrier": "Reliance Jio Infocomm Ltd"}
        self.assertEqual(phonelookup.agreement(ours, theirs),
                         {"valid": True, "line_type": True,
                          "location": True, "carrier": True})

    def test_missing_remote_values_do_not_match(self):
        ours = {"valid": True, "line_type": "mobile", "location": "X", "carrier": "Y"}
        result = phonelookup.agreement(ours, {"valid": True})
        self.assertFalse(result["location"])
        self.assertFalse(result["carrier"])


class DorkTest(unittest.TestCase):
    def test_output_is_deterministic_and_complete(self):
        query = phonelookup.dork(US_FICTIONAL)
        self.assertEqual(query, phonelookup.dork(US_FICTIONAL))
        for form in ("2015550123", "+12015550123", "201-555-0123", "(201) 555-0123"):
            self.assertIn(f'"{form}"', query)

    def test_indian_spaced_form(self):
        self.assertIn('"81234 56789"', phonelookup.dork(IN_MOBILE))


class ExpandCodesTest(unittest.TestCase):
    def test_split_block_and_unknown_code(self):
        self.assertEqual(phonelookup.expand_codes("BR/WB/ZZ", phonelookup.IN_CIRCLES),
                         "Bihar & Jharkhand / West Bengal")


class ParseWikiTest(unittest.TestCase):
    def test_missing_values_and_markup(self):
        text = "\n".join([
            "intro", "==Call No Series==", '{| class="wikitable"', "|+ caption",
            "|-", "| 9000 || AT || AP", "|-", "| 9001 || RJ", "| 9002",
            "| 9003 || VI || BR/WB", "|}", "== See also ==", "| 9999 || XX || YY",
        ])
        cells = parse_wiki.table_cells(parse_wiki.series_section(text))
        self.assertEqual(parse_wiki.series_entries(cells), {
            "9000": ("AT", "AP"),
            "9001": ("RJ", ""),
            "9002": ("", ""),
            "9003": ("VI", "BR/WB"),
        })


class MergeTest(unittest.TestCase):
    def test_priority(self):
        self.assertEqual(merge.merged_row(("AT", "AP"), ("RJ", "KA")),
                         ("AT", "AP", "wikipedia"))
        self.assertEqual(merge.merged_row(("RJ", ""), ("RJ", "KA")),
                         ("RJ", "KA", "in-mob-prefix"))
        self.assertEqual(merge.merged_row(("xx", "KA"), ("", "")),
                         ("", "KA", "partial"))
        self.assertIsNone(merge.merged_row(("", ""), ("", "")))

    def test_clean_codes_dedupes_and_drops_notes(self):
        self.assertEqual(merge.clean_codes("BR/WB/BR/note"), "BR/WB")


if __name__ == "__main__":
    unittest.main()
