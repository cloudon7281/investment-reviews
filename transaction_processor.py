"""Transaction data transformation and aggregation.

This module handles conversion of StockTransaction lists into formats
needed for financial calculations. It knows about the portfolio-specific
data structures but delegates actual financial calculations to financial_metrics.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from logger import logger
import financial_metrics


def transaction_to_cashflow(transaction) -> Optional[Tuple[datetime, float]]:
    """Convert a StockTransaction to a cashflow tuple.

    Args:
        transaction: StockTransaction object

    Returns:
        Tuple of (date, cashflow_amount) or None for zero-cashflow transactions

    Cashflow sign convention (investor-centric):
        BUY: negative (cash outflow)
        SELL: positive (cash inflow)
        TRANSFER: use total_amount as-is (negative for sender, positive for receiver)
        STOCK_CONVERSION: None (zero cashflow)
    """
    if transaction.transaction_type == 'BUY':
        return (transaction.date, -transaction.total_amount)
    elif transaction.transaction_type == 'SELL':
        return (transaction.date, +transaction.total_amount)
    elif transaction.transaction_type == 'TRANSFER':
        return (transaction.date, transaction.total_amount)
    elif transaction.transaction_type == 'STOCK_CONVERSION':
        return None  # Zero cashflow
    else:
        logger.warning(f"Unknown transaction type: {transaction.transaction_type}")
        return None


def build_cashflows(transactions: List) -> Tuple[List[datetime], List[float]]:
    """Build cashflow series from transactions.

    Note: With the synthetic SELL transaction pattern, current_value is baked into
    the transactions list and no longer needs to be passed separately.

    Args:
        transactions: List of StockTransaction objects (may include synthetic SELL)

    Returns:
        Tuple of (dates_list, values_list) suitable for financial_metrics.calculate_mwrr()
    """
    # Build date-indexed cashflows (net by date)
    # Note: Synthetic SELL transactions are already in the transactions list
    cashflow_buckets = defaultdict(float)

    for txn in transactions:
        cf_tuple = transaction_to_cashflow(txn)
        if cf_tuple is not None:
            date, amount = cf_tuple
            # Use date only (no time component) for grouping
            date_key = date.date() if isinstance(date, datetime) else date
            cashflow_buckets[date_key] += amount

    # Convert to sorted lists
    sorted_items = sorted(cashflow_buckets.items(), key=lambda x: x[0])
    dates = [datetime.combine(d, datetime.min.time()) for d, _ in sorted_items]
    values = [cf for _, cf in sorted_items]

    return dates, values


def calculate_mwrr_for_transactions(transactions: List) -> Optional[float]:
    """Calculate MWRR for a list of transactions.

    This is a convenience wrapper that combines build_cashflows() and
    financial_metrics.calculate_mwrr().

    Note: With the synthetic SELL transaction pattern, current value is already
    included in the transactions list as a synthetic SELL at eval_date.

    Args:
        transactions: List of StockTransaction objects (may include synthetic SELL)

    Returns:
        Annualized MWRR as decimal (e.g., 0.15 for 15%) or None if undefined
    """
    dates, values = build_cashflows(transactions)
    return financial_metrics.calculate_mwrr(dates, values)


def calculate_aggregated_mwrr(transaction_groups: Dict[str, List]) -> Dict[str, Optional[float]]:
    """Calculate MWRR for aggregated groups (tags, categories, etc.).

    This aggregates transactions across multiple stocks within a group,
    then calculates MWRR for each group.

    Note: With the synthetic SELL transaction pattern, current values are already
    included in the transaction lists as synthetic SELLs.

    Args:
        transaction_groups: Dict mapping group_key to list of transactions (may include synthetic SELLs)

    Returns:
        Dict mapping group_key to MWRR value
    """
    results = {}
    for group_key in transaction_groups:
        transactions = transaction_groups[group_key]
        mwrr = calculate_mwrr_for_transactions(transactions)
        results[group_key] = mwrr
    return results


def calculate_transactions_through_date(transactions: List, target_date: datetime,
                                       include_investment_threshold: bool = True) -> Dict:
    """Calculate comprehensive transaction results through a target date.

    This unified method handles all transaction types (BUY, SELL, STOCK_CONVERSION, TRANSFER)
    and returns conversion-adjusted numbers for use by all modes.

    Args:
        transactions: List of StockTransaction objects
        target_date: The date to calculate through
        include_investment_threshold: If True, only count BUY transactions > £500 as investments

    Returns:
        Dictionary with:
        - units_held: Net units held at target_date
        - total_invested: Total amount invested (GBP)
        - total_received: Total amount received (GBP)
        - gross_units_bought: Total units bought (adjusted for conversions)
        - gross_units_sold: Total units sold (before conversions)
        - gross_amount_paid: Total amount paid for all purchases
        - gross_amount_received: Total amount received from all sales
        - conversion_adjusted_units: Units after applying all conversions
        - conversion_adjusted_cost_basis: Cost basis after applying conversions
        - conversion_ratio: Cumulative conversion ratio
        - current_ticker: Final ticker after any STOCK_CONVERSION transactions (None if no conversions)
    """
    logger.debug(f"Calculating transactions through {target_date.strftime('%Y-%m-%d')}")

    # Initialize counters
    units_held = 0.0
    total_invested = 0.0
    total_received = 0.0
    gross_units_bought = 0.0  # This will be adjusted for conversions
    gross_units_sold = 0.0
    gross_amount_paid = 0.0
    gross_amount_received = 0.0

    # Track conversion ratios for cost basis adjustment
    conversion_ratio = 1.0
    original_cost_basis = 0.0

    # Track ticker changes from STOCK_CONVERSION
    current_ticker = None

    for txn in transactions:
        if txn.date <= target_date:
            logger.debug(f"  Processing {txn.transaction_type} on {txn.date.strftime('%Y-%m-%d')}: {txn.quantity} units @ £{txn.price_per_share:.2f}")

            if txn.transaction_type == 'BUY':
                # Update holdings
                units_held += txn.quantity

                # Track gross amounts (before conversion adjustments)
                gross_units_bought += txn.quantity
                gross_amount_paid += txn.total_amount

                # Track investments (with threshold if specified)
                if include_investment_threshold and txn.total_amount > 500:
                    total_invested += txn.total_amount
                    original_cost_basis += txn.total_amount
                    logger.debug(f"    BUY: Investment £{txn.total_amount:.2f} (above threshold)")
                elif not include_investment_threshold:
                    total_invested += txn.total_amount
                    original_cost_basis += txn.total_amount
                    logger.debug(f"    BUY: Investment £{txn.total_amount:.2f} (no threshold)")
                else:
                    logger.debug(f"    BUY: Dividend accumulation £{txn.total_amount:.2f} (below threshold)")

            elif txn.transaction_type == 'SELL':
                # Update holdings
                if txn.quantity < 0:
                    units_held += txn.quantity  # quantity is already negative
                else:
                    units_held -= txn.quantity

                # Track gross amounts
                gross_units_sold += abs(txn.quantity)
                gross_amount_received += txn.total_amount
                total_received += txn.total_amount

            elif txn.transaction_type == 'STOCK_CONVERSION':
                # Handle stock conversions and share grants
                # Track ticker changes
                if txn.get_new_ticker():
                    current_ticker = txn.get_new_ticker()
                    logger.debug(f"    TICKER CHANGE: -> {current_ticker}")

                if txn.new_quantity:
                    if txn.quantity > 0:
                        # Ratio-based conversion: convert existing shares
                        conversion_ratio *= txn.new_quantity / txn.quantity
                        units_held *= txn.new_quantity / txn.quantity
                        gross_units_bought *= txn.new_quantity / txn.quantity  # Adjust gross units for conversions
                        logger.debug(f"    CONVERSION: {txn.quantity} -> {txn.new_quantity} (ratio: {txn.new_quantity/txn.quantity:.2f})")
                        logger.debug(f"    Adjusted gross_units_bought to: {gross_units_bought}")
                    elif txn.quantity == 0:
                        # Share grant: add new shares without converting existing ones
                        units_held += txn.new_quantity
                        logger.debug(f"    SHARE GRANT: +{txn.new_quantity} new shares")

            elif txn.transaction_type == 'TRANSFER':
                # Bed-and-ISA transfer: adjusts invested (cost basis transfer between categories)
                units_held += txn.quantity
                total_invested += txn.total_amount  # Positive for receiving, negative for sending
                original_cost_basis += txn.total_amount  # Also adjust cost basis
                logger.debug(f"    TRANSFER: {txn.quantity} units, £{txn.total_amount:.2f} cost basis adjustment")

    # Calculate conversion-adjusted values
    conversion_adjusted_units = units_held
    conversion_adjusted_cost_basis = original_cost_basis  # Cost basis doesn't change with conversions

    logger.debug(f"  Final results through {target_date.strftime('%Y-%m-%d')}:")
    logger.debug(f"    Units held: {units_held}")
    logger.debug(f"    Total invested: £{total_invested:.2f}")
    logger.debug(f"    Total received: £{total_received:.2f}")
    logger.debug(f"    Gross units bought (conversion-adjusted): {gross_units_bought}")
    logger.debug(f"    Gross units sold: {gross_units_sold}")
    logger.debug(f"    Gross amount paid: £{gross_amount_paid:.2f}")
    logger.debug(f"    Gross amount received: £{gross_amount_received:.2f}")
    logger.debug(f"    Conversion ratio: {conversion_ratio:.2f}")
    logger.debug(f"    Conversion-adjusted cost basis: £{conversion_adjusted_cost_basis:.2f}")

    return {
        'units_held': units_held,
        'total_invested': total_invested,
        'total_received': total_received,
        'gross_units_bought': gross_units_bought,
        'gross_units_sold': gross_units_sold,
        'gross_amount_paid': gross_amount_paid,
        'gross_amount_received': gross_amount_received,
        'conversion_adjusted_units': conversion_adjusted_units,
        'conversion_adjusted_cost_basis': conversion_adjusted_cost_basis,
        'conversion_ratio': conversion_ratio,
        'current_ticker': current_ticker
    }


def calculate_doubling_metrics(transactions: List, current_price: Optional[float]) -> tuple:
    """Calculate progress-to-doubling ratio and count of completed profit-taking doublings.

    A profit-taking event is a SELL where:
      - The fraction sold is between 15% and 30% of holdings at the time of the sell
      - The sell price exceeds 1.9× the current base_price

    base_price starts at the first BUY price.  After each qualifying sell, base_price resets
    to that sell price so the next doubling is measured from the new watermark.
    STOCK_CONVERSION events adjust the running base_price proportionally (e.g. a 2:1 split
    halves the base price so it stays comparable with post-split market prices).

    Args:
        transactions: Full lifetime transaction history (chronological).
        current_price: Current price per share (GBP), or None if fully sold.

    Returns:
        Tuple of (progress_to_doubling: str, doubling_count: int) where
        progress_to_doubling is e.g. "1.7x" or "—" when base_price is unavailable.
    """
    running_base_price: Optional[float] = None
    current_units: float = 0.0
    doubling_count: int = 0

    for txn in sorted(transactions, key=lambda t: t.date):
        if txn.transaction_type == 'BUY':
            if running_base_price is None:
                running_base_price = txn.price_per_share
            current_units += txn.quantity

        elif txn.transaction_type == 'SELL':
            qty = abs(txn.quantity)
            if current_units > 0 and running_base_price is not None and running_base_price > 0:
                fraction = qty / current_units
                if 0.15 <= fraction <= 0.30 and txn.price_per_share > 1.9 * running_base_price:
                    doubling_count += 1
                    running_base_price = txn.price_per_share
            current_units -= qty

        elif txn.transaction_type == 'STOCK_CONVERSION':
            if txn.new_quantity is not None and txn.quantity > 0:
                ratio = txn.new_quantity / txn.quantity
                current_units *= ratio
                if running_base_price is not None:
                    running_base_price /= ratio  # price per share falls when share count rises

        elif txn.transaction_type == 'TRANSFER':
            current_units += txn.quantity

    # Format progress_to_doubling
    if running_base_price is None or running_base_price <= 0 or current_price is None:
        progress_to_doubling = "\u2014"  # em dash
    else:
        ratio = current_price / running_base_price
        progress_to_doubling = f"{ratio:.1f}x"

    return progress_to_doubling, doubling_count


def get_first_buy_price_split_adjusted(transactions: List) -> Optional[float]:
    """Return the first BUY transaction's price per share, adjusted for subsequent splits/conversions.

    The first-buy unit price is used as base_price for progress-to-doubling calculations.
    Any STOCK_CONVERSION events that occur *after* the first buy are applied so the returned
    price is directly comparable to the current (post-split) market price.

    Share grants (STOCK_CONVERSION with quantity == 0) are ignored because they add shares
    without changing the price ratio of existing holdings.

    Args:
        transactions: List of StockTransaction objects in chronological order.

    Returns:
        Split-adjusted base price per share, or None if no BUY transaction exists.
    """
    first_buy_price: Optional[float] = None
    cumulative_conversion_ratio: float = 1.0

    for txn in transactions:
        if txn.transaction_type == 'BUY' and first_buy_price is None:
            first_buy_price = txn.price_per_share
        elif (
            txn.transaction_type == 'STOCK_CONVERSION'
            and first_buy_price is not None
            and txn.new_quantity is not None
            and txn.quantity > 0
        ):
            cumulative_conversion_ratio *= txn.new_quantity / txn.quantity

    if first_buy_price is None or cumulative_conversion_ratio == 0:
        return None
    return first_buy_price / cumulative_conversion_ratio
