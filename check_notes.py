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
from ticker_mapping import TICKER_MAPPING, SPECIAL_EXCHANGE_SUFFIX_MAP, EXCHANGE_SUFFIX_MAP

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
    bar = market_bar(ticker, trade_date, cache)

    if bar is None:
        return result(FAIL, f'{ticker} returns no market data at all')
    if 'error' in bar:
        return result(FAIL, f'{ticker} could not be read: {bar["error"]}')

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
        note_rate = fx_to_gbp(currency, trade_date, cache, parsed.get('exchange_rate'))
        quote_rate = fx_to_gbp(yf_currency, trade_date, cache)
    if note_rate is None or quote_rate is None:
        return result(WARN, f'no {currency}/{yf_currency} rate for {trade_date.date()}; '
                            f'cannot compare a {currency} note with a {yf_currency} quote',
                      yf_currency=yf_currency, low=low, high=high)

    note_gbp = price * note_rate
    low_gbp, high_gbp = low * quote_rate, high * quote_rate
    ratio = ((low_gbp + high_gbp) / 2) / note_gbp if note_gbp else 0.0
    quoted = f' ({yf_currency}, converted)' if yf_currency != currency else ''

    if low_gbp * (1 - RANGE_TOLERANCE) <= note_gbp <= high_gbp * (1 + RANGE_TOLERANCE):
        return result(OK, f'£{note_gbp:.4f} is inside {bar["bar_date"]} range '
                          f'[{low_gbp:.4f}, {high_gbp:.4f}]{quoted}',
                      yf_currency=yf_currency, low=low, high=high, ratio=ratio)

    low, high, price = low_gbp, high_gbp, note_gbp

    reason = explain_ratio(ratio)
    # Yahoo's history carries splits back; a note records the shares as they traded on the
    # day.  That is a real difference between two correct sources, so it is something to
    # look at rather than something wrong.
    status = WARN if 'split-adjusted' in reason else FAIL
    return result(status, f'{price:.4f} is outside {bar["bar_date"]} range '
                          f'[{low:.4f}, {high:.4f}] — {reason}',
                  yf_currency=yf_currency, low=low, high=high, ratio=ratio)


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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='+', help='note files or directories of them')
    parser.add_argument('--json', action='store_true', help='emit results as JSON')
    parser.add_argument('--quiet', action='store_true', help='only show what is not OK')
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

    shown = [c for c in checks if c.status != OK] if args.quiet else checks
    root = args.paths[0] if len(args.paths) == 1 and os.path.isdir(args.paths[0]) else ''

    if args.json:
        print(json.dumps([c._asdict() for c in shown], indent=1))
    else:
        render(shown, root)

    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == '__main__':
    sys.exit(main())
