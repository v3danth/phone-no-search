"""Tests for phonelookup.py and the data scripts.

Every number here is one of libphonenumber's published example numbers or
a fictional US 555-01xx number, never a real person's number.
"""

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import merge  # noqa: E402
import parse_wiki  # noqa: E402
import phonelookup  # noqa: E402

IN_MOBILE = "918123456789"   # libphonenumber example, prefix 8123 only in DoT letters
IN_SERIES = "917410410123"   # libphonenumber example: 7410 Vi Rajasthan in the
                             # series table, 74104 Airtel in libphonenumber
US_FICTIONAL = "12015550123"


class LookupTest(unittest.TestCase):
    def test_libphonenumber_block_beats_series_table(self):
        result = phonelookup.lookup(IN_SERIES)
        self.assertTrue(result["valid"])
        self.assertEqual(result["line_type"], "mobile")
        self.assertEqual(result["carrier"], "Bharti Airtel")
        self.assertEqual(result["series_source"], "libphonenumber")
        # The operators differ, so the series table's circle is not trusted.
        self.assertEqual(result["location"], "India")
        self.assertEqual([h["source"] for h in result["history"]],
                         ["wikipedia", "libphonenumber"])

    def test_series_table_alone(self):
        with mock.patch.object(phonelookup, "libphonenumber_entries", return_value=[]):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["location"], "Rajasthan")
        self.assertEqual(result["carrier"], "Vodafone Idea (Vi)")
        self.assertEqual(result["series_source"], "wikipedia")
        # Dated from data/wiki_series_history.csv: when Wikipedia first
        # showed the current value, not when the page was downloaded.
        self.assertEqual(result["updated"], "2024-10-24")

    def test_closed_operator_keeps_circle_from_dot_letter(self):
        # 81234: DoT 2012 says Tata Karnataka, libphonenumber later says Tata Docomo.
        result = phonelookup.lookup(IN_MOBILE)
        self.assertTrue(result["valid"])
        self.assertEqual(result["carrier"], "Tata Teleservices (merged into Airtel 2019)")
        self.assertEqual(result["location"], "Karnataka")

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


def use_table(test, attr, cache, text):
    """Point phonelookup.<attr> at a temp CSV holding `text` for one test."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    tmp.write(text)
    tmp.close()
    original = getattr(phonelookup, attr)
    setattr(phonelookup, attr, Path(tmp.name))
    cache.cache_clear()

    def restore():
        setattr(phonelookup, attr, original)
        cache.cache_clear()
        Path(tmp.name).unlink()
    test.addCleanup(restore)


MSC_HEADER = "block,operator,circle,date,kind,letter,note\n"


class UnallocatedTest(unittest.TestCase):
    def test_valid_mobile_with_no_source_gets_a_note(self):
        with mock.patch.object(phonelookup, "india_mobile_history", return_value=[]):
            six = phonelookup.lookup("916698012345")
            other = phonelookup.lookup("919999912345")
        self.assertTrue(six["valid"])
        self.assertIn("probably not allocated", six["note"])
        self.assertEqual(other.get("note", "no operator known for this block"),
                         "no operator known for this block")


class HistoryTest(unittest.TestCase):
    """How series, blocks-file and DoT letter rows combine. IN_SERIES's
    prefix 7410 is Vi Rajasthan in the series table."""

    def setUp(self):
        patcher = mock.patch.object(phonelookup, "libphonenumber_entries", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER)
        use_table(self, "BLOCKS_CSV", phonelookup.block_table,
                  "prefix,operator,circle,source,updated,note\n")

    def test_block_override_wins_and_history_keeps_both(self):
        use_table(self, "BLOCKS_CSV", phonelookup.block_table,
                  "prefix,operator,circle,source,updated,note\n"
                  "74104,RJ,KA,numverify,2027-01-02,test\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["carrier"], "Reliance Jio")
        self.assertEqual(result["location"], "Karnataka")
        self.assertEqual(result["series_source"], "numverify")
        self.assertEqual(result["updated"], "2027-01-02")
        self.assertEqual([h["location"] for h in result["history"]],
                         ["Rajasthan", "Karnataka"])

    def test_reused_block_ends_on_newest_letter(self):
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,AS,2026-01-01,allocation,u2,\n"
                  "74104,RCom,BR,2012-05-16,allocation,u1,\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["updated"]), ("Bharti Airtel", "2026-01-01"))
        self.assertEqual([h["source"] for h in result["history"]],
                         ["wikipedia", "dot.gov.in", "dot.gov.in"])
        self.assertEqual(result["history"][-1]["letter"], "u2")

    def test_closed_operator_falls_back_to_series_table(self):
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,Aircel,RJ,2012-05-16,allocation,u1,\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["carrier"], "Vodafone Idea (Vi)")
        self.assertEqual(result["history"][0]["carrier"], "Aircel (closed 2018)")

    def test_dated_letter_beats_libphonenumber(self):
        lib = [{"carrier": "Reliance Jio", "location": "", "source": "libphonenumber",
                "updated": "2017-01-01", "kind": "listed", "prefix": "74104", "commit": "c"}]
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,AS,2026-01-01,allocation,u1,\n")
        with mock.patch.object(phonelookup, "libphonenumber_entries", return_value=lib):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["location"]), ("Bharti Airtel", "Assam"))
        self.assertEqual([h["source"] for h in result["history"]],
                         ["wikipedia", "libphonenumber", "dot.gov.in"])

    def test_libphonenumber_circle_comes_from_same_operator(self):
        lib = [{"carrier": "Bharti Airtel", "location": "", "source": "libphonenumber",
                "updated": "2017-01-01", "kind": "listed", "prefix": "74104", "commit": "c"}]
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,AS,2016-01-01,allocation,u1,\n")
        with mock.patch.object(phonelookup, "libphonenumber_entries", return_value=lib):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["location"]), ("Bharti Airtel", "Assam"))
        self.assertEqual(result["series_source"], "libphonenumber")

    def test_withdrawal_is_not_the_answer(self):
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,RJ,2012-05-16,allocation,u1,\n"
                  "74104,AT,RJ,2015-01-01,withdrawal,u2,\n")
        self.assertEqual(phonelookup.lookup(IN_SERIES)["series_source"], "wikipedia")


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


class SeriesHistoryTest(unittest.TestCase):
    def test_earlier_values_are_superseded_and_current_is_dated(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        tmp.write("prefix,operator,circle,since,until,since_ref,until_ref\n"
                  "7410,Aircel,RJ,2010-01-01,2015-01-01,1,2\n"
                  "7410,VI,RJ,2015-01-01,,2,\n")
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        phonelookup.series_history.cache_clear()
        self.addCleanup(phonelookup.series_history.cache_clear)
        with mock.patch.dict(phonelookup.SERIES_HISTORY_CSV, {"wikipedia": Path(tmp.name)}), \
                mock.patch.object(phonelookup, "libphonenumber_entries", return_value=[]):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["updated"]), ("Vodafone Idea (Vi)", "2015-01-01"))
        first = result["history"][0]
        self.assertEqual((first["carrier"], first["kind"], first["until"]),
                         ("Aircel (closed 2018)", "superseded", "2015-01-01"))
        self.assertFalse(phonelookup.is_current(first))


class LibphonenumberHistoryTest(unittest.TestCase):
    def setUp(self):
        use_table(self, "LIBPN_CSV", phonelookup.libpn_table,
                  "prefix,carrier,since,until,since_commit,until_commit\n"
                  "7410,RELIANCE,2013-01-01,2015-01-01,a,b\n"
                  "7410,Reliance,2015-01-01,2018-01-01,b,c\n"
                  "74104,Airtel,2016-01-01,,d,\n")

    def test_longest_prefix_spelling_and_removal(self):
        entries = phonelookup.libphonenumber_entries("7410410123")
        self.assertEqual([(e["updated"], e["kind"], e["prefix"]) for e in entries],
                         [("2013-01-01", "listed", "7410"), ("2016-01-01", "listed", "74104")])
        other = phonelookup.libphonenumber_entries("7410510123")
        self.assertEqual([(e["updated"], e["kind"]) for e in other],
                         [("2013-01-01", "listed"), ("2018-01-01", "removed")])
        self.assertFalse(phonelookup.is_current(other[-1]))


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
