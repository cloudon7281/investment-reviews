"""Decision log: the investment decisions recorded at each review, and the trades that carried them out.

Each review's decisions are recorded in one YAML file, in the `decisions/` folder of the notes
tree (investment-reviews#96). A file gives the date the decisions were made and the window in
which their trades are executed; each entry names a stock, an action and its classification.
Every buy or sell of that stock inside the window belongs to that entry, which is how one
decision covers several trades, including trades in different accounts.

The links are worked out on every run rather than stored, so a log can be written before its
trades exist and filled in for past reviews without touching the transaction history. Nothing
here reads a price: a classification is what was recorded at the time, never something derived
from what happened afterwards.

Classifications use a fixed, versioned taxonomy. A file names the version it was written
under, and every version stays defined here, so a record keeps its meaning when the taxonomy
is later extended.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from list_trades_processor import _ACCOUNT_DISPLAY
from logger import logger


# Every taxonomy version ever used.  Never edit a published version: add a new one, so
# records written under the old one remain interpretable (investment-reviews#96, 4.5.5).
CLASSIFICATION_VERSIONS: Dict[int, Dict[str, Dict[str, str]]] = {
    1: {
        'buy': {
            'thesis': 'Thesis investment',
            'moonshot': 'Moonshot investment',
            'valuation': 'Valuation opportunity',
            'rebalance': 'Portfolio rebalancing',
            'replacement': 'Better expression of thesis',
            'other': 'Other',
        },
        'sell': {
            'profit-take': 'Profit-taking',
            'stop-loss': 'Stop-loss',
            'low-volatility': 'Insufficient volatility',
            'fundamentals-change': 'Deterioration in fundamentals',
            'time': 'Time-based reassessment',
            'benchmark-underperformance': 'Benchmark underperformance',
            'better-expression-available': 'Better expression available',
            'moonshot-proof-failure': 'Moonshot proof-point failure',
            'rebalance': 'Portfolio rebalancing',
            'liquidity': 'Liquidity requirement',
            'other': 'Other',
        },
        'investment_type': {
            'core': 'Core diversified investment',
            'growth': 'Thesis-based growth investment',
            'moonshot': 'Asymmetric speculative investment',
        },
    },
}

ACTIONS = ('buy', 'sell')

_FILE_KEYS = {'classification_version', 'decision_date', 'execution_window', 'decisions'}
_WINDOW_KEYS = {'start', 'end'}
_REQUIRED_DECISION_KEYS = {'ticker', 'action', 'primary_reason', 'investment_type'}
_DECISION_KEYS = _REQUIRED_DECISION_KEYS | {'secondary_reasons', 'commentary', 'linked_decision_id'}

# The transaction types a decision can be carried out by.  Transfers (bed-and-ISA) and
# corporate actions are not decisions.
_TRANSACTION_ACTIONS = {'BUY': 'buy', 'SELL': 'sell'}


@dataclass(frozen=True)
class Decision:
    """One recorded investment decision."""
    decision_id: str
    decision_date: datetime
    window_start: datetime
    window_end: datetime
    ticker: str
    action: str
    primary_reason: str
    secondary_reasons: Tuple[str, ...]
    investment_type: str
    commentary: Optional[str]
    linked_decision_id: Optional[str]
    classification_version: int
    source_file: str


@dataclass(frozen=True)
class Trade:
    """A buy or sell from the parsed notes, in the form decisions are linked against."""
    stock_name: str
    ticker: str
    account: str
    date: datetime
    action: str
    quantity: float
    value: float
    source_file: Optional[str]


@dataclass
class DecisionLinks:
    """The result of linking a decision log to the trades.

    Attributes:
        trades_by_decision: every decision's trades, keyed by decision ID; empty if none
        not_executed: decisions no trade matched
        unlogged: trades on or after the start of the first execution window that no
            decision covers
        linked_from: for each decision ID, the decisions whose linked_decision_id names it
    """
    trades_by_decision: Dict[str, List[Trade]]
    not_executed: List[Decision]
    unlogged: List[Trade]
    linked_from: Dict[str, List[str]]


class DecisionLogError(Exception):
    """The decision log is invalid.  `problems` lists every fault found, not just the first."""

    def __init__(self, problems: List[str]):
        super().__init__(f"{len(problems)} problem(s) in the decision log")
        self.problems = problems


def make_decision_id(decision_date: datetime, action: str, ticker: str) -> str:
    """The stable identifier of a decision: its date, action and stock."""
    return f"{decision_date.strftime('%Y-%m-%d')}/{action}/{ticker}"


def _to_datetime(value) -> Optional[datetime]:
    """A YAML date (parsed or as a YYYY-MM-DD string) as a datetime, or None if it is not one."""
    if isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None
    return None


def _parse_file(path: str, problems: List[str]) -> List[Decision]:
    """The decisions in one log file, appending every fault found to `problems`."""
    name = os.path.basename(path)
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as e:
        problems.append(f"{name}: cannot be read: {e}")
        return []

    if not isinstance(data, dict):
        problems.append(f"{name}: must be a mapping with {', '.join(sorted(_FILE_KEYS))}")
        return []

    faults_before = len(problems)
    for key in sorted(set(data) - _FILE_KEYS):
        problems.append(f"{name}: unknown field '{key}'")
    for key in sorted(_FILE_KEYS - set(data)):
        problems.append(f"{name}: missing field '{key}'")

    version = data.get('classification_version')
    taxonomy = CLASSIFICATION_VERSIONS.get(version) if isinstance(version, int) else None
    if 'classification_version' in data and taxonomy is None:
        problems.append(f"{name}: unknown classification_version {version!r}; "
                        f"known versions are {sorted(CLASSIFICATION_VERSIONS)}")

    decision_date = _to_datetime(data.get('decision_date'))
    if 'decision_date' in data and decision_date is None:
        problems.append(f"{name}: decision_date must be a YYYY-MM-DD date")

    window = data.get('execution_window')
    window_start = window_end = None
    if 'execution_window' in data:
        if not isinstance(window, dict) or set(window) != _WINDOW_KEYS:
            problems.append(f"{name}: execution_window must have exactly 'start' and 'end'")
        else:
            window_start, window_end = _to_datetime(window['start']), _to_datetime(window['end'])
            if window_start is None or window_end is None:
                problems.append(f"{name}: execution_window start and end must be YYYY-MM-DD dates")
            elif window_start > window_end:
                problems.append(f"{name}: execution_window starts after it ends")
            elif decision_date and decision_date > window_end:
                problems.append(f"{name}: decision_date is after the execution window ends")

    entries = data.get('decisions')
    if 'decisions' in data and not isinstance(entries, list):
        problems.append(f"{name}: decisions must be a list")
        entries = []

    if len(problems) > faults_before:
        return []

    decisions = []
    for index, entry in enumerate(entries or [], start=1):
        decision = _parse_entry(entry, f"{name} decision {index}", taxonomy, version,
                                decision_date, window_start, window_end, path, problems)
        if decision:
            decisions.append(decision)
    return decisions


def _parse_entry(entry, where: str, taxonomy: Dict[str, Dict[str, str]], version: int,
                 decision_date: datetime, window_start: datetime, window_end: datetime,
                 path: str, problems: List[str]) -> Optional[Decision]:
    """One log entry as a Decision, or None after appending its faults to `problems`."""
    if not isinstance(entry, dict):
        problems.append(f"{where}: must be a mapping")
        return None

    faults_before = len(problems)
    for key in sorted(set(entry) - _DECISION_KEYS):
        problems.append(f"{where}: unknown field '{key}'")
    for key in sorted(_REQUIRED_DECISION_KEYS - set(entry)):
        problems.append(f"{where}: missing field '{key}'")
    if len(problems) > faults_before:
        return None

    ticker = entry['ticker']
    if not isinstance(ticker, str) or not ticker.strip():
        problems.append(f"{where}: ticker must be a non-empty string")
        return None
    ticker = ticker.strip()
    where = f"{where} ({ticker})"

    action = entry['action']
    if action not in ACTIONS:
        problems.append(f"{where}: action must be one of {', '.join(ACTIONS)}, not {action!r}")
        return None
    reasons = taxonomy[action]

    primary = entry['primary_reason']
    if not isinstance(primary, str) or primary not in reasons:
        problems.append(f"{where}: primary_reason {primary!r} is not a {action} reason; "
                        f"valid reasons are {', '.join(reasons)}")

    secondary = entry.get('secondary_reasons') or []
    if not isinstance(secondary, list) or not all(isinstance(r, str) for r in secondary):
        problems.append(f"{where}: secondary_reasons must be a list of reason codes")
        secondary = []
    for reason in secondary:
        if reason not in reasons:
            problems.append(f"{where}: secondary reason {reason!r} is not a {action} reason")
    if primary in secondary:
        problems.append(f"{where}: primary reason {primary!r} is repeated as a secondary reason")
    duplicates = sorted({r for r in secondary if secondary.count(r) > 1})
    if duplicates:
        problems.append(f"{where}: duplicate secondary reasons {duplicates}")

    investment_type = entry['investment_type']
    if not isinstance(investment_type, str) or investment_type not in taxonomy['investment_type']:
        problems.append(f"{where}: investment_type must be one of "
                        f"{', '.join(taxonomy['investment_type'])}, not {investment_type!r}")

    commentary = entry.get('commentary')
    if commentary is not None and not isinstance(commentary, str):
        problems.append(f"{where}: commentary must be text")

    linked = entry.get('linked_decision_id')
    if linked is not None and not isinstance(linked, str):
        problems.append(f"{where}: linked_decision_id must be a decision ID")

    if len(problems) > faults_before:
        return None

    return Decision(
        decision_id=make_decision_id(decision_date, action, ticker),
        decision_date=decision_date,
        window_start=window_start,
        window_end=window_end,
        ticker=ticker,
        action=action,
        primary_reason=primary,
        secondary_reasons=tuple(secondary),
        investment_type=investment_type,
        commentary=commentary.strip() if commentary else None,
        linked_decision_id=linked,
        classification_version=version,
        source_file=path,
    )


def _check_across_files(decisions: List[Decision], problems: List[str]) -> None:
    """Faults that only show across the whole log: duplicate IDs, overlaps, dangling links."""
    by_id: Dict[str, Decision] = {}
    for decision in decisions:
        if decision.decision_id in by_id:
            problems.append(f"{decision.decision_id}: recorded twice, in "
                            f"{os.path.basename(by_id[decision.decision_id].source_file)} and "
                            f"{os.path.basename(decision.source_file)}")
        else:
            by_id[decision.decision_id] = decision

    # Two decisions on the same stock and action with overlapping windows would both claim
    # the trades in the overlap, so which decision a trade belongs to would be undefined.
    groups: Dict[Tuple[str, str], List[Decision]] = {}
    for decision in by_id.values():
        groups.setdefault((decision.ticker, decision.action), []).append(decision)
    for group in groups.values():
        group.sort(key=lambda d: d.window_start)
        for earlier, later in zip(group, group[1:]):
            if later.window_start <= earlier.window_end:
                problems.append(f"{earlier.decision_id} and {later.decision_id}: execution windows "
                                f"overlap, so a trade in both could belong to either")

    for decision in by_id.values():
        if decision.linked_decision_id and decision.linked_decision_id not in by_id:
            problems.append(f"{decision.decision_id}: linked_decision_id "
                            f"{decision.linked_decision_id!r} is not a recorded decision")


def load_decision_log(directory: str) -> List[Decision]:
    """Every decision in the log, validated, ordered by decision date.

    A missing directory is an empty log: the log starts with the first review recorded in it.

    Raises:
        DecisionLogError: listing every fault in the log, if there is any.
    """
    if not os.path.isdir(directory):
        logger.info(f"No decision log at {directory}")
        return []

    problems: List[str] = []
    decisions: List[Decision] = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(('.yaml', '.yml')):
            decisions.extend(_parse_file(os.path.join(directory, name), problems))
    _check_across_files(decisions, problems)
    if problems:
        raise DecisionLogError(problems)

    logger.info(f"Decision log: {len(decisions)} decisions from {directory}")
    return sorted(decisions, key=lambda d: (d.decision_date, d.decision_id))


def trades_from(portfolio_review) -> List[Trade]:
    """Every buy and sell in the parsed notes, in date order."""
    trades = []
    for account, stock_notes in portfolio_review.stock_notes.items():
        for stock_note in stock_notes:
            for txn in stock_note.transactions:
                action = _TRANSACTION_ACTIONS.get(txn.transaction_type)
                if action:
                    trades.append(Trade(
                        stock_name=stock_note.stock_name,
                        ticker=stock_note.ticker,
                        account=account,
                        date=txn.date,
                        action=action,
                        quantity=txn.quantity,
                        value=txn.total_amount,
                        source_file=txn.source_file,
                    ))
    return sorted(trades, key=lambda t: t.date)


def link_decisions(decisions: List[Decision], trades: List[Trade]) -> DecisionLinks:
    """Attach each trade to the decision whose stock, action and execution window it falls in.

    The log's validation guarantees no trade can fall in two decisions' windows.
    """
    trades_by_decision: Dict[str, List[Trade]] = {d.decision_id: [] for d in decisions}
    by_stock: Dict[Tuple[str, str], List[Decision]] = {}
    for decision in decisions:
        by_stock.setdefault((decision.ticker, decision.action), []).append(decision)

    log_start = min((d.window_start for d in decisions), default=None)
    unlogged = []
    for trade in trades:
        day = datetime(trade.date.year, trade.date.month, trade.date.day)
        match = next((d for d in by_stock.get((trade.ticker, trade.action), [])
                      if d.window_start <= day <= d.window_end), None)
        if match:
            trades_by_decision[match.decision_id].append(trade)
        elif log_start and day >= log_start:
            unlogged.append(trade)

    linked_from: Dict[str, List[str]] = {}
    for decision in decisions:
        if decision.linked_decision_id:
            linked_from.setdefault(decision.linked_decision_id, []).append(decision.decision_id)

    return DecisionLinks(
        trades_by_decision=trades_by_decision,
        not_executed=[d for d in decisions if not trades_by_decision[d.decision_id]],
        unlogged=unlogged,
        linked_from=linked_from,
    )


def check_tables(decisions: List[Decision], links: DecisionLinks) -> Dict[str, pd.DataFrame]:
    """The decision-log check as three tables: decisions, their trades, and unlogged trades."""
    def trade_row(trade: Trade) -> dict:
        return {
            'stock_name': trade.stock_name,
            'ticker': trade.ticker,
            'account': _ACCOUNT_DISPLAY.get(trade.account, trade.account),
            'date': trade.date,
            'action': trade.action.capitalize(),
            # Thousands separators keep the column text, so it is not reformatted as a float
            'quantity': f"{trade.quantity:,.6f}".rstrip('0').rstrip('.'),
            'value_gbp': trade.value,
            'note': os.path.basename(trade.source_file) if trade.source_file else None,
        }

    decision_rows, trade_rows = [], []
    for d in decisions:
        trades = links.trades_by_decision[d.decision_id]
        decision_rows.append({
            'decision_id': d.decision_id,
            'ticker': d.ticker,
            'action': d.action.capitalize(),
            'window_start': d.window_start,
            'window_end': d.window_end,
            'primary_reason': d.primary_reason,
            'secondary_reasons': ', '.join(d.secondary_reasons),
            'investment_type': d.investment_type,
            'trades': len(trades),
            'status': 'executed' if trades else 'not executed',
            'linked_to': d.linked_decision_id or '',
            'linked_from': ', '.join(links.linked_from.get(d.decision_id, [])),
        })
        trade_rows.extend({'decision_id': d.decision_id, **trade_row(t)} for t in trades)

    return {
        'decisions': pd.DataFrame(decision_rows),
        'decision_trades': pd.DataFrame(trade_rows),
        'unlogged_trades': pd.DataFrame([trade_row(t) for t in links.unlogged]),
    }
