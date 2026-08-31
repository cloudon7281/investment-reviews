"""Invariants that must hold for any valid review, whatever the market did.

The integration tests used to compare a live run against a stored snapshot of a
previous live run.  That cannot work: the reference values are a function of market
prices on the day they were captured, not of the code, so the comparison either goes
stale and fails spuriously or is loosened until it cannot fail at all
(investment-reviews#29).

These checks assert properties instead of values.  They hold on any trading day, need
no reference file and never go stale.  Each one is chosen because it can genuinely
fail: an invariant that is true by construction is worse than no invariant, because it
reads as coverage.

They run on the results DataFrames rather than the rendered tables, because currency
formatting has already rounded those (a £3 discrepancy on £87m, and a sub-penny stock
whose price renders as £0.00).

Violations are reported, not raised: a review that has lost its benchmarks is still
worth printing.  The caller decides what a violation means.
"""

from typing import Dict, List, Optional
import pandas as pd
from logger import logger

# Rounding slack when comparing an aggregate against the rows it came from.
RECONCILIATION_TOLERANCE_GBP = 0.01


def _value(cell):
    """Return a numeric cell, unwrapping the (value, currency) tuples reviews use."""
    if isinstance(cell, tuple):
        cell = cell[0]
    return None if cell is None or pd.isna(cell) else float(cell)


def _priced_holdings(df: pd.DataFrame, table: str, units_column: str = 'units_held') -> List[str]:
    """Every holding still held must have a price and a value.

    This is the check that #28 needed: a delisted holding took the whole batch's price
    data down with it, and every row in the review silently lost its price.

    Modes name the units column differently, so it is passed in.  A missing column is
    reported rather than skipped — a check that cannot run must say so, or it reads as
    coverage it is not providing.
    """
    if df.empty:
        return []
    if units_column not in df.columns:
        return [f"{table}: cannot verify prices, no '{units_column}' column"]

    unpriced = []
    for _, row in df.iterrows():
        if (_value(row.get(units_column)) or 0) <= 0:
            continue
        if _value(row.get('current_price')) is None or _value(row.get('current_value')) is None:
            unpriced.append(str(row.get('ticker', '?')))

    if not unpriced:
        return []
    return [f"{table}: {len(unpriced)} held position(s) have no price: {', '.join(sorted(unpriced))}"]


def _high_ordering(df: pd.DataFrame, table: str) -> List[str]:
    """The smoothed and percentile highs are drawn from the same window as the raw high,
    so neither can exceed it.

    Only called for the modes that report all three highs.  Annual review reports the
    raw high alone, so there is nothing to order there.
    """
    if df.empty:
        return []
    for column in ('recent_high', 'smoothed_high', 'percentile_high'):
        if column not in df.columns:
            return [f"{table}: cannot verify high ordering, no '{column}' column"]

    violations = []
    for _, row in df.iterrows():
        high = _value(row.get('recent_high'))
        if high is None:
            continue
        for column in ('smoothed_high', 'percentile_high'):
            value = _value(row.get(column))
            if value is not None and value > high:
                violations.append(
                    f"{table}: {row.get('ticker', '?')} has {column} {value:.4f} above "
                    f"recent_high {high:.4f}"
                )
    return violations


def _group_totals_reconcile(detail_total: float, group_df: pd.DataFrame, grouping: str) -> List[str]:
    """Grouped summaries are produced by a separate pass over the holdings, so their
    totals must add back up.  A grouping that drops rows — an unexpected category, a
    null tag — shows up here and nowhere else."""
    if group_df.empty:
        return []

    grouped_total = sum(_value(v) or 0 for v in group_df['current_value'])
    if abs(grouped_total - detail_total) <= RECONCILIATION_TOLERANCE_GBP:
        return []
    return [f"{grouping} totals £{grouped_total:,.2f} do not reconcile with the "
            f"holdings total £{detail_total:,.2f}"]


def check_full_history(results: Dict[str, pd.DataFrame]) -> List[str]:
    """Check a full-history result set."""
    holdings = results.get('individual_stocks', pd.DataFrame())
    violations = _priced_holdings(holdings, 'Full Investment History')
    violations += _high_ordering(holdings, 'Full Investment History')

    if not holdings.empty:
        detail_total = sum(_value(v) or 0 for v in holdings['current_value'])
        violations += _group_totals_reconcile(detail_total, results.get('per_category', pd.DataFrame()), 'Category')
        violations += _group_totals_reconcile(detail_total, results.get('per_tag', pd.DataFrame()), 'Tag')

    return violations


def check_periodic_review(results: Dict[str, pd.DataFrame],
                          expected_benchmarks: Optional[int] = None) -> List[str]:
    """Check a periodic-review result set.

    Args:
        results: The result set from process_periodic_review
        expected_benchmarks: How many benchmarks were configured, if known
    """
    violations = []
    for category in ('new', 'retained', 'increased'):
        df = results.get(category, pd.DataFrame())
        violations += _priced_holdings(df, f"{category.title()} Stocks")
        violations += _high_ordering(df, f"{category.title()} Stocks")

    # Benchmarks are dropped silently when their prices are missing, so a review can
    # lose all of them and still print.  During #28 every one was skipped.
    if expected_benchmarks:
        found = len(results.get('benchmarks', pd.DataFrame()))
        if found < expected_benchmarks:
            violations.append(f"Benchmarks: {found} of {expected_benchmarks} produced a row")

    return violations


def check_annual_review(results: Dict[str, pd.DataFrame]) -> List[str]:
    """Check an annual-review result set.

    High ordering is not checked: annual review reports the raw 90-day high only.
    """
    holdings = results.get('individual_stocks', pd.DataFrame())
    return _priced_holdings(holdings, 'Annual Review Detail', units_column='holdings_at_end')


def report(violations: List[str], mode: str) -> bool:
    """Log any violations and say whether the review is sound.

    The prefix is what the integration tests look for, so it is part of the contract
    between a review run and the harness that checks it.

    Returns:
        True if no invariant was violated
    """
    for violation in violations:
        logger.error(f"INVARIANT VIOLATION: {violation}")
    if violations:
        logger.error(f"{mode}: {len(violations)} invariant(s) violated")
        return False
    logger.info(f"{mode}: all invariants hold")
    return True
