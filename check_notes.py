#!/usr/bin/env python3
"""Check broker notes against Yahoo Finance before they go into the live tree.

A note's Yahoo identity cannot be derived from the note.  ISINs are only sometimes
accepted, unit trusts have no exchange at all, and a single exchange carries lines of the
same fund in different currencies — so `ARMG.L` and `ARMR.L` are both Global X Defence
Tech on the LSE, one priced in GBP and one in USD (investment-reviews#40, #59).

It can, however, be checked.  The note states a quantity, a price and a date; the market
states what that instrument did on that date.  If they disagree the identity is wrong,
and the *way* they disagree says how:

    ratio ~1.0            the note and the market agree
    ratio ~100 or ~0.01   pence quoted against pounds
    ratio near an FX rate the right fund, but the wrong currency line
    ratio a round integer Yahoo's split-adjusted history against an unadjusted note
    anything else         a different instrument entirely

The comparison is against the trade date's high/low range rather than its closing price:
a trade executes intraday, so the note's price belongs inside that day's range.  Judged
against closes instead, a fifth of genuinely correct notes look wrong.

Run it over new notes before copying them into the live tree:

    check_notes.py ~/Downloads/new-notes/
    check_notes.py one_note.pdf --json

Exit status is 0 when every note checks out, 1 when any does not, so it can gate a
script.
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, NamedTuple, Optional

warnings.filterwarnings('ignore')

from pdf_parser import parse_stock_transaction_pdf, NoteParseError, get_exchange_suffix
from mhtml_parser import parse_stock_transaction_mhtml
from csv_parser import parse_stock_transaction_csv
from yaml_parser import parse_stock_transaction_yaml
import yaml

import ticker_mapping
from ticker_mapping import (TICKER_MAPPING, SPECIAL_EXCHANGE_SUFFIX_MAP,
                            EXCHANGE_SUFFIX_MAP)

NOTE_EXTENSIONS = ('.pdf', '.mhtml', '.csv', '.yaml', '.yml')

# How far either side of the trade date to look for a bar.  A note dated on a weekend or
# a holiday settles against the next session, and funds do not price every day.
TRADING_DAY_SEARCH = 4

# Allowed either side of the day's own high/low.  It has to absorb more than rounding:
# where the note's price is derived from a consideration in another currency, that
# consideration carries dealing costs and a retail FX spread that the exchange's own
# range does not.  The AGGG.L purchase lands 0.74% above its converted range for exactly
# that reason and is correct.
RANGE_TOLERANCE = 0.02

OK, WARN, FAIL = 'OK', 'WARN', 'FAIL'

# Only these carry a traded price.  A transfer or a conversion records a cost base being
# moved or restated — the demerger entry in #52 apportions a GBP cost across two holdings
# — so there is no market price for that day to compare it against, and comparing anyway
# reports a correct note as wrong.
PRICED_TRANSACTION_TYPES = ('purchase', 'disposal', 'sale')


class NotCheckedHere(Exception):
    """This file is deliberately outside the tool's remit, as opposed to unreadable.

    The two must not collapse into one another: skipping a corporate action is correct,
    while a contract note that yields nothing is the silence #36 and #54 exist to remove.
    """


class Check(NamedTuple):
    """One security found in one note, and what the market says about it."""
    path: str
    status: str
    ticker: Optional[str]
    provenance: str
    note_currency: Optional[str]
    note_price: Optional[float]
    trade_date: Optional[str]
    yf_currency: Optional[str]
    yf_low: Optional[float]
    yf_high: Optional[float]
    ratio: Optional[float]
    detail: str


def collect_notes(paths: List[str]) -> List[str]:
    """Every note file under the given files or directories."""
    found = []
    for path in paths:
        if os.path.isfile(path):
            found.append(path)
        elif os.path.isdir(path):
            for directory, _, filenames in os.walk(path):
                for filename in sorted(filenames):
                    if filename.lower().endswith(NOTE_EXTENSIONS) and not filename.startswith('.'):
                        found.append(os.path.join(directory, filename))
        else:
            print(f"WARNING: {path} does not exist", file=sys.stderr)
    return sorted(set(found))


def parse_note(path: str) -> List[Dict]:
    """Parse a note using the same code the nightly scan uses.

    Deliberately the same functions rather than a reimplementation: a checker that parsed
    notes its own way would pass files the scan then chokes on.
    """
    name = os.path.basename(path).lower()
    if name.endswith('.pdf'):
        if 'bought' not in name and 'sold' not in name:
            # A corporate action has no price to check against the market, and #53/#54
            # already report one that cannot be read.  Not this tool's business.
            raise NotCheckedHere('corporate action, not a contract note')
        parsed = parse_stock_transaction_pdf(path)
        return [parsed] if parsed else []
    if name.endswith('.mhtml'):
        return parse_stock_transaction_mhtml(path)
    if name.endswith('.csv'):
        return parse_stock_transaction_csv(path)
    if name.endswith(('.yaml', '.yml')):
        return parse_stock_transaction_yaml(path)
    raise ValueError(f'unsupported file type: {os.path.splitext(path)[1]}')


def identity_provenance(parsed: Dict) -> str:
    """Where the Yahoo identifier came from, which is what a wrong one has to be traced to."""
    ticker = parsed.get('ticker') or ''
    isin = parsed.get('isin') or ''
    bare = ticker.split('.')[0]

    if parsed.get('stock_name') in TICKER_MAPPING:
        return 'name mapping'
    if bare in SPECIAL_EXCHANGE_SUFFIX_MAP:
        return 'ticker map'
    if isin[:2].upper() in EXCHANGE_SUFFIX_MAP:
        return f'ISIN country {isin[:2].upper()}'
    if isin:
        return 'note ticker, no suffix'
    return 'note ticker'


def market_bar(ticker: str, trade_date: datetime, cache: Dict) -> Optional[Dict]:
    """The instrument's high, low and currency on (or nearest before) the trade date."""
    import yfinance as yf
    warnings.filterwarnings('ignore')

    key = (ticker, trade_date.date())
    if key in cache:
        return cache[key]

    result = None
    try:
        handle = yf.Ticker(ticker)
        # auto_adjust=False for the same reason market_data_fetcher uses it: adjusted
        # history is back-corrected for dividends, so a note from several years and many
        # dividends ago sits 20-25% above its own adjusted range and reads as a different
        # instrument.  A contract note records what was actually paid.
        history = handle.history(
            start=(trade_date - timedelta(days=TRADING_DAY_SEARCH)).strftime('%Y-%m-%d'),
            end=(trade_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            auto_adjust=False)
        if not history.empty:
            row = history.iloc[-1]
            currency = (handle.info or {}).get('currency')
            low, high = float(row['Low']), float(row['High'])
            # GBp is Yahoo reporting pence; the notes are already in pounds by this point.
            if currency == 'GBp':
                low, high, currency = low / 100.0, high / 100.0, 'GBP'
            result = {'low': low, 'high': high, 'currency': currency,
                      'bar_date': str(history.index[-1].date())}
    except Exception as error:
        result = {'error': f'{type(error).__name__}: {error}'}

    cache[key] = result
    return result


def whole_factor(ratio: float) -> Optional[int]:
    """The whole-number factor this ratio is, if it is one, either way up.

    Not a fixed list: splits compound.  NVIDIA's 4:1 in 2021 and 10:1 in 2024 leave a
    2020 note sitting 40x from its own adjusted history, and no list of likely factors
    was going to contain 40.
    """
    for candidate in (ratio, 1 / ratio if ratio else 0):
        if candidate >= 1.5:
            nearest = round(candidate)
            if nearest >= 2 and abs(candidate - nearest) / nearest < 0.03:
                return nearest
    return None


def explain_ratio(ratio: float) -> str:
    """What a price disagreement of this size usually means."""
    factor = whole_factor(ratio)
    if factor == 100:
        # Both readings are exactly 100, and nothing in the numbers separates them.
        return 'exactly 100x: pence against pounds, or a 100:1 split?'
    if factor:
        return f'about {factor}x: split-adjusted history against an unadjusted note?'
    if 1.05 <= ratio <= 1.6 or 0.62 <= ratio <= 0.95:
        return 'close to an FX rate: the right fund on the wrong currency line?'
    return 'a different instrument'


def fx_to_gbp(currency: Optional[str], trade_date: datetime, cache: Dict,
              stated: Optional[float] = None) -> Optional[float]:
    """What one unit of `currency` was worth in sterling on the trade date.

    A rate stated on the note itself wins: it is the rate the broker actually applied,
    where a mid-market rate fetched afterwards is only close to it.
    """
    if not currency or currency == 'GBP':
        return 1.0
    if stated:
        return float(stated)

    key = ('fx', currency, trade_date.date())
    if key in cache:
        return cache[key]

    rate = None
    try:
        import yfinance as yf
        history = yf.Ticker(f'{currency}GBP=X').history(
            start=(trade_date - timedelta(days=TRADING_DAY_SEARCH)).strftime('%Y-%m-%d'),
            end=(trade_date + timedelta(days=1)).strftime('%Y-%m-%d'))
        if not history.empty:
            rate = float(history['Close'].iloc[-1])
    except Exception:
        rate = None

    cache[key] = rate
    return rate


def trade_date_of(raw) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d')
    except ValueError:
        return None


def check_transaction(path: str, parsed: Dict, cache: Dict) -> Check:
    """Compare one parsed transaction against the market on its trade date."""
    ticker = parsed.get('ticker')
    provenance = identity_provenance(parsed)
    currency = parsed.get('currency')
    price = parsed.get('price')
    raw_date = parsed.get('transaction_date') or parsed.get('settlement_date')

    def result(status, detail, **kw):
        return Check(path=path, status=status, ticker=ticker, provenance=provenance,
                     note_currency=currency, note_price=price,
                     trade_date=str(raw_date)[:10] if raw_date else None,
                     yf_currency=kw.get('yf_currency'), yf_low=kw.get('low'),
                     yf_high=kw.get('high'), ratio=kw.get('ratio'), detail=detail)

    if not ticker:
        return result(FAIL, 'the note yields no ticker, so nothing can be priced')

    kind = (parsed.get('transaction_type') or '').lower()
    if kind and kind not in PRICED_TRANSACTION_TYPES:
        bar = market_bar(ticker, trade_date_of(raw_date) or datetime.now(), cache)
        if bar is None or 'error' in bar:
            return result(FAIL, f'{ticker} returns no market data '
                                f'(a {kind} still has to name a real security)')
        return result(OK, f'{kind}: a cost-base entry, so there is no traded price to '
                          f'check; {ticker} resolves',
                      yf_currency=bar['currency'], low=bar['low'], high=bar['high'])

    if price is None:
        return result(FAIL, 'the note yields no price, so nothing can be compared')
    if not raw_date:
        return result(WARN, 'the note yields no date; cannot compare against the market')

    trade_date = trade_date_of(raw_date)
    if trade_date is None:
        return result(WARN, f'the note date {raw_date!r} could not be read')

    status, detail, extras = compare_to_market(
        ticker, currency, price, trade_date, parsed.get('exchange_rate'), cache)
    return result(status, detail, **extras)


def compare_to_market(ticker: str, currency: Optional[str], price: float,
                      trade_date: datetime, stated_rate: Optional[float], cache: Dict):
    """Does the market on that day agree with this price for this identifier?

    Separated out so a proposed candidate is judged by exactly the same standard as the
    identifier it would replace.  A candidate scored more leniently than the thing it
    replaces would be worse than no suggestion at all (investment-reviews#59).
    """
    bar = market_bar(ticker, trade_date, cache)

    if bar is None:
        return FAIL, f'{ticker} returns no market data at all', {}
    if 'error' in bar:
        return FAIL, f'{ticker} could not be read: {bar["error"]}', {}

    low, high, yf_currency = bar['low'], bar['high'], bar['currency']
    mid = (low + high) / 2 or 1.0
    ratio = mid / price if price else 0.0

    # Both sides are converted to sterling rather than requiring their currency labels to
    # agree.  A label mismatch is routine and says nothing: AGGG.L is listed on the LSE
    # and quoted in USD, and the Interactive Investor CSV states every price in GBP
    # because it derives them from a GBP consideration.  Failing on the labels rejected
    # correct notes while the prices agreed perfectly (investment-reviews#59).
    if currency == yf_currency:
        # Already like for like.  Converting anyway needs a rate that may not exist —
        # Yahoo has no CZKGBP=X — and would fail a note that never needed converting.
        note_rate = quote_rate = 1.0
    else:
        note_rate = fx_to_gbp(currency, trade_date, cache, stated_rate)
        quote_rate = fx_to_gbp(yf_currency, trade_date, cache)
    if note_rate is None or quote_rate is None:
        return (WARN, f'no {currency}/{yf_currency} rate for {trade_date.date()}; '
                      f'cannot compare a {currency} note with a {yf_currency} quote',
                {'yf_currency': yf_currency, 'low': low, 'high': high})

    note_gbp = price * note_rate
    low_gbp, high_gbp = low * quote_rate, high * quote_rate
    ratio = ((low_gbp + high_gbp) / 2) / note_gbp if note_gbp else 0.0
    quoted = f' ({yf_currency}, converted)' if yf_currency != currency else f' ({currency})'

    extras = {'yf_currency': yf_currency, 'low': low, 'high': high, 'ratio': ratio}
    # Only call it sterling when it has actually been converted into sterling: where the
    # note and the quote share a currency nothing is converted, and a hardcoded pound
    # sign was labelling euros as pounds in a tool whose whole job is to be trusted.
    money = '£' if note_rate != 1.0 or currency == 'GBP' else ''
    if low_gbp * (1 - RANGE_TOLERANCE) <= note_gbp <= high_gbp * (1 + RANGE_TOLERANCE):
        return (OK, f'{money}{note_gbp:.4f} is inside {bar["bar_date"]} range '
                    f'[{low_gbp:.4f}, {high_gbp:.4f}]{quoted}', extras)

    reason = explain_ratio(ratio)
    # Yahoo's history carries splits back; a note records the shares as they traded on the
    # day.  That is a real difference between two correct sources, so it is something to
    # look at rather than something wrong.
    status = WARN if 'split-adjusted' in reason else FAIL
    return (status, f'{money}{note_gbp:.4f} is outside {bar["bar_date"]} range '
                    f'[{low_gbp:.4f}, {high_gbp:.4f}] — {reason}', extras)


def check_note(path: str, cache: Dict) -> List[Check]:
    """Check every security a note names.  One note may hold many."""
    def failure(detail):
        return [Check(path, FAIL, None, '-', None, None, None, None, None, None, None, detail)]

    try:
        transactions = parse_note(path)
    except NotCheckedHere:
        return []
    except NoteParseError as error:
        return failure(f'could not be read: {error}')
    except Exception as error:
        return failure(f'could not be parsed: {type(error).__name__}: {error}')

    if not transactions:
        return failure('parsed, but yields no transactions')

    checks, seen = [], set()
    for parsed in transactions:
        key = (parsed.get('ticker'), str(parsed.get('transaction_date'))[:10])
        if key in seen:
            continue
        seen.add(key)
        checks.append(check_transaction(path, parsed, cache))
    return checks


# Suffixes worth trying for a London-or-European listing whose bare ticker resolves to
# something else.  Ordered by how often they turn out to be the answer here; the empty
# suffix is included because a US line is sometimes right and the note ticker wrong.
CANDIDATE_SUFFIXES = ('.L', '', '.TO', '.DE', '.PA', '.MI', '.AS', '.SW', '.ST', '.OL',
                      '.V', '.CO', '.HE', '.MC', '.BR', '.VI', '.PR')


class Candidate(NamedTuple):
    """A possible identifier for a note, and how it would be recorded if chosen."""
    identifier: str
    section: str   # which part of ticker_mappings.yaml it would be recorded in
    key: str
    value: str
    status: str
    detail: str


def candidates_for(parsed: Dict) -> List[Candidate]:
    """Identifiers worth trying, and how each would be written down.

    Only offers what the resolver can actually use.  A note with a ticker is resolved by
    ticker plus suffix, and one without by its stock name — so a candidate that matched
    but could not be recorded would be a trap, not a suggestion.  The ISIN is offered as
    a name mapping only for a note that has no ticker, which is where the resolver
    consults names at all.
    """
    ticker = (parsed.get('ticker') or '').strip()
    isin = (parsed.get('isin') or '').strip()
    name = (parsed.get('stock_name') or '').strip()
    bare = ticker.split('.')[0]

    seen, out = set(), []

    def add(identifier, section, key, value):
        if identifier and identifier not in seen:
            seen.add(identifier)
            out.append((identifier, section, key, value))

    if bare:
        for suffix in CANDIDATE_SUFFIXES:
            add(f'{bare}{suffix}', 'ticker_suffixes', bare, suffix)
    if name and not ticker:
        # 87% of the ISINs in this book resolve on Yahoo, so it is worth trying — but
        # only for a note the resolver would look up by name, which is one with no ticker.
        # Offering it for a ticker-bearing note would propose an identifier that matches
        # and can never take effect.
        add(isin, 'names', name, isin)
    return [Candidate(i, sec, k, v, '', '') for i, sec, k, v in out]


def search_candidates(parsed: Dict, cache: Dict, limit: int = None) -> List[Candidate]:
    """Score every candidate the same way the note's own identifier was scored."""
    price = parsed.get('price')
    currency = parsed.get('currency')
    trade_date = trade_date_of(parsed.get('transaction_date') or parsed.get('settlement_date'))
    if price is None or trade_date is None:
        return []

    scored = []
    for candidate in candidates_for(parsed)[:limit]:
        status, detail, _ = compare_to_market(
            candidate.identifier, currency, price, trade_date,
            parsed.get('exchange_rate'), cache)
        scored.append(candidate._replace(status=status, detail=detail))
    return scored


def write_mapping(section: str, key: str, value: str, note: str = None,
                  path: str = None) -> str:
    """Record a chosen mapping in ticker_mappings.yaml.

    The file's explanatory header is preserved verbatim and the data re-dumped beneath
    it: the per-entry reasoning lives in `note` fields rather than comments precisely so
    that a writer cannot destroy it.
    """
    path = path or ticker_mapping.MAPPINGS_FILE
    with open(path, encoding='utf-8') as handle:
        text = handle.read()

    header_lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith('#') or not line.strip():
            header_lines.append(line)
        else:
            break
    header = ''.join(header_lines)

    data = yaml.safe_load(text) or {}
    data.setdefault(section, {})
    data[section][key] = {value_key(section): value, 'note': note} if note else value

    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(header)
        yaml.safe_dump(data, handle, sort_keys=True, allow_unicode=True,
                       default_flow_style=False, width=100)
    return path


def value_key(section: str) -> str:
    return {'names': 'yahoo', 'exchange_suffixes': 'suffix',
            'ticker_suffixes': 'suffix', 'renames': 'to'}[section]


def render(checks: List[Check], root: str) -> None:
    print(f"{'':6} {'NOTE':44} {'TICKER':13} {'FROM':18} {'CCY':4} {'PRICE':>11}  DETAIL")
    for check in checks:
        name = os.path.relpath(check.path, root) if root else os.path.basename(check.path)
        price = f'{check.note_price:.4f}' if check.note_price is not None else '-'
        print(f"{check.status:6} {name[-44:]:44} {str(check.ticker or '-'):13} "
              f"{check.provenance:18} {str(check.note_currency or '-'):4} {price:>11}  {check.detail}")

    counts = {status: sum(1 for c in checks if c.status == status) for status in (OK, WARN, FAIL)}
    print(f"\n{counts[OK]} ok, {counts[WARN]} to look at, {counts[FAIL]} wrong")
    if counts[FAIL]:
        print("\nA note that does not match is usually a missing or wrong entry in "
              "ticker_mapping.py.\nCheck the security by hand before copying these notes "
              "into the live tree.")


def offer_candidates(check: Check, parsed: Dict, cache: Dict,
                     prompt=input, out=print) -> bool:
    """Show what else this note could be, and record the operator's choice.

    Returns True if a mapping was written.  Choosing nothing is a first-class answer:
    the tool has no way to tell a wrong identifier from a security Yahoo simply does not
    carry, and guessing on the operator's behalf is how a plausible wrong number gets
    into the book (investment-reviews#50).
    """
    out(f"\n{check.path}")
    out(f"  {check.ticker} ({check.provenance}): {check.detail}")

    scored = search_candidates(parsed, cache)
    matches = [c for c in scored if c.status == OK and c.identifier != check.ticker]
    if not matches:
        tried = ', '.join(c.identifier for c in scored) or 'nothing'
        out(f"  No candidate matched the note. Tried: {tried}")
        out("  Search for the security by hand and add it to ticker_mappings.yaml.")
        return False

    out("  Candidates that match the note's own price on its trade date:")
    for number, candidate in enumerate(matches, 1):
        how = f"{candidate.section}: {candidate.key} -> {candidate.value!r}"
        out(f"    {number}. {candidate.identifier:14} {candidate.detail}")
        out(f"       {how}")

    answer = prompt("  Choose a number, or Enter for none: ").strip()
    if not answer:
        out("  Nothing recorded.")
        return False
    if not answer.isdigit() or not 1 <= int(answer) <= len(matches):
        out(f"  {answer!r} is not one of the choices; nothing recorded.")
        return False

    chosen = matches[int(answer) - 1]
    path = write_mapping(chosen.section, chosen.key, chosen.value,
                         note=f'chosen against the {check.trade_date} price in '
                              f'{os.path.basename(check.path)}')
    out(f"  Recorded in {os.path.basename(path)}. Commit it before the notes go live.")
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='+', help='note files or directories of them')
    parser.add_argument('--json', action='store_true', help='emit results as JSON')
    parser.add_argument('--quiet', action='store_true', help='only show what is not OK')
    parser.add_argument('--fix', action='store_true',
                        help='for each note that does not check out, propose candidates '
                             'and record the one you choose in ticker_mappings.yaml')
    parser.add_argument('--since', metavar='YYYY-MM-DD',
                        help='only check notes dated on or after this, so a routine run '
                             'is not dominated by holdings that have since been delisted '
                             'or renamed')
    args = parser.parse_args(argv)

    logging.disable(logging.WARNING)

    notes = collect_notes(args.paths)
    if not notes:
        print('No notes found.', file=sys.stderr)
        return 1

    since = trade_date_of(args.since) if args.since else None
    if args.since and since is None:
        print(f'--since {args.since!r} is not a date', file=sys.stderr)
        return 1

    cache: Dict = {}
    checks = []
    for path in notes:
        for check in check_note(path, cache):
            dated = trade_date_of(check.trade_date)
            if since and dated and dated < since:
                continue
            checks.append(check)

    if args.fix:
        if args.json:
            print('--fix asks questions, so it cannot be combined with --json',
                  file=sys.stderr)
            return 2
        if not sys.stdin.isatty():
            print('--fix asks questions and stdin is not a terminal', file=sys.stderr)
            return 2
        written = 0
        for check in checks:
            if check.status != FAIL or not check.ticker:
                continue
            for parsed in parse_note(check.path):
                if parsed.get('ticker') == check.ticker:
                    written += offer_candidates(check, parsed, cache)
                    break
        if written:
            print(f"\n{written} mapping(s) recorded. Re-run to confirm, then commit "
                  f"ticker_mappings.yaml.")
        return 1 if any(c.status == FAIL for c in checks) else 0

    shown = [c for c in checks if c.status != OK] if args.quiet else checks
    root = args.paths[0] if len(args.paths) == 1 and os.path.isdir(args.paths[0]) else ''

    if args.json:
        print(json.dumps([c._asdict() for c in shown], indent=1))
    else:
        render(shown, root)

    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == '__main__':
    sys.exit(main())
