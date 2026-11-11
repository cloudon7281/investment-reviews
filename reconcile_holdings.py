"""Reconcile the holdings the notes imply with what the brokers say is held (investment-reviews#104).

The tool knows a holding only from the broker notes in the tree, so a note that was never
downloaded leaves it holding the wrong number of units, silently.  This mode reads the holdings
exports from the brokers' own portals and reports every holding where the two disagree.

Each export is one broker's view of one or more accounts:

    HL     one file per account; its first line names the account, ISA or Fund & Share (Taxable)
    ii     the pension, always
    IBKR   one file for every account; each position names its account, which --broker-accounts
           classifies, because nothing in the file says whether an account is an ISA

Lines are matched to the tool's holdings, which are keyed (ticker, category), and summed per
holding.  No broker export gives both a ticker and a name, and none gives the Yahoo ticker the
tool uses, so each broker has its own rule:

    HL     the stock name in the H&L contract notes is the leading part of the name in the
           holdings export: "Amphenol Corp" is "Amphenol Corp Class A Com Stk USD0.001 *R"
    ii     the symbol is the tool's ticker without its exchange suffix (ETFs), or the SEDOL the
           ii transaction notes carry (funds)
    IBKR   the symbol is the tool's ticker, with or without its exchange suffix; the tool keys
           IBKR's funds by their ISIN, which is what IBKR shows

The broker_holdings section of ticker_mappings.yaml overrides the rule for a line it cannot
match.  A line matching nothing in its own category is looked for in the others and reported as
a category mismatch; a line that still matches nothing, or matches more than one holding, is
reported rather than guessed.

Units are compared in whole units, because the brokers and the notes round fractions
differently.  A difference of less than 1% of the broker's holding is reported apart from the
rest: it is usually a small dividend reinvestment whose note was not downloaded.  Values move
with the market, so they only need to agree to within 5%.
"""

import csv
import io
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

import pandas as pd

from list_trades_processor import _ACCOUNT_DISPLAY
from ticker_mapping import BROKER_HOLDINGS_MAP

BROKERS = ('HL', 'ii', 'IBKR')

# The broker whose notes each parser reads, by file extension.  A YAML note is written by hand
# and names no broker.
NOTE_BROKER = {'.pdf': 'HL', '.csv': 'ii', '.mhtml': 'IBKR'}

CATEGORIES = ('isa', 'taxable', 'pension')

MINOR_FRACTION = 0.01
VALUE_TOLERANCE = 0.05

# Findings, in the order the report lists them.
UNIT_DISCREPANCY = 'Unit discrepancy'
CATEGORY_MISMATCH = 'Category mismatch'
NO_NOTES = 'Held at broker, no notes'
NOT_AT_BROKER = 'In notes, not at broker'
AMBIGUOUS = 'Ambiguous match'
VALUE_DISCREPANCY = 'Value discrepancy'
MINOR_DIFFERENCE = 'Minor difference'
FINDING_ORDER = (UNIT_DISCREPANCY, CATEGORY_MISMATCH, NO_NOTES, NOT_AT_BROKER, AMBIGUOUS,
                 VALUE_DISCREPANCY, MINOR_DIFFERENCE)


class ReconcileInputError(ValueError):
    """A broker file or argument that cannot be read as given."""


@dataclass
class BrokerLine:
    """One position in a broker's holdings export."""
    broker: str
    category: str               # isa / taxable / pension
    identifier: str             # H&L: the stock name; ii and IBKR: the symbol
    description: str            # what the report shows for it
    units: float
    value_gbp: Optional[float]  # None when the broker shows no value
    source: str


@dataclass
class Holding:
    """One of the tool's holdings, as full-history computes it today."""
    ticker: str
    category: str
    name: Optional[str]
    tag: Optional[str]
    units: float
    value_gbp: float
    brokers: FrozenSet[str]     # the brokers whose notes built it
    tickers: Set[str] = field(default_factory=set)  # its key and any ticker a conversion gave it
    sedol: Optional[str] = None


# --- Arguments --------------------------------------------------------------------------------

def parse_broker_files_arg(value: str) -> Dict[str, List[str]]:
    """Read --broker-files, 'HL=a.csv,b.csv;ii=c.csv;IBKR=d.csv', into {broker: [paths]}."""
    files: Dict[str, List[str]] = {}
    canonical = {b.lower(): b for b in BROKERS}
    for part in value.split(';'):
        part = part.strip()
        if not part:
            continue
        name, sep, paths = part.partition('=')
        broker = canonical.get(name.strip().lower())
        if not sep or broker is None:
            raise ReconcileInputError(
                f"--broker-files: {part!r} is not BROKER=file,... with BROKER one of {', '.join(BROKERS)}")
        listed = [os.path.expanduser(p.strip()) for p in paths.split(',') if p.strip()]
        if not listed:
            raise ReconcileInputError(f"--broker-files: no files given for {broker}")
        files.setdefault(broker, []).extend(listed)
    if not files:
        raise ReconcileInputError("--broker-files names no files")
    return files


def read_broker_accounts(path: str) -> Dict[str, str]:
    """Read the --broker-accounts CSV, columns account,category, into {account: category}."""
    accounts = {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            account = (row.get('account') or '').strip()
            category = (row.get('category') or '').strip().lower()
            if not account:
                continue
            if category not in CATEGORIES:
                raise ReconcileInputError(
                    f"{path}: account {account} has category {row.get('category')!r}, "
                    f"not one of ISA, Taxable, Pension")
            accounts[account] = category
    return accounts


# --- Broker files -----------------------------------------------------------------------------

def _read_text(path: str) -> str:
    """A broker export as text.  H&L writes Windows-1252 (its pound sign is byte 0xA3)."""
    with open(path, 'rb') as handle:
        raw = handle.read()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    # ii prefixes its export with several byte-order marks, not one
    return text.lstrip('\ufeff')


def _number(text: Optional[str]) -> Optional[float]:
    """'£1,234.56', '1,694.680', '$-71.63' or '' as a float, or None when blank."""
    cleaned = (text or '').strip().replace(',', '').replace('£', '').replace('$', '')
    if cleaned in ('', '-'):
        return None
    return float(cleaned)


def parse_hl_file(path: str) -> Tuple[str, List[BrokerLine]]:
    """An H&L account's holdings export, as (category, lines): the account is named on line one,
    and the holdings are the table headed 'Stock'."""
    rows = list(csv.reader(io.StringIO(_read_text(path))))
    title = rows[0][0].strip() if rows and rows[0] else ''
    if 'ISA' in title:
        category = 'isa'
    elif 'Fund & Share' in title:
        category = 'taxable'
    else:
        raise ReconcileInputError(
            f"{path}: the first line names the account {title!r}, which is neither an H&L "
            f"Stocks & Shares ISA nor an H&L Fund & Share Account")

    header_index = next((i for i, row in enumerate(rows) if row and row[0].strip() == 'Stock'), None)
    if header_index is None:
        raise ReconcileInputError(f"{path}: no table headed 'Stock'")
    header = [h.strip() for h in rows[header_index]]
    units_col = header.index('Units held')
    value_col = next(i for i, h in enumerate(header) if h.startswith('Value'))

    lines = []
    for row in rows[header_index + 1:]:
        if not row or not row[0].strip() or row[0].strip() == 'Totals':
            break
        name = row[0].strip()
        lines.append(BrokerLine('HL', category, name, name, _number(row[units_col]),
                                _number(row[value_col]), path))
    return category, lines


def parse_ii_file(path: str) -> List[BrokerLine]:
    """ii's pension holdings export: Symbol, Name, Qty, ..., 'Market Value £'."""
    lines = []
    for row in csv.DictReader(io.StringIO(_read_text(path))):
        symbol = (row.get('Symbol') or '').strip()
        if not symbol:
            continue  # the Totals rows
        lines.append(BrokerLine('ii', 'pension', symbol, (row.get('Name') or symbol).strip(),
                                _number(row['Qty']), _number(row['Market Value £']), path))
    return lines


def parse_ibkr_file(path: str, accounts: Dict[str, str],
                    gbp_rate: Callable[[str], float]) -> List[BrokerLine]:
    """IBKR's accounts summary.  Positions are the per-account rows under 'Open Positions'.

    Each position's value is in its own currency, converted with gbp_rate(currency).  The rows
    with no account aggregate the accounts, and the Total rows the currencies; both are skipped.
    """
    header = None
    lines = []
    unknown = set()
    for row in csv.reader(io.StringIO(_read_text(path))):
        if len(row) < 2 or row[0] != 'Open Positions':
            continue
        if row[1] == 'Header':
            header = row[2:]
            continue
        if row[1] != 'Data' or header is None:
            continue
        position = dict(zip(header, row[2:]))
        account = (position.get('Account') or '').strip()
        if not account or (position.get('Asset Category') or '').startswith('Total'):
            continue
        if account not in accounts:
            unknown.add(account)
            continue
        value = _number(position.get('Value'))
        currency = position['Currency'].strip()
        symbol = position['Symbol'].strip()
        lines.append(BrokerLine('IBKR', accounts[account], symbol, symbol, _number(position['Quantity']),
                                None if value is None else value * gbp_rate(currency), path))
    if unknown:
        raise ReconcileInputError(
            f"{path}: --broker-accounts does not classify IBKR account(s) {', '.join(sorted(unknown))}")
    if header is None:
        raise ReconcileInputError(f"{path}: no 'Open Positions' section")
    return lines


def read_broker_files(files: Dict[str, List[str]], accounts: Optional[Dict[str, str]],
                      gbp_rate: Callable[[str], float]
                      ) -> Tuple[List[BrokerLine], Set[Tuple[str, str]]]:
    """Every line of every file, and the (broker, category) accounts the files cover."""
    lines: List[BrokerLine] = []
    covered: Set[Tuple[str, str]] = set()
    for broker, paths in files.items():
        for path in paths:
            if broker == 'HL':
                category, file_lines = parse_hl_file(path)
                covered.add(('HL', category))
            elif broker == 'ii':
                file_lines = parse_ii_file(path)
                covered.add(('ii', 'pension'))
            else:
                if accounts is None:
                    raise ReconcileInputError("an IBKR file needs --broker-accounts to classify its accounts")
                file_lines = parse_ibkr_file(path, accounts, gbp_rate)
                covered.update(('IBKR', category) for category in accounts.values())
            lines.extend(file_lines)
    return lines, covered


# --- The tool's side --------------------------------------------------------------------------

def holdings_from_review(portfolio_review, individual_stocks: pd.DataFrame) -> List[Holding]:
    """The tool's holdings: units and GBP value from full-history, identity from the notes."""
    computed = {}
    for row in individual_stocks.to_dict('records'):
        computed[(row['ticker'], row['account_type'].lower())] = row

    holdings = []
    for category, notes in portfolio_review.stock_notes.items():
        for note in notes:
            row = computed.get((note.ticker, category))
            if row is None:
                continue  # a note with no transactions: full-history skips it too
            tickers = {note.ticker}
            for txn in note.transactions or []:
                if txn.get_new_ticker():
                    tickers.add(txn.get_new_ticker())
            brokers = frozenset(NOTE_BROKER[ext] for ext in
                                (os.path.splitext(p)[1].lower() for p in note.file_paths) if ext in NOTE_BROKER)
            holdings.append(Holding(
                ticker=note.ticker, category=category, name=note.stock_name, tag=note.tag,
                units=float(row['units_held']), value_gbp=float(row['current_value'] or 0.0),
                brokers=brokers, tickers=tickers, sedol=note.sedol))
    return holdings


# --- Matching ---------------------------------------------------------------------------------

def _base(ticker: str) -> str:
    """A Yahoo ticker without its exchange suffix: DRO.AX is DRO."""
    return ticker.split('.')[0]


def _name_prefix_length(note_name: Optional[str], broker_name: str) -> int:
    """How much of the broker's name the note's name accounts for, or 0 if it is not its start.

    The note's name has to end at a word boundary, so 'Cohort' is not taken for 'Cohorts plc'.
    """
    if not note_name:
        return 0
    note, broker = note_name.strip().lower(), broker_name.strip().lower()
    if not broker.startswith(note):
        return 0
    if len(broker) > len(note) and broker[len(note)].isalnum():
        return 0
    return len(note)


def _candidates(line: BrokerLine, pool: Iterable[Holding],
                overrides: Dict[str, Dict[str, str]]) -> List[Holding]:
    pool = list(pool)
    mapped = overrides.get(line.broker, {}).get(line.identifier)
    if mapped:
        return [h for h in pool if mapped in h.tickers]
    if line.broker == 'HL':
        lengths = [(h, _name_prefix_length(h.name, line.identifier)) for h in pool if 'HL' in h.brokers]
        best = max((n for _, n in lengths), default=0)
        return [h for h, n in lengths if best and n == best]
    if line.broker == 'ii':
        return [h for h in pool
                if line.identifier == h.sedol or line.identifier in {_base(t) for t in h.tickers}]
    return [h for h in pool if line.identifier in h.tickers | {_base(t) for t in h.tickers}]


def _prefer_held(hits: List[Holding]) -> List[Holding]:
    """Of several matches, the one still held, when exactly one is: a sold-out holding of the same
    name is history, not a rival."""
    if len(hits) > 1:
        held = [h for h in hits if int(h.units) != 0]
        if len(held) == 1:
            return held
    return hits


def match_line(line: BrokerLine, holdings: List[Holding], overrides: Dict[str, Dict[str, str]],
               claimed: FrozenSet[int] = frozenset()) -> List[Holding]:
    """The holdings a line matches: its own category first, then any other.

    A holding in another category is a candidate only if no line in its own category matched it
    (`claimed`, by id).  Otherwise the same fund held at one broker in two accounts, with notes for
    only one of them, would be reported as misfiled rather than as missing its notes.
    """
    hits = _prefer_held(_candidates(line, [h for h in holdings if h.category == line.category], overrides))
    if not hits:
        hits = _prefer_held(_candidates(
            line, [h for h in holdings if h.category != line.category and id(h) not in claimed], overrides))
    return hits


# --- Reconciliation ---------------------------------------------------------------------------

def tag_in_scope(tag: Optional[str], include_tags: Optional[List[str]],
                 exclude_tags: Optional[List[str]]) -> bool:
    """The tag filters, as the notes scan applies them: an untagged holding passes both."""
    if not tag:
        return True
    if include_tags and not any(p.lower() in tag.lower() for p in include_tags):
        return False
    if exclude_tags and any(p.lower() in tag.lower() for p in exclude_tags):
        return False
    return True


ROW_COLUMNS = ['finding', 'account', 'ticker', 'stock_name', 'broker', 'notes_units', 'broker_units',
               'notes_value', 'broker_value', 'difference']


def _row(finding: str, category: str, holding: Optional[Holding], lines: List[BrokerLine],
         notes_units: Optional[int], broker_units: Optional[int],
         notes_value: Optional[float], broker_value: Optional[float], difference: str) -> Dict:
    brokers = sorted({l.broker for l in lines})
    return {
        'finding': finding,
        'account': _ACCOUNT_DISPLAY.get(category, category),
        'ticker': holding.ticker if holding else '',
        'stock_name': (holding.name if holding else None) or (lines[0].description if lines else ''),
        'broker': ', '.join(brokers),
        'notes_units': notes_units,
        'broker_units': broker_units,
        'notes_value': notes_value,
        'broker_value': broker_value,
        'difference': difference,
    }


def _broker_value(lines: List[BrokerLine]) -> Optional[float]:
    if any(l.value_gbp is None for l in lines):
        return None
    return sum(l.value_gbp for l in lines)


def reconcile(lines: List[BrokerLine], holdings: List[Holding], covered: Set[Tuple[str, str]],
              include_categories: Optional[List[str]] = None, include_tags: Optional[List[str]] = None,
              exclude_tags: Optional[List[str]] = None,
              overrides: Optional[Dict[str, Dict[str, str]]] = None) -> Tuple[List[Dict], int]:
    """Every difference between the broker lines and the tool's holdings.

    Args:
        lines: every broker line read.
        holdings: every holding the notes imply, unfiltered, so a broker line can always find its
            holding and the filters can be applied through it.
        covered: the (broker, category) accounts the broker files cover.  A holding built only
            from another broker's notes is not reported as missing from a file nobody supplied.
        include_categories, include_tags, exclude_tags: the run's filters.  The category filter
            applies to broker lines through their own category; the tag filters through the
            holding a line matches.  A line that matches nothing has no tag, so it is always
            reported.

    Returns:
        (rows, agreed): one row per finding, and how many holdings agreed in units and value.
    """
    overrides = BROKER_HOLDINGS_MAP if overrides is None else overrides

    def holding_in_scope(h: Holding) -> bool:
        return tag_in_scope(h.tag, include_tags, exclude_tags)

    rows: List[Dict] = []
    groups: Dict[Tuple[int, str], List[BrokerLine]] = {}
    by_id = {id(h): h for h in holdings}
    consumed: Set[int] = set()

    lines = [l for l in lines if not include_categories or l.category in include_categories]
    # The holdings some line matches in its own category, which no line may then claim from another
    claimed: Set[int] = set()
    for line in lines:
        own = _prefer_held(_candidates(line, [h for h in holdings if h.category == line.category], overrides))
        if len(own) == 1:
            claimed.add(id(own[0]))
    claimed = frozenset(claimed)

    for line in lines:
        hits = match_line(line, holdings, overrides, claimed)
        if len(hits) == 1:
            consumed.add(id(hits[0]))
            if holding_in_scope(hits[0]):
                groups.setdefault((id(hits[0]), line.category), []).append(line)
        elif not hits:
            rows.append(_row(NO_NOTES, line.category, None, [line], None, int(line.units),
                             None, line.value_gbp, ''))
        else:
            consumed.update(id(h) for h in hits)
            rows.append(_row(AMBIGUOUS, line.category, None, [line], None, int(line.units), None,
                             line.value_gbp, 'matches ' + ', '.join(sorted(h.ticker for h in hits))))

    agreed = 0
    for (holding_id, category), group in groups.items():
        h = by_id[holding_id]
        notes_units, broker_units = int(h.units), int(sum(l.units for l in group))
        broker_value = _broker_value(group)
        notes_value = h.value_gbp if notes_units > 0 else None
        if category != h.category:
            rows.append(_row(CATEGORY_MISMATCH, category, h, group, notes_units, broker_units, notes_value,
                             broker_value, f"notes have it in {_ACCOUNT_DISPLAY.get(h.category, h.category)}"))
            continue
        difference = broker_units - notes_units
        if difference and not (broker_units and abs(difference) < MINOR_FRACTION * abs(broker_units)):
            rows.append(_row(UNIT_DISCREPANCY, category, h, group, notes_units, broker_units, notes_value,
                             broker_value, f"{difference:+,} units"))
            continue
        if difference:
            rows.append(_row(MINOR_DIFFERENCE, category, h, group, notes_units, broker_units, notes_value,
                             broker_value, f"{difference:+,} units"))
        value_differs = (broker_value and notes_value is not None
                         and abs(notes_value - broker_value) > VALUE_TOLERANCE * abs(broker_value))
        if value_differs:
            rows.append(_row(VALUE_DISCREPANCY, category, h, group, notes_units, broker_units, notes_value,
                             broker_value, f"{(notes_value - broker_value) / broker_value:+.1%} in value"))
        if not difference and not value_differs:
            agreed += 1

    for h in holdings:
        if id(h) in consumed or int(h.units) == 0:
            continue
        if include_categories and h.category not in include_categories:
            continue
        if not holding_in_scope(h):
            continue
        accounts = {(b, h.category) for b in h.brokers}
        if accounts and not accounts & covered:
            continue  # its broker's file for this account was not supplied
        rows.append(_row(NOT_AT_BROKER, h.category, h, [], int(h.units), None,
                         h.value_gbp if h.units > 0 else None, None, ''))

    rows.sort(key=lambda r: (FINDING_ORDER.index(r['finding']), r['account'], r['ticker'], r['stock_name']))
    return rows, agreed


def has_material_findings(rows: List[Dict]) -> bool:
    """Anything a run should fail on: every finding except a minor difference."""
    return any(r['finding'] != MINOR_DIFFERENCE for r in rows)
