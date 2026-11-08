"""Tests for phonelookup.py and the data scripts.

Every number here is one of libphonenumber's published example numbers or
a fictional US 555-01xx number, never a real person's number.
"""

import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

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
        with mock.patch.object(phonelookup.history, "libphonenumber_entries", return_value=[]):
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
    """Point phonelookup.constants.<attr> at a temp CSV holding `text`.

    The loaders read the path from the constants module, so the override lives
    there; the matching lru_cache is cleared around the test.
    """
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)  # noqa: SIM115
    tmp.write(text)
    tmp.close()
    original = getattr(phonelookup.constants, attr)
    setattr(phonelookup.constants, attr, Path(tmp.name))
    cache.cache_clear()

    def restore():
        setattr(phonelookup.constants, attr, original)
        cache.cache_clear()
        Path(tmp.name).unlink()
    test.addCleanup(restore)


MSC_HEADER = "block,operator,circle,date,kind,letter,note\n"


class UnallocatedTest(unittest.TestCase):
    def test_valid_mobile_with_no_source_gets_a_note(self):
        known = [{"carrier": "Bharti Airtel", "location": "", "source": "x",
                  "updated": "", "kind": "listed"}]

        def neighbours_known(national):
            return [] if national == "9999912345" else known

        with mock.patch.object(phonelookup.history, "india_mobile_history", return_value=[]):
            six = phonelookup.lookup("916698012345")
            empty_prefix = phonelookup.lookup("919999912345")
        with mock.patch.object(phonelookup.history, "india_mobile_history",
                               side_effect=neighbours_known):
            gap = phonelookup.lookup("919999912345")
        self.assertTrue(six["valid"])
        self.assertIn("probably not allocated", six["note"])
        self.assertIn("probably not allocated", empty_prefix["note"])
        self.assertEqual(gap["note"], "no operator known for this block")


class HistoryTest(unittest.TestCase):
    """How series, blocks-file and DoT letter rows combine. IN_SERIES's
    prefix 7410 is Vi Rajasthan in the series table."""

    def setUp(self):
        patcher = mock.patch.object(phonelookup.history, "libphonenumber_entries", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER)
        use_table(self, "BLOCKS_CSV", phonelookup.block_table,
                  "prefix,operator,circle,source,updated,note\n")
        use_table(self, "COAI_CSV", phonelookup.coai_table, "block,operator,circle,listed_as\n")
        use_table(self, "LEVELS2011_CSV", phonelookup.levels2011_table,
                  "level,operator,circle\n")

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
        with mock.patch.object(phonelookup.history, "libphonenumber_entries", return_value=lib):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["location"]), ("Bharti Airtel", "Assam"))
        self.assertEqual([h["source"] for h in result["history"]],
                         ["wikipedia", "libphonenumber", "dot.gov.in"])

    def test_libphonenumber_circle_comes_from_same_operator(self):
        lib = [{"carrier": "Bharti Airtel", "location": "", "source": "libphonenumber",
                "updated": "2017-01-01", "kind": "listed", "prefix": "74104", "commit": "c"}]
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,AS,2016-01-01,allocation,u1,\n")
        with mock.patch.object(phonelookup.history, "libphonenumber_entries", return_value=lib):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["location"]), ("Bharti Airtel", "Assam"))
        self.assertEqual(result["series_source"], "libphonenumber")

    def test_closed_undated_source_never_beats_current_one(self):
        # Newest dated entry is closed; COAI (undated) names a closed one
        # too, the series table a current one: the series table answers.
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,Aircel,RJ,2012-05-16,allocation,u1,\n")
        use_table(self, "COAI_CSV", phonelookup.coai_table,
                  "block,operator,circle,listed_as\n74104,RCom,MU,Reliance\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["carrier"], "Vodafone Idea (Vi)")
        self.assertEqual(result["series_source"], "wikipedia")

    def test_withdrawal_is_not_the_answer(self):
        use_table(self, "MSC_CSV", phonelookup.msc_table, MSC_HEADER +
                  "74104,AT,RJ,2012-05-16,allocation,u1,\n"
                  "74104,AT,RJ,2015-01-01,withdrawal,u2,\n")
        self.assertEqual(phonelookup.lookup(IN_SERIES)["series_source"], "wikipedia")

    def test_scribd_2011_is_the_stalest_baseline(self):
        # The c.2011 list names a closed operator and a circle; the series
        # table (current) must still answer, but the 2011 entry stays in
        # history as the oldest baseline with its circle.
        use_table(self, "LEVELS2011_CSV", phonelookup.levels2011_table,
                  "level,operator,circle\n7410,Tata,WB\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["carrier"], "Vodafone Idea (Vi)")
        self.assertEqual(result["series_source"], "wikipedia")
        self.assertEqual(result["history"][0]["source"], "scribd-2011")
        self.assertEqual(result["history"][0]["location"], "West Bengal")

    def test_scribd_2011_fills_a_block_with_no_other_source(self):
        # Prefer a 5-digit level over a 4-digit one, and use it as the
        # answer when nothing else covers the block.
        use_table(self, "LEVELS2011_CSV", phonelookup.levels2011_table,
                  "level,operator,circle\n74104,CG,KA\n7410,AT,RJ\n")
        use_table(self, "SERIES_CSV", phonelookup.series_table,
                  "series,operator,circle,source,updated\n")
        result = phonelookup.lookup(IN_SERIES)
        self.assertEqual(result["carrier"], "BSNL/MTNL")
        self.assertEqual(result["location"], "Karnataka")
        self.assertEqual(result["series_source"], "scribd-2011")


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

    def test_urls_cover_every_engine_and_encode_the_query(self):
        query = phonelookup.dork(US_FICTIONAL)
        urls = phonelookup.dork_urls(query)
        self.assertEqual(set(urls), set(phonelookup.SEARCH_ENGINES))
        self.assertIn("duckduckgo.com", urls["DuckDuckGo"])
        self.assertIn("yandex.com", urls["Yandex"])
        self.assertTrue(all(" " not in url for url in urls.values()))


class SeriesHistoryTest(unittest.TestCase):
    def test_earlier_values_are_superseded_and_current_is_dated(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)  # noqa: SIM115
        tmp.write("prefix,operator,circle,since,until,since_ref,until_ref\n"
                  "7410,Aircel,RJ,2010-01-01,2015-01-01,1,2\n"
                  "7410,VI,RJ,2015-01-01,,2,\n")
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        phonelookup.series_history.cache_clear()
        self.addCleanup(phonelookup.series_history.cache_clear)
        with mock.patch.dict(phonelookup.SERIES_HISTORY_CSV, {"wikipedia": Path(tmp.name)}), \
                mock.patch.object(phonelookup.history, "libphonenumber_entries", return_value=[]):
            result = phonelookup.lookup(IN_SERIES)
        self.assertEqual((result["carrier"], result["updated"]),
                         ("Vodafone Idea (Vi)", "2015-01-01"))
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


class ProbeBlockTest(unittest.TestCase):
    def test_samples_span_the_block_and_are_deterministic(self):
        self.assertEqual(
            phonelookup.block_sample_numbers("83170", 3),
            ["+918317016666", "+918317050000", "+918317083333"])
        self.assertEqual(
            phonelookup.block_sample_numbers("83170", 3),
            phonelookup.block_sample_numbers("83170", 3))

    def test_circle_code_parsed_from_twilio_carrier_string(self):
        self.assertEqual(
            phonelookup.twilio_circle_code("Reliance (JIO) - Uttar Pradesh West"), "UW")
        self.assertEqual(
            phonelookup.twilio_circle_code(
                "Airtel India - Tamil Nadu (94) (Bharti Airtel)"), "TN")
        self.assertEqual(phonelookup.twilio_circle_code("Reliance (JIO)"), "")

    def test_operator_code_matches_twilio_strings(self):
        self.assertEqual(
            phonelookup.twilio_operator_code("Airtel India - TN (Bharti Airtel)"),
            "AT")
        self.assertEqual(
            phonelookup.twilio_operator_code("Reliance (JIO) - West Bengal"), "RJ")
        self.assertEqual(phonelookup.twilio_operator_code("New Telco"), "")

    def test_line_status_is_flattened_or_flagged_absent(self):
        self.assertEqual(
            phonelookup.twilio_line_status({"line_status": {"status": "reachable"}}),
            {"status": "reachable"})
        self.assertIn("error", phonelookup.twilio_line_status({}))
        self.assertIn(
            "error_code 60",
            phonelookup.twilio_line_status({"line_status": {"error_code": 60}})["error"])

    def test_optional_twilio_fields_are_requested_and_returned(self):
        body = {
            "valid": True,
            "phone_number": "+447772000001",
            "line_type_intelligence": {"carrier_name": "Example carrier"},
            "sim_swap": {"swapped_period": "PT24H", "error_code": None},
            "call_forwarding": {"call_forwarding_enabled": True, "error_code": None},
        }
        fields = ",".join((
            phonelookup.LTI_FIELD,
            phonelookup.SIM_SWAP_FIELD,
            phonelookup.CALL_FORWARDING_FIELD,
        ))
        with mock.patch.object(
                phonelookup.providers.twilio, "urlopen",
                return_value=BytesIO(json.dumps(body).encode())) as open_url:
            result = phonelookup.twilio_lookup(
                "+447772000001", "AC123", "secret", fields)

        request = open_url.call_args.args[0]
        self.assertEqual(parse_qs(urlparse(request.full_url).query)["Fields"], [fields])
        self.assertEqual(result["sim_swap"], body["sim_swap"])
        self.assertEqual(result["call_forwarding"], body["call_forwarding"])

    def test_majority_wins_over_a_ported_in_number(self):
        mobile = "mobile"
        live = {
            "+918317016666": {"valid": True, "carrier": "Reliance (JIO) - KA", "line_type": mobile},
            "+918317050000": {"valid": True, "carrier": "Reliance (JIO) - KA", "line_type": mobile},
            "+918317083333": {"valid": True, "carrier": "Airtel India (Bharti)",
                              "line_type": mobile},
        }
        with mock.patch.object(phonelookup.providers.twilio, "twilio_lookup",
                               side_effect=lambda e, s, t, f=None: live[e]):
            result = phonelookup.probe_block("83170", 3, ("S", "T"), {}, False)
        self.assertEqual(result["majority"], "RJ")
        self.assertEqual(result["suggested_row"]["operator"], "RJ")
        self.assertIn("2/3", result["suggested_row"]["note"])

    def test_split_sample_is_inconclusive(self):
        live = {
            "+918317025000": {"valid": True, "carrier": "Reliance (JIO)", "line_type": "mobile"},
            "+918317075000": {"valid": True, "carrier": "Airtel India (Bharti)",
                              "line_type": "mobile"},
        }
        with mock.patch.object(phonelookup.providers.twilio, "twilio_lookup",
                               side_effect=lambda e, s, t, f=None: live[e]):
            result = phonelookup.probe_block("83170", 2, ("S", "T"), {}, False)
        self.assertEqual(result["majority"], "")
        self.assertIsNone(result["suggested_row"])

    def test_landline_and_absent_samples_do_not_build_a_mobile_block(self):
        live = {
            "+918020016666": {"valid": True, "carrier": "BSNL", "line_type": "landline"},
            "+918020050000": {"valid": True, "carrier": "BSNL", "line_type": "landline"},
            "+918020083333": {"valid": False, "carrier": None, "line_type": None},
        }
        with mock.patch.object(phonelookup.providers.twilio, "twilio_lookup",
                               side_effect=lambda e, s, t, f=None: live[e]):
            result = phonelookup.probe_block("80200", 3, ("S", "T"), {}, False)
        self.assertEqual(result["majority"], "")
        self.assertIsNone(result["suggested_row"])
        self.assertEqual(result["outcomes"], {"landline": 2, "absent": 1})

    def test_checks_log_is_idempotent_per_number(self):
        sample = {"number": "+918317050000", "live_carrier": "Reliance (JIO)",
                  "live_code": "RJ", "mcc": "405", "mnc": "854",
                  "line_type": "mobile", "offline_carrier": "", "location": "KA",
                  "error": None}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "twilio_checks.csv"
            with mock.patch.object(phonelookup.constants, "TWILIO_CHECKS_CSV", path):
                phonelookup.append_twilio_checks([sample])
                phonelookup.append_twilio_checks([sample])  # re-run must not dupe
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)  # header + one row


class TwilioGroundTruthTest(unittest.TestCase):
    def test_twilio_is_the_current_carrier_and_all_sources_kept(self):
        fake = {"81234": {"prefix": "81234", "operator": "RJ", "circle": "KA",
                          "source": "twilio", "updated": "2026-11-07",
                          "note": "3/3 Reliance Jio"}}
        with mock.patch.object(phonelookup.tables, "twilio_table", lambda: fake):
            result = phonelookup.lookup("918123456789")  # block 81234
        self.assertEqual(result["current_carrier"], "Reliance Jio")
        self.assertEqual(result["carrier"], "Reliance Jio")
        self.assertEqual(result["series_source"], "twilio")
        sources = [h["source"] for h in result["history"]]
        self.assertEqual(sources[-1], "twilio")          # twilio is the answer
        self.assertIn("dot.gov.in", sources)             # allocation still kept

    def test_no_twilio_row_leaves_current_carrier_null(self):
        with mock.patch.object(phonelookup.tables, "twilio_table", lambda: {}):
            result = phonelookup.lookup("918123456789")
        self.assertIsNone(result["current_carrier"])


class SweepTest(unittest.TestCase):
    def test_parse_range(self):
        self.assertEqual(phonelookup.parse_range("70000-79999"), (70000, 79999))
        with self.assertRaises(ValueError):
            phonelookup.parse_range("70000")

    def test_budget_cap_stops_before_overspending(self):
        budget = {"calls": 0, "max": 2}
        reply = {"valid": True, "carrier": "Jio", "line_type": "mobile"}
        with mock.patch.object(phonelookup.providers.twilio, "twilio_lookup",
                               side_effect=lambda e, s, t, f=None: dict(reply)):
            cache = {}
            phonelookup.billed_lookup("+91a", ("S", "T"), cache, False, "f", budget)
            phonelookup.billed_lookup("+91b", ("S", "T"), cache, False, "f", budget)
            with self.assertRaises(phonelookup.BudgetExceeded):
                phonelookup.billed_lookup("+91c", ("S", "T"), cache, False, "f", budget)
        self.assertEqual(budget["calls"], 2)

    def test_cache_hit_is_free_and_does_not_count(self):
        budget = {"calls": 0, "max": 0}  # no billed calls allowed
        cache = {"+91x": {"carrier": "Jio", "fields": "line_type_intelligence"}}
        got = phonelookup.billed_lookup("+91x", ("S", "T"), cache, False,
                                        "line_type_intelligence", budget)
        self.assertEqual(got["carrier"], "Jio")
        self.assertEqual(budget["calls"], 0)

    def test_sweep_triages_and_respects_cap(self):
        # 70000 is live mobile (3 samples), 70001 is landline (1 sample, triaged)
        def fake(e164, sid, tok, fields=None):
            if e164.startswith("+917000050") or e164.startswith("+917000016") \
               or e164.startswith("+917000083"):
                return {"valid": True, "carrier": "Reliance (JIO)", "line_type": "mobile"}
            return {"valid": True, "carrier": "BSNL", "line_type": "landline"}
        saves = []
        with mock.patch.object(phonelookup.providers.twilio, "twilio_lookup", side_effect=fake):
            results, billed, hit_cap = phonelookup.sweep_blocks(
                ["70000", "70001"], 3, ("S", "T"), {}, False,
                "line_type_intelligence", 10, saves.append)
        self.assertFalse(hit_cap)
        self.assertEqual(billed, 4)  # 3 for the mobile block + 1 triaged landline
        self.assertEqual(results[0]["majority"], "RJ")
        self.assertIsNone(results[1]["suggested_row"])

    def test_suggested_rows_file_is_idempotent_per_prefix(self):
        row = {"prefix": "70370", "operator": "RJ", "circle": "UW",
               "source": "twilio", "updated": "2026-11-07", "note": "n"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "twilio_suggested.csv"
            with mock.patch.object(phonelookup.constants, "SUGGESTED_CSV", path):
                phonelookup.save_suggested_rows([row])
                phonelookup.save_suggested_rows([{**row, "operator": "AT"}])
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)  # header + one row (updated, not duped)
        self.assertIn("AT", lines[1])


class SpamSignalTest(unittest.TestCase):
    def test_trai_caller_series_classified(self):
        self.assertIn("140", phonelookup.caller_category("1409999999"))
        self.assertIn("1600", phonelookup.caller_category("16001234567"))
        self.assertEqual(phonelookup.caller_category("9886012345"), "")

    def test_signal_empty_for_plain_mobile_and_non_india(self):
        self.assertEqual(
            phonelookup.spam_signal("919886012345", "9886012345", "IN"), {})
        # 140-style digits outside India must not be flagged as TRAI series
        self.assertEqual(
            phonelookup.spam_signal("14155550123", "4155550123", "US"), {})

    def test_lookup_flags_telemarketer_series(self):
        result = phonelookup.lookup("911409999999")
        self.assertTrue(result["valid"])
        self.assertIn("140", result["spam"]["category"])

    def test_local_spam_list_sets_reported_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spam_numbers.csv"
            path.write_text("number,source,updated\n"
                            "919886012345,user-report,2026-11-08\n",
                            encoding="utf-8")
            with mock.patch.object(phonelookup.constants, "SPAM_CSV", path):
                phonelookup.spam_table.cache_clear()
                signal = phonelookup.spam_signal("919886012345", "9886012345", "IN")
        phonelookup.spam_table.cache_clear()
        self.assertTrue(signal["reported_spam"])
        self.assertEqual(signal["spam_source"], "user-report")


class NetworkRegistryTest(unittest.TestCase):
    def test_resolves_known_code(self):
        reg = phonelookup.network_registry("310", "260")
        self.assertEqual(reg["registered_operator"], "T-Mobile")
        self.assertEqual(reg["mnc"], "260")

    def test_mnc_format_variants_match(self):
        # The file stores Airtel Karnataka as 404/045; a 2-digit serving MNC
        # ("45") and the raw 3-digit form must both resolve to it.
        self.assertIn("Airtel", phonelookup.network_registry("404", "45")["registered_operator"])
        self.assertIn("Airtel", phonelookup.network_registry("404", "045")["registered_operator"])

    def test_unknown_or_empty_returns_empty(self):
        self.assertEqual(phonelookup.network_registry("999", "1"), {})
        self.assertEqual(phonelookup.network_registry("", ""), {})
        self.assertEqual(phonelookup.network_registry("405", None), {})

    def test_placeholder_mnc_joins_distinct_names(self):
        reg = phonelookup.network_registry("404", "999")
        self.assertTrue(reg["registered_operator"])

    def test_india_rows_flagged_historical(self):
        reg = phonelookup.network_registry("405", "53")
        self.assertTrue(reg["historical"])
        self.assertIn("historical", reg["source"])
        # non-India rows carry no historical flag
        self.assertNotIn("historical", phonelookup.network_registry("310", "260"))

    def test_missing_file_disables_feature(self):
        with mock.patch.object(phonelookup.constants, "MCC_MNC_CSV", Path("/no/such/file.csv")):
            phonelookup.mcc_mnc_table.cache_clear()
            self.assertEqual(phonelookup.network_registry("310", "260"), {})
        phonelookup.mcc_mnc_table.cache_clear()


class FlowAndRegistryTest(unittest.TestCase):
    """Presence providers and the offline MCC/MNC registry, without the network."""

    def test_flow_payload_wraps_the_number(self):  # positive
        self.assertEqual(phonelookup.flow_payload("+918123456789"),
                         {"phone": "+918123456789"})

    def test_flipkart_posts_number_and_parses_json(self):  # positive
        body = {"RESPONSE": {"userDetails": {"+918123456789": "VERIFIED"}}}
        with mock.patch.object(phonelookup.providers.flow, "urlopen",
                               return_value=BytesIO(json.dumps(body).encode())):
            result = phonelookup.flipkart_lookup("+918123456789")
        self.assertEqual(result["RESPONSE"]["userDetails"]["+918123456789"],
                         "VERIFIED")

    def test_registry_trims_whitespace_and_pads_mnc(self):  # edge
        reg = phonelookup.network_registry("  404 ", " 45 ")
        self.assertIn("Airtel", reg["registered_operator"])
        self.assertTrue(reg["historical"])

    def test_flow_lookup_reports_unreachable_service(self):  # negative
        with mock.patch.object(phonelookup.providers.flow, "urlopen",
                               side_effect=URLError("refused")):
            result = phonelookup.flow_lookup("+918123456789")
        self.assertIn("error", result)
        self.assertIn("unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
