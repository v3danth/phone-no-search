"""Command-line interface: parse flags, run the right action, print JSON results.

Imports the library functions and never the other way round, so the library works
without the command line. Results go to stdout; diagnostics go through logging.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import constants as c
from .agreement import agreement
from .config import env_setting, twilio_creds
from .core import lookup
from .dork import dork, dork_urls
from .providers.flow import flipkart_lookup, flow_lookup
from .providers.numverify import numverify
from .providers.twilio import (
    append_twilio_checks,
    blocks_to_refresh,
    cached_twilio_lookup,
    live_cache_load,
    live_cache_save,
    probe_block,
    save_suggested_rows,
    sweep_blocks,
)
from .records import Credentials

logger = logging.getLogger(__name__)

DESCRIPTION = "Offline phone number lookup, numverify-style output."
EPILOG = """\
examples:
  phonelookup 917904000000 +16505550123
  phonelookup --file numbers.txt
  phonelookup --dork 919886000000
  phonelookup --numverify 919886000000
  phonelookup --live 919886000000
  phonelookup --probe-block 83170 --samples 3
  phonelookup --probe-range 70000-79999 --max-calls 200
"""

# argparse flag -> the Twilio field package it requests (data over logic, so a
# new optional field is one row here plus one add_argument).
OPTIONAL_FIELDS = (
    ("line_status", c.LINE_STATUS_FIELD),
    ("sim_swap", c.SIM_SWAP_FIELD),
    ("call_forwarding", c.CALL_FORWARDING_FIELD),
)


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line flags."""
    parser = argparse.ArgumentParser(
        prog="phonelookup", description=DESCRIPTION, epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("numbers", nargs="*")
    parser.add_argument("--file", help="file with one number per line")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument("--dork", action="store_true",
                        help="print a search string and a URL per search engine")
    parser.add_argument("--numverify", action="store_true",
                        help="also query numverify (1 API request per number)")
    parser.add_argument("--live", action="store_true",
                        help="also query Twilio Lookup for live HLR carrier data "
                             "(needs TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN; "
                             "1 billed request per number; results cached locally)")
    parser.add_argument("--refresh", action="store_true",
                        help="with --live, ignore the cache and re-query Twilio")
    parser.add_argument("--line-status", action="store_true",
                        help="with --live, also request Twilio line_status")
    parser.add_argument("--sim-swap", action="store_true",
                        help="with --live, also request Twilio sim_swap")
    parser.add_argument("--call-forwarding", action="store_true",
                        help="with --live, also request Twilio call_forwarding")
    parser.add_argument("--probe-block", action="store_true",
                        help="treat positional args as block prefixes and sample a "
                             "few numbers per block via Twilio to infer the operator")
    parser.add_argument("--samples", type=int, default=3, metavar="N",
                        help="numbers to sample per block with --probe-block (default 3)")
    parser.add_argument("--probe-range", metavar="LOW-HIGH",
                        help="sweep every 5-digit mobile block in the range with no "
                             "operator or a closed one (e.g. 70000-79999)")
    parser.add_argument("--max-calls", type=int, metavar="N",
                        help="hard cap on billed Twilio calls for --probe-range")
    return parser


def requested_fields(args: argparse.Namespace) -> str:
    """The comma-separated Twilio field list implied by the optional flags."""
    fields = [c.LTI_FIELD]
    fields += [field for attr, field in OPTIONAL_FIELDS if getattr(args, attr)]
    return ",".join(fields)


def input_numbers(args: argparse.Namespace) -> list[str]:
    """Numbers from arguments, then --file, then piped stdin. Raises OSError if
    --file cannot be read."""
    numbers = list(args.numbers)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            numbers += fh.read().split()
    if not numbers and not sys.stdin.isatty():
        numbers = sys.stdin.read().split()
    return numbers


def parse_range(text: str) -> tuple[int, int]:
    """Parse "LOW-HIGH" into (low, high) ints, or raise ValueError."""
    low, sep, high = text.partition("-")
    if not sep:
        raise ValueError("range must be LOW-HIGH, e.g. 70000-79999")
    return int(low), int(high)


def _print(result: object, indent: int | None) -> None:
    """Print one JSON result to stdout (the program's output)."""
    print(json.dumps(result, indent=indent, ensure_ascii=False))


def print_dorks(numbers: list[str]) -> None:
    """Print a search query and URL per number; skip unparsable ones."""
    import phonenumbers
    for raw in numbers:
        try:
            query = dork(raw)
        except phonenumbers.NumberParseException as err:
            logger.warning("%s: %s", raw, err)
            continue
        print(query)
        for name, url in dork_urls(query).items():
            print(f"  {name}: {url}")


def print_lookups(numbers: list[str], key: str, indent: int | None,
                  twilio: Credentials | None = None, refresh: bool = False,
                  fields: str = c.LTI_FIELD) -> None:
    """Print one JSON result per number, adding numverify/Twilio/flow blocks when
    requested. Live Twilio results are cached so repeat runs cost nothing.
    """
    cache = live_cache_load() if twilio else {}
    dirty = False
    for raw in numbers:
        result: dict = lookup(raw)
        offline = result
        if result["valid"]:
            if key or twilio:
                result = {"offline": offline}
                if key:
                    remote = numverify(offline["number"], key)
                    result["numverify"] = remote
                    if "error" not in remote:
                        result["agree"] = agreement(offline, remote)
                if twilio:
                    e164 = offline["international_format"]
                    before = cache.get(e164)
                    result["live"] = cached_twilio_lookup(
                        e164, twilio, cache, refresh, fields)
                    dirty = dirty or cache.get(e164) is not before
            result["flow"] = flow_lookup(offline["international_format"])
            result["flipkart"] = flipkart_lookup(offline["international_format"])
        _print(result, indent)
    if dirty:
        live_cache_save(cache)


def print_block_probes(prefixes: list[str], twilio: Credentials, samples: int,
                       refresh: bool, indent: int | None) -> None:
    """Probe each block prefix and print its inferred operator as JSON."""
    cache = live_cache_load()
    all_samples = []
    suggested = []
    for prefix in prefixes:
        result = probe_block(prefix, samples, twilio, cache, refresh)
        all_samples += result["samples"]
        if result["suggested_row"]:
            suggested.append(result["suggested_row"])
        _print(result, indent)
    live_cache_save(cache)
    if all_samples:
        append_twilio_checks(all_samples)
    if suggested:
        save_suggested_rows(suggested)


def print_block_sweep(low: int, high: int, twilio: Credentials, samples: int,
                      refresh: bool, fields: str, max_calls: int | None,
                      indent: int | None) -> None:
    """Sweep a block range within a billed-call cap, printing suggested rows."""
    prefixes = blocks_to_refresh(low, high)
    logger.info("%d blocks worth probing in %d-%d; cap %s calls",
                len(prefixes), low, high,
                max_calls if max_calls is not None else "none")
    cache = live_cache_load()
    results, billed, hit_cap = sweep_blocks(
        prefixes, samples, twilio, cache, refresh, fields, max_calls,
        live_cache_save)

    suggested = []
    all_samples = []
    for result in results:
        all_samples += result["samples"]
        if result["suggested_row"]:
            suggested.append(result["suggested_row"])
            _print(result["suggested_row"], indent)
    if all_samples:
        append_twilio_checks(all_samples)
    if suggested:
        save_suggested_rows(suggested)
    logger.info("done: scanned %d/%d blocks, %d rows suggested (saved to %s), "
                "%d calls billed%s", len(results), len(prefixes), len(suggested),
                c.SUGGESTED_CSV.name, billed,
                " (CAP HIT, resume to continue)" if hit_cap else "")


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return its exit code (0 on success)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if (args.line_status or args.sim_swap or args.call_forwarding) and not args.live:
        logger.error("--line-status, --sim-swap and --call-forwarding require --live")
        return 2

    key = ""
    if args.numverify:
        key = env_setting("NUMVERIFY_KEY")
        if not key:
            logger.error("--numverify needs NUMVERIFY_KEY in the environment or .env")
            return 2

    twilio: Credentials | None = None
    if args.live or args.probe_block or args.probe_range:
        twilio = twilio_creds()
        if not twilio:
            flag = ("--probe-range" if args.probe_range else
                    "--probe-block" if args.probe_block else "--live")
            logger.error("%s needs TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in the "
                         "environment or .env", flag)
            return 2

    if (args.probe_block or args.probe_range) and args.samples < 1:
        logger.error("--samples must be at least 1")
        return 2

    fields = requested_fields(args)
    indent = 2 if args.pretty else None

    if args.probe_range:
        try:
            low, high = parse_range(args.probe_range)
        except ValueError as err:
            logger.error("--probe-range: %s", err)
            return 2
        assert twilio is not None
        print_block_sweep(low, high, twilio, args.samples, args.refresh,
                          fields, args.max_calls, indent)
        return 0

    try:
        numbers = input_numbers(args)
    except OSError as err:
        logger.error("cannot read --file: %s", err)
        return 2
    if not numbers:
        parser.print_help()
        return 2

    if args.probe_block:
        assert twilio is not None
        print_block_probes(numbers, twilio, args.samples, args.refresh, indent)
    elif args.dork:
        print_dorks(numbers)
    else:
        print_lookups(numbers, key, indent=indent,
                      twilio=twilio, refresh=args.refresh, fields=fields)
    return 0
