"""Outcomes of the decisions in the decision log (investment-reviews#96).

For each logged purchase: what the shares it bought have returned, realised and unrealised.
For each logged sale: what the shares it sold would have been worth had they been kept.  Both
are measured at the as-of date and 3, 6, 12 and 24 months after each decision's first trade,
and grouped into cohorts by the calendar month of the decision date.

Only logged trades are decisions.  Every other trade -- a dividend reinvestment, a holding from
before the log, a capital-gains swap -- is left out of the figures as a decision, but still
moves shares, so it still counts when sales are matched to purchases.

How shares are followed from the trades to the decisions that own them:

- Lots are matched first in, first out within each account.  Every purchase adds a lot, owned
  by its decision if the log covers it and by no decision otherwise.  Every sale, logged or
  not, takes from the oldest lots first, and its proceeds go to the decisions owning them.
- Units are counted in today's terms: scaled by the splits and conversions after the trade,
  as Yahoo's price history is.  A split then changes neither a lot nor its value.
- A bed-and-ISA move takes lots from one account and gives the same lots, with their
  decisions, to the other.  It is neither a sale nor a purchase.
- A demerger's new shares, and the shares of a share grant, are given to the lots held in
  that account, in proportion to their units.

Each outcome is set beside a benchmark: the same cash put into US equities on the same dates
(see Benchmark).

Prices are Yahoo closes in GBP, looked up with the existing 14-day lookback.  A ticker Yahoo
has no data for is treated as delisted: worth nothing at the as-of date, and N/A at a fixed
horizon, since Yahoo drops a delisted stock's whole history.  Distributions are not included.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from dateutil.relativedelta import relativedelta

import decision_log
import financial_metrics
import holdings_calculator
import transaction_processor
from decision_log import Decision
from list_trades_processor import _ACCOUNT_DISPLAY
from logger import logger
from periodic_review_processor import BENCHMARKS

HORIZON_MONTHS = (3, 6, 12, 24)

# Annualised returns are N/A until this many months have passed since the first trade.
ANNUALISE_AFTER_MONTHS = 3

AS_OF = 'As of'

# The benchmark every outcome is compared with: periodic-review's "Benchmarks - US Equities",
# an equal-weight basket of the indices it lists under that tag (#96).
BENCHMARK_TAG = 'Benchmarks - US Equities'
BENCHMARK_TICKERS = [ticker for tag, ticker, _ in BENCHMARKS if tag == BENCHMARK_TAG]

# Units below this are rounding left by proportional allocation, not a holding.
_UNIT_EPSILON = 1e-6

# A P&L smaller than half a penny is flat: neither a gain nor a loss.
_FLAT_PNL = 0.005

# Same-day order: purchases first, so a sale can take from a lot bought that day; the
# sending leg of a move before its receiving leg, and a demerger's parent before its child.
_EVENT_ORDER = {'BUY': 0, 'STOCK_CONVERSION': 1, 'SELL': 5}

NoteKey = Tuple[str, str]  # (ticker, account), as the parsed notes key a holding


class PriceFetchError(Exception):
    """Prices could not be fetched for these tickers, so the report would value them wrongly."""


@dataclass
class Movement:
    """A change to the shares a decision owns, or a trade of a sale decision.

    `units` are in today's terms and signed: positive when the decision gains shares.  `cash`
    is what the movement paid or received, negative for a purchase; None if it moved no cash.
    """
    decision_id: str
    date: datetime
    event: str
    note: NoteKey
    units: float
    cash: Optional[float]
    source_file: Optional[str]


@dataclass
class Outcome:
    """A decision measured at one date.

    For a purchase: cost, the proceeds realised by then, and the value of the shares still
    held.  For a sale: the proceeds, and the value the shares sold would have had.
    Value fields are None when a price is missing; `flag` then says why.
    """
    decision_id: str
    measured_at: str
    date: datetime
    invested: float
    realised: float
    held_value: Optional[float]
    total_value: Optional[float]
    pnl: Optional[float]
    total_return: Optional[float]
    annualised: Optional[float]
    still_held: bool
    cash_flows: List[Tuple[datetime, float]] = field(default_factory=list)
    flag: Optional[str] = None
    benchmark_value: Optional[float] = None
    benchmark_return: Optional[float] = None
    benchmark_annualised: Optional[float] = None
    benchmark_flows: List[Tuple[datetime, float]] = field(default_factory=list)


# A lot is [owner decision ID or None, units, date acquired].  A holding's lots are kept in
# order of acquisition, so taking from the front is first in, first out.
Lot = list


def _lot_units(lots) -> float:
    return sum(lot[1] for lot in lots)


def _take(lots: List[Lot], units: float) -> List[Lot]:
    """Remove `units` from the oldest lots first; return the parts taken, as lots."""
    taken = []
    while units > _UNIT_EPSILON and lots:
        owner, available, acquired = lots[0]
        used = min(available, units)
        taken.append([owner, used, acquired])
        units -= used
        if available - used > _UNIT_EPSILON:
            lots[0][1] = available - used
        else:
            lots.pop(0)
    return taken


def _add(lots: List[Lot], lot: Lot) -> None:
    """Add a lot after every lot acquired on or before it."""
    position = len(lots)
    while position > 0 and lots[position - 1][2] > lot[2]:
        position -= 1
    lots.insert(position, lot)


def follow_decisions(stock_notes: Dict[str, list], decisions: List[Decision]) -> Dict[str, List[Movement]]:
    """Every decision's movements, from replaying all the trades in date order.

    Args:
        stock_notes: PortfolioReview.stock_notes -- every account's holdings and trades.
        decisions: the whole decision log, not only the decisions being reported, so that
            lots owned by an earlier decision are not mistaken for anyone else's.
    """
    by_stock = decision_log.decisions_by_stock(decisions)
    movements: Dict[str, List[Movement]] = {d.decision_id: [] for d in decisions}

    events = []
    for notes in stock_notes.values():
        for note in notes:
            for txn in note.transactions:
                if txn.transaction_type == 'TRANSFER':
                    order = 2 if txn.quantity < 0 else 3 if txn.quantity == 0 else 4
                else:
                    order = _EVENT_ORDER[txn.transaction_type]
                events.append((txn.date, order, len(events), note, txn))
    events.sort(key=lambda event: event[:3])

    lots: Dict[NoteKey, List[Lot]] = {}
    moving: Dict[Tuple[str, object], List[Lot]] = {}
    demerging: Dict[Tuple[str, object], List[Lot]] = {}

    def record(owner, date, event, key, units, cash, txn):
        if owner is not None and owner in movements:
            movements[owner].append(Movement(owner, date, event, key, units, cash, txn.source_file))

    def give(held, key, txn, parts, units, event):
        """Add `units` to this holding as lots like `parts`: same owners and dates, in proportion."""
        total = _lot_units(parts)
        for owner, part_units, acquired in parts:
            share = units * part_units / total
            _add(held, [owner, share, acquired])
            record(owner, txn.date, event, key, share, None, txn)

    for date, _, _, note, txn in events:
        key = (note.ticker, note.category)
        held = lots.setdefault(key, [])
        units = abs(txn.quantity) * holdings_calculator.get_subsequent_stock_splits(note.transactions, date)
        day = date.date()

        if txn.transaction_type == 'BUY':
            decision = decision_log.matching_decision(by_stock, note.ticker, 'buy', date)
            owner = decision.decision_id if decision else None
            _add(held, [owner, units, date])
            record(owner, date, 'Bought', key, units, -txn.total_amount, txn)

        elif txn.transaction_type == 'SELL':
            if units > _lot_units(held) + _UNIT_EPSILON:
                logger.warning(f"{note.ticker} in {note.category}: sale of {units:g} units on {day} "
                               f"exceeds the {_lot_units(held):g} held; the excess belongs to no purchase")
            for owner, part, _ in _take(held, units):
                record(owner, date, 'Sold', key, -part, txn.total_amount * part / units, txn)
            decision = decision_log.matching_decision(by_stock, note.ticker, 'sell', date)
            if decision:
                record(decision.decision_id, date, 'Sold', key, -units, txn.total_amount, txn)

        elif txn.transaction_type == 'TRANSFER' and txn.quantity < 0:
            taken = _take(held, units)
            moving.setdefault((note.ticker, day), []).extend(taken)
            for owner, part, _ in taken:
                record(owner, date, 'Moved out', key, -part, None, txn)

        elif txn.transaction_type == 'TRANSFER' and txn.quantity == 0:
            # The parent's side of a demerger: it gives up cost, not shares.  The new shares
            # are due on the shares held before that day, not on any bought on it.
            demerging[(note.category, day)] = [list(lot) for lot in held if lot[2] < date]

        elif txn.transaction_type == 'TRANSFER':
            if moving.get((note.ticker, day)):
                give(held, key, txn, moving.pop((note.ticker, day)), units, 'Moved in')
            elif demerging.get((note.category, day)):
                give(held, key, txn, demerging.pop((note.category, day)), units, 'Demerged in')
            else:
                logger.info(f"{note.ticker} in {note.category}: {units:g} units transferred in on {day} "
                            f"with no matching transfer out or demerger; they belong to no purchase")
                _add(held, [None, units, date])

        elif txn.transaction_type == 'STOCK_CONVERSION' and txn.quantity == 0 and txn.new_quantity:
            # A share grant adds shares without converting the existing ones.
            # Each lot held before that day grows in proportion, in place, so the lots keep
            # their order.
            granted = txn.new_quantity * holdings_calculator.get_subsequent_stock_splits(note.transactions, date)
            entitled = [lot for lot in held if lot[2] < date]
            total = _lot_units(entitled)
            if total > _UNIT_EPSILON:
                for lot in entitled:
                    share = granted * lot[1] / total
                    lot[1] += share
                    record(lot[0], date, 'Granted', key, share, None, txn)

    for (ticker, day), parts in moving.items():
        if parts:
            logger.warning(f"{ticker}: {_lot_units(parts):g} units transferred out on {day} "
                           f"were not transferred in anywhere; their purchases lose them")
    return movements


class Prices:
    """GBP closes for each holding, under the ticker it is priced by today."""

    def __init__(self, price_data: Dict[str, pd.DataFrame], current_tickers: Dict[NoteKey, str]):
        self.price_data = price_data
        self.current_tickers = current_tickers

    def ticker(self, key: NoteKey) -> str:
        return self.current_tickers.get(key, key[0])

    def delisted(self, key: NoteKey) -> bool:
        """Yahoo has no data at all for this ticker."""
        frame = self.price_data.get(self.ticker(key))
        return frame is not None and frame.empty

    def price(self, key: NoteKey, date: datetime) -> Optional[float]:
        return holdings_calculator.get_stock_price_from_data(self.ticker(key), date, self.price_data)


class Benchmark:
    """An equal-weight basket of indices, in GBP.

    Each amount invested is split equally across the indices on the day it goes in, and
    held as units of each.  The basket's value is then what that mix would be worth.
    """

    def __init__(self, price_data: Dict[str, pd.DataFrame], tickers: List[str]):
        self.price_data = price_data
        self.tickers = tickers

    def prices(self, date: datetime) -> Optional[Dict[str, float]]:
        """Every index's GBP close at `date`, or None if any is missing."""
        found = {t: holdings_calculator.get_stock_price_from_data(t, date, self.price_data) for t in self.tickers}
        return None if any(p is None for p in found.values()) else found


def _sold_fraction(held: Dict[NoteKey, float], movement: Movement, prices: Prices) -> Optional[float]:
    """The fraction of a purchase's holding that a sale movement disposes of.

    Measured in units when the holding is one stock, however many accounts it is in.  After
    a demerger it is two stocks, and units of one are not units of the other, so the fraction
    is of the holding's value that day; None if a price is missing.
    """
    by_ticker: Dict[str, float] = {}
    for key, units in held.items():
        if units > _UNIT_EPSILON:
            by_ticker[prices.ticker(key)] = by_ticker.get(prices.ticker(key), 0.0) + units
    sold = -movement.units
    if len(by_ticker) <= 1:
        total = sum(by_ticker.values())
        return min(sold / total, 1.0) if total > _UNIT_EPSILON else 1.0
    values = {}
    for ticker, units in by_ticker.items():
        key = next(k for k in held if prices.ticker(k) == ticker)
        price = prices.price(key, movement.date)
        if price is None:
            return None
        values[ticker] = units * price
    total = sum(values.values())
    price = prices.price(movement.note, movement.date)
    return min(sold * price / total, 1.0) if total > 0 else None


def benchmark_outcome(decision: Decision, upto: List[Movement], date: datetime, prices: Prices,
                      benchmark: Benchmark) -> Tuple[Optional[float], List[Tuple[datetime, float]]]:
    """What the decision's cash would have made in the benchmark: its value at `date`, and its flows.

    A purchase's cost goes into the basket on its purchase dates, and each sale of its shares
    sells the same fraction of the basket.  A sale's proceeds go into the basket on its sale
    dates.  The value is the basket's proceeds plus what is left in it; None if a price is missing.
    """
    units = {t: 0.0 for t in benchmark.tickers}
    held: Dict[NoteKey, float] = {}
    realised = 0.0
    flows = []

    def invest(amount, when):
        closes = benchmark.prices(when)
        if closes is None:
            return False
        for ticker in benchmark.tickers:
            units[ticker] += amount / len(benchmark.tickers) / closes[ticker]
        return True

    for m in upto:
        if decision.action == 'sell':
            if not invest(m.cash, m.date):
                return None, []
            flows.append((m.date, -m.cash))
            continue
        if m.event == 'Bought':
            if not invest(-m.cash, m.date):
                return None, []
            flows.append((m.date, m.cash))
        elif m.event == 'Sold':
            fraction = _sold_fraction(held, m, prices)
            closes = benchmark.prices(m.date)
            if fraction is None or closes is None:
                return None, []
            proceeds = fraction * sum(units[t] * closes[t] for t in benchmark.tickers)
            for ticker in benchmark.tickers:
                units[ticker] *= 1 - fraction
            realised += proceeds
            flows.append((m.date, proceeds))
        held[m.note] = held.get(m.note, 0.0) + m.units

    closes = benchmark.prices(date)
    if closes is None:
        return None, []
    remaining = sum(units[t] * closes[t] for t in benchmark.tickers)
    return realised + remaining, flows + [(date, remaining)]


def _own_event(decision: Decision) -> str:
    """The movement that is the decision's own trade, rather than a later effect on its shares."""
    return 'Bought' if decision.action == 'buy' else 'Sold'


def first_trade(decision: Decision, movements: List[Movement]) -> Optional[datetime]:
    """The date of the decision's first trade, from which its horizons are measured."""
    return min((m.date for m in movements if m.event == _own_event(decision)), default=None)


def measure(decision: Decision, movements: List[Movement], date: datetime, measured_at: str,
            prices: Prices, at_as_of: bool, benchmark: Optional[Benchmark] = None) -> Optional[Outcome]:
    """The decision's outcome at `date`, from its movements up to and including that date.

    Returns None if the decision had no trade by then.  Later movements cannot affect it.
    """
    upto = [m for m in movements if m.date <= date]
    own = [m for m in upto if m.event == _own_event(decision)]
    if not own:
        return None

    units: Dict[NoteKey, float] = {}
    for m in upto:
        units[m.note] = units.get(m.note, 0.0) + m.units

    if decision.action == 'buy':
        invested = -sum(m.cash for m in own)
        realised = sum(m.cash for m in upto if m.event == 'Sold')
        flows = [(m.date, m.cash) for m in upto if m.cash is not None]
        exposure = {key: u for key, u in units.items() if u > _UNIT_EPSILON}
    else:
        # The counterfactual: the proceeds are given up to keep the shares sold.
        invested = sum(m.cash for m in own)
        realised = invested
        flows = [(m.date, -m.cash) for m in own]
        exposure = {key: -u for key, u in units.items() if -u > _UNIT_EPSILON}

    held_value: Optional[float] = 0.0
    flags = []
    for key, held in sorted(exposure.items()):
        price = prices.price(key, date)
        if price is None and prices.delisted(key) and at_as_of:
            price = 0.0
            flags.append(f"{prices.ticker(key)} delisted: valued at zero")
        elif price is None:
            held_value = None
            reason = "delisted, no price history" if prices.delisted(key) else "no price within 14 days"
            flags.append(f"{prices.ticker(key)}: {reason}")
            continue
        if held_value is not None:
            held_value += held * price

    if held_value is None:
        total_value = pnl = total_return = annualised = None
    else:
        total_value = realised + held_value if decision.action == 'buy' else held_value
        pnl = total_value - invested
        total_return = pnl / invested if invested else None
        flows = flows + [(date, held_value)]
        annualised = None
        if date >= min(m.date for m in own) + relativedelta(months=ANNUALISE_AFTER_MONTHS):
            annualised = financial_metrics.calculate_mwrr([d for d, _ in flows], [v for _, v in flows])

    benchmark_value, benchmark_flows = (None, [])
    if benchmark is not None:
        benchmark_value, benchmark_flows = benchmark_outcome(decision, upto, date, prices, benchmark)
    benchmark_return = benchmark_annualised = None
    if benchmark_value is not None and invested:
        benchmark_return = benchmark_value / invested - 1
        if date >= min(m.date for m in own) + relativedelta(months=ANNUALISE_AFTER_MONTHS):
            benchmark_annualised = financial_metrics.calculate_mwrr(
                [d for d, _ in benchmark_flows], [v for _, v in benchmark_flows])

    return Outcome(
        decision_id=decision.decision_id, measured_at=measured_at, date=date,
        invested=invested, realised=realised, held_value=held_value, total_value=total_value,
        pnl=pnl, total_return=total_return, annualised=annualised,
        still_held=decision.action == 'buy' and bool(exposure),
        cash_flows=flows if held_value is not None else [],
        flag="; ".join(flags) or None,
        benchmark_value=benchmark_value, benchmark_return=benchmark_return,
        benchmark_annualised=benchmark_annualised, benchmark_flows=benchmark_flows,
    )


def horizon_label(months: int) -> str:
    return f"{months} months"


def measure_all(decisions: List[Decision], movements: Dict[str, List[Movement]], prices: Prices,
                eval_date: datetime, benchmark: Optional[Benchmark] = None) -> Dict[str, List[Outcome]]:
    """Each decision's outcome at the as-of date and at every horizon that has passed by then."""
    outcomes: Dict[str, List[Outcome]] = {}
    for decision in decisions:
        moves = movements[decision.decision_id]
        start = first_trade(decision, moves)
        if start is None or start > eval_date:
            continue
        results = [measure(decision, moves, eval_date, AS_OF, prices, at_as_of=True, benchmark=benchmark)]
        for months in HORIZON_MONTHS:
            horizon = start + relativedelta(months=months)
            if horizon <= eval_date:
                results.append(measure(decision, moves, horizon, horizon_label(months), prices,
                                       at_as_of=False, benchmark=benchmark))
        outcomes[decision.decision_id] = results
    return outcomes


def cohort_stats(outcomes: List[Outcome]) -> dict:
    """The outcome statistics of a cohort of decisions, all measured at the same horizon.

    A decision with a missing price is counted as unpriced and left out of every other
    figure, never treated as a loss.  The bands and multiples apply alike to a purchase
    (value against cost) and to a sale (value retained against proceeds).
    """
    priced = [o for o in outcomes if o.total_value is not None]

    def flat(o):
        return abs(o.pnl) < _FLAT_PNL

    def count(predicate):
        return sum(1 for o in priced if predicate(o))

    invested = sum(o.invested for o in priced)
    total_value = sum(o.total_value for o in priced)
    pnl = total_value - invested
    annualised = [o.annualised for o in priced if o.annualised is not None]

    # Annualised only once every decision in it has been held long enough to be.
    held_long_enough = bool(priced) and len(annualised) == len(priced)
    cohort_annualised = None
    if held_long_enough:
        flows = [flow for o in priced for flow in o.cash_flows]
        cohort_annualised = financial_metrics.calculate_mwrr([d for d, _ in flows], [v for _, v in flows])

    # The benchmark over the same decisions, so it is comparable; N/A if any lacks one.
    benchmark_return = benchmark_annualised = None
    if priced and invested and all(o.benchmark_value is not None for o in priced):
        benchmark_return = sum(o.benchmark_value for o in priced) / invested - 1
        if held_long_enough:
            flows = [flow for o in priced for flow in o.benchmark_flows]
            benchmark_annualised = financial_metrics.calculate_mwrr([d for d, _ in flows], [v for _, v in flows])

    return {
        'decisions': len(outcomes),
        'unpriced': len(outcomes) - len(priced),
        'still_held': sum(1 for o in outcomes if o.still_held),
        'profitable': count(lambda o: not flat(o) and o.pnl > 0),
        'x2': count(lambda o: o.total_value >= 2 * o.invested),
        'x5': count(lambda o: o.total_value >= 5 * o.invested),
        'x10': count(lambda o: o.total_value >= 10 * o.invested),
        'loss_under_20': count(lambda o: not flat(o) and -0.2 < o.total_return < 0),
        'loss_20_to_50': count(lambda o: not flat(o) and -0.5 <= o.total_return <= -0.2),
        'loss_over_50': count(lambda o: o.total_return < -0.5),
        'flat': count(flat),
        'invested': invested if priced else None,
        'total_value': total_value if priced else None,
        'pnl': pnl if priced else None,
        'aggregate_return': pnl / invested if invested else None,
        'value_added': -pnl if priced else None,
        'mean_annualised': sum(annualised) / len(annualised) if annualised else None,
        'annualised_count': len(annualised),
        'cohort_annualised': cohort_annualised,
        'benchmark_return': benchmark_return,
        'benchmark_annualised': benchmark_annualised,
    }


def _month(decision: Decision) -> str:
    return decision.decision_date.strftime('%Y-%m')


def _primary_reason(decision: Decision) -> str:
    return decision.primary_reason


def cohort_table(decisions: List[Decision], outcomes: Dict[str, List[Outcome]], measured_at: str,
                 group_by=_month, column: str = 'month') -> pd.DataFrame:
    """One row per cohort with its statistics at `measured_at`, and a total row.

    Cohorts are decision months unless `group_by` says otherwise; `column` names the column
    holding each cohort's name.
    """
    cohorts: Dict[str, List[Outcome]] = {}
    for decision in decisions:
        outcome = next((o for o in outcomes.get(decision.decision_id, []) if o.measured_at == measured_at), None)
        if outcome:
            cohorts.setdefault(group_by(decision), []).append(outcome)
    if not cohorts:
        return pd.DataFrame()
    # Every row has a type, so the writers rule off the total from the cohorts above it.
    rows = [{column: name, 'horizon': measured_at, '_row_type': 'cohort', **cohort_stats(cohorts[name])}
            for name in sorted(cohorts)]
    rows.append({column: 'Total', 'horizon': measured_at, '_row_type': 'total',
                 **cohort_stats([o for name in cohorts for o in cohorts[name]])})
    return pd.DataFrame(rows)


def horizon_table(decisions: List[Decision], outcomes: Dict[str, List[Outcome]]) -> pd.DataFrame:
    """The cohort statistics at each fixed horizon, for the months with an eligible decision."""
    tables = [cohort_table(decisions, outcomes, horizon_label(months)) for months in HORIZON_MONTHS]
    tables = [t for t in tables if not t.empty]
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


def _joined(values) -> Optional[str]:
    return ", ".join(values) or None


def decision_table(decisions: List[Decision], movements: Dict[str, List[Movement]],
                   outcomes: Dict[str, List[Outcome]], linked_from: Dict[str, List[str]]) -> pd.DataFrame:
    """One row per decision: its classification, trades and the horizons it is measured at."""
    rows = []
    for decision in decisions:
        own = [m for m in movements[decision.decision_id] if m.event == _own_event(decision)]
        measured = [o.measured_at for o in outcomes.get(decision.decision_id, []) if o.measured_at != AS_OF]
        rows.append({
            'decision_id': decision.decision_id,
            'ticker': decision.ticker,
            'action': decision.action.capitalize(),
            'decision_date': decision.decision_date,
            'first_trade': min((m.date for m in own), default=None),
            'last_trade': max((m.date for m in own), default=None),
            'accounts': _joined(sorted({_ACCOUNT_DISPLAY.get(m.note[1], m.note[1]) for m in own})),
            'status': 'executed' if decision.decision_id in outcomes else 'not executed',
            'primary_reason': decision.primary_reason,
            'secondary_reasons': _joined(decision.secondary_reasons),
            'investment_type': decision.investment_type,
            'classification_version': decision.classification_version,
            'linked_to': decision.linked_decision_id,
            'linked_from': _joined(linked_from.get(decision.decision_id, [])),
            'horizons': _joined(m.split()[0] for m in measured),
            'commentary': decision.commentary,
        })
    return pd.DataFrame(rows)


def outcome_table(decisions: List[Decision], outcomes: Dict[str, List[Outcome]]) -> pd.DataFrame:
    """One row per decision per measurement, for reconciling the cohorts to their decisions."""
    rows = []
    for decision in decisions:
        for o in outcomes.get(decision.decision_id, []):
            rows.append({
                'decision_id': o.decision_id,
                'ticker': decision.ticker,
                'measured_at': o.measured_at,
                'date': o.date,
                'invested': o.invested,
                'realised': o.realised,
                'held_value': o.held_value,
                'total_value': o.total_value,
                'pnl': o.pnl,
                'total_return': o.total_return,
                'annualised': o.annualised,
                'value_added': -o.pnl if o.pnl is not None else None,
                'benchmark_value': o.benchmark_value,
                'benchmark_return': o.benchmark_return,
                'benchmark_annualised': o.benchmark_annualised,
                'still_held': 'Yes' if o.still_held else 'No',
                'flag': o.flag,
            })
    return pd.DataFrame(rows)


def movement_table(decisions: List[Decision], movements: Dict[str, List[Movement]]) -> pd.DataFrame:
    """Every trade and share movement behind the decisions, with the note it came from."""
    rows = []
    for decision in decisions:
        for m in movements[decision.decision_id]:
            rows.append({
                'decision_id': m.decision_id,
                'date': m.date,
                'event': m.event,
                'ticker': m.note[0],
                'account': _ACCOUNT_DISPLAY.get(m.note[1], m.note[1]),
                'units': round(m.units, 4),
                'cash': m.cash,
                'note': m.source_file and m.source_file.rsplit('/', 1)[-1],
            })
    return pd.DataFrame(rows)


def current_tickers(stock_notes: Dict[str, list]) -> Dict[NoteKey, str]:
    """The ticker each holding is priced under today, after any conversion that renamed it."""
    tickers = {}
    for notes in stock_notes.values():
        for note in notes:
            result = transaction_processor.calculate_transactions_through_date(
                note.transactions, datetime.now(), include_investment_threshold=False)
            tickers[(note.ticker, note.category)] = result['current_ticker'] or note.ticker
    return tickers


def process_decision_outcomes(portfolio_review, log_dir: str, start_date: datetime,
                              end_date: Optional[datetime], eval_date: Optional[datetime],
                              market_data_fetcher) -> Dict[str, object]:
    """The decision outcomes report for the decisions dated from start_date to end_date.

    Raises:
        decision_log.DecisionLogError: if the log is invalid.
        PriceFetchError: if prices could not be fetched for a ticker the report values.
    """
    # Whole days: trades are dated at midnight, and a horizon is a date, not a time.
    eval_date = eval_date or datetime.now()
    eval_date = datetime(eval_date.year, eval_date.month, eval_date.day)
    end_date = end_date or eval_date

    all_decisions = decision_log.load_decision_log(log_dir)
    movements = follow_decisions(portfolio_review.stock_notes, all_decisions)
    decisions = sorted((d for d in all_decisions if start_date <= d.decision_date <= end_date),
                       key=lambda d: (d.decision_date, d.action, d.ticker))
    links = decision_log.link_decisions(all_decisions, decision_log.trades_from(portfolio_review))

    keys = sorted({m.note for d in decisions for m in movements[d.decision_id] if m.date <= eval_date})
    tickers_by_key = current_tickers(portfolio_review.stock_notes)
    tickers = sorted({tickers_by_key.get(key, key[0]) for key in keys})
    starts = [first_trade(d, movements[d.decision_id]) for d in decisions]
    starts = [s for s in starts if s is not None]
    price_data = {}
    if tickers and starts:
        logger.info(f"Fetching prices for {len(tickers)} tickers from {min(starts):%Y-%m-%d} to {eval_date:%Y-%m-%d}")
        price_data = market_data_fetcher.batch_get_stock_prices(tickers, min(starts), eval_date)
        # Fetched apart from the holdings, so an index never shares a holding's ticker map.
        benchmark_data = market_data_fetcher.batch_get_stock_prices(BENCHMARK_TICKERS, min(starts), eval_date)
        failed = sorted(t for t in tickers + BENCHMARK_TICKERS if t in market_data_fetcher.fetch_errors)
        if failed:
            raise PriceFetchError(f"Prices could not be fetched for {', '.join(failed)}; "
                                  f"the report would value them as delisted")
    else:
        benchmark_data = {}

    prices = Prices(price_data, tickers_by_key)
    outcomes = measure_all(decisions, movements, prices, eval_date, Benchmark(benchmark_data, BENCHMARK_TICKERS))

    purchases = [d for d in decisions if d.action == 'buy']
    sales = [d for d in decisions if d.action == 'sell']
    by_stock = decision_log.decisions_by_stock(all_decisions)
    left_out = [t for t in decision_log.trades_from(portfolio_review)
                if start_date <= t.date <= eval_date
                and decision_log.matching_decision(by_stock, t.ticker, t.action, t.date) is None]

    return {
        'purchase_cohorts': cohort_table(purchases, outcomes, AS_OF),
        'sale_cohorts': cohort_table(sales, outcomes, AS_OF),
        'purchase_reasons': cohort_table(purchases, outcomes, AS_OF, _primary_reason, 'primary_reason'),
        'sale_reasons': cohort_table(sales, outcomes, AS_OF, _primary_reason, 'primary_reason'),
        'purchase_horizons': horizon_table(purchases, outcomes),
        'sale_horizons': horizon_table(sales, outcomes),
        'decisions': decision_table(decisions, movements, outcomes, links.linked_from),
        'purchase_outcomes': outcome_table(purchases, outcomes),
        'sale_outcomes': outcome_table(sales, outcomes),
        'movements': movement_table(decisions, movements),
        'summary': {
            'start_date': start_date,
            'end_date': end_date,
            'eval_date': eval_date,
            'decisions': len(decisions),
            'not_executed': len(decisions) - len(outcomes),
            'left_out_trades': len(left_out),
            'delisted': sorted({prices.ticker(key) for key in keys if prices.delisted(key)}),
            'unpriced': sum(1 for results in outcomes.values() for o in results if o.total_value is None),
        },
    }
