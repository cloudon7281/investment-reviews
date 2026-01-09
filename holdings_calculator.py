"""Holdings and valuation calculations.

This module handles calculating holdings, stock valuations, and positions at
various dates. It uses transaction data and market data to compute these values.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from logger import logger
import transaction_processor


def get_holdings_at_date(transactions: List, target_date: datetime) -> float:
    """Calculate the number of units held at a specific date.

    Args:
        transactions: List of StockTransaction objects
        target_date: The date to calculate holdings for

    Returns:
        Number of units held at the target date
    """
    logger.debug(f"    Calculating holdings at {target_date.strftime('%Y-%m-%d')}")

    # Use unified method to calculate transactions through target date
    # We don't need investment threshold for holdings calculation
    results = transaction_processor.calculate_transactions_through_date(
        transactions,
        target_date,
        include_investment_threshold=False
    )

    holdings = results['units_held']
    logger.debug(f"    Final holdings at {target_date.strftime('%Y-%m-%d')}: {holdings}")

    return holdings


def get_subsequent_stock_splits(transactions: List, target_date: datetime) -> float:
    """Calculate the aggregated ratio of stock splits that occurred after the target date.

    Args:
        transactions: List of StockTransaction objects
        target_date: The date to check splits after

    Returns:
        Aggregated split ratio (e.g., 6.0 for a 2x and 3x split)
    """
    split_ratio = 1.0

    for txn in transactions:
        if txn.date > target_date and txn.transaction_type == 'STOCK_CONVERSION':
            if txn.new_quantity and txn.quantity and txn.new_quantity > 0 and txn.quantity > 0:
                actual_split_ratio = txn.new_quantity / txn.quantity
                split_ratio *= actual_split_ratio
                logger.debug(f"    Found subsequent split on {txn.date.strftime('%Y-%m-%d')}: {actual_split_ratio}x (from {txn.quantity} -> {txn.new_quantity})")

    if split_ratio != 1.0:
        logger.debug(f"    Total subsequent split ratio: {split_ratio}x")

    return split_ratio


def get_stock_price_from_data(ticker: str, target_date: datetime, price_data: Dict) -> Optional[float]:
    """Get stock price at a specific date using pre-fetched price data.

    Args:
        ticker: Stock ticker symbol
        target_date: Date to get price for
        price_data: Pre-fetched price data dictionary

    Returns:
        GBP price at the target date, or None if not available
    """
    if ticker in price_data and not price_data[ticker].empty:
        price_df = price_data[ticker]

        # Try to find price on exact date first
        target_date_str = target_date.strftime('%Y-%m-%d')
        exact_date_data = price_df[price_df.index.strftime('%Y-%m-%d') == target_date_str]

        if not exact_date_data.empty:
            gbp_price = exact_date_data['Close'].iloc[0]
            if not pd.isna(gbp_price):
                logger.debug(f"    Using pre-fetched price for {ticker} on exact date {target_date_str}: {gbp_price}")
                return gbp_price

        # Search backwards up to 14 days to find most recent valid price
        for days_back in range(1, 15):
            check_date = target_date - timedelta(days=days_back)
            check_date_str = check_date.strftime('%Y-%m-%d')
            check_date_data = price_df[price_df.index.strftime('%Y-%m-%d') == check_date_str]

            if not check_date_data.empty:
                gbp_price = check_date_data['Close'].iloc[0]
                if not pd.isna(gbp_price):
                    logger.debug(f"    Using pre-fetched price for {ticker} {days_back} days before {target_date_str}: {gbp_price}")
                    return gbp_price

        logger.debug(f"    No valid price found for {ticker} within 14 days of {target_date_str}")
        return None
    else:
        logger.debug(f"    No price data available for {ticker}")
        return None


def calculate_stock_value(ticker: str, holdings: float, holdings_date: datetime,
                          target_date: datetime, transactions: List, price_data: Dict,
                          allow_forward_fill: bool = False) -> Tuple[Optional[float], Optional[float]]:
    """Calculate stock value at target date, accounting for stock splits.

    This is a simplified helper for cases where holdings are already known
    (e.g., full_history mode). It handles stock splits and price lookback.

    Args:
        ticker: Stock ticker symbol
        holdings: Number of units held at holdings_date
        holdings_date: Date when holdings were calculated
        target_date: Date to get price for (usually today for full_history)
        transactions: List of transactions for this stock (needed for split detection)
        price_data: Pre-fetched price data dictionary
        allow_forward_fill: If True, use forward lookback when backward fails (for value_over_time)

    Returns:
        Tuple of (stock value in GBP at target date, GBP price at target date)
    """
    if holdings <= 0:
        return None, None

    # Adjust holdings for subsequent stock splits (YF prices are split-adjusted)
    split_ratio = get_subsequent_stock_splits(transactions, holdings_date)
    if split_ratio != 1.0:
        holdings *= split_ratio
        logger.debug(f"    Adjusted holdings for subsequent splits: {split_ratio}x -> {holdings}")

    # Get price from pre-fetched data using backward search
    gbp_price = get_stock_price_from_data(ticker, target_date, price_data)

    # If no price found with backward lookback and forward fill allowed, try forward lookback
    if gbp_price is None and allow_forward_fill:
        gbp_price = get_earliest_available_price(ticker, target_date, price_data)

    if gbp_price is not None:
        logger.debug(f"    Using pre-fetched price for {ticker} at {target_date.strftime('%Y-%m-%d')}: GBP={gbp_price}")
        return holdings * gbp_price, gbp_price
    else:
        logger.debug(f"    No price data available for {ticker}")
        return None, None


def get_earliest_available_price(ticker: str, target_date: datetime, price_data: Dict) -> Optional[float]:
    """Get the earliest available price after the target date (forward lookback).

    Used when backward lookback fails, typically for stocks that were held before they started trading publicly.

    Args:
        ticker: Stock ticker symbol
        target_date: Date to start searching from
        price_data: Pre-fetched price data dictionary

    Returns:
        First available GBP price after target_date, or None if not found
    """
    if ticker not in price_data or price_data[ticker].empty:
        return None

    price_df = price_data[ticker]

    # Get all dates after target_date
    future_dates = price_df[price_df.index > target_date]

    if future_dates.empty:
        return None

    # Get the first (earliest) available price
    for idx, row in future_dates.iterrows():
        gbp_price = row['Close']
        if not pd.isna(gbp_price):
            days_forward = (idx.date() - target_date.date()).days
            logger.debug(f"    Using forward-fill price for {ticker} {days_forward} days after {target_date.strftime('%Y-%m-%d')}: {gbp_price}")
            return gbp_price

    return None


def get_stock_valuations_at_date(ticker: str, start_date: datetime, end_date: datetime,
                                  target_date: datetime, transactions: List, price_data: Dict,
                                  use_start_date_holdings: bool = False) -> Tuple[Optional[float], float, Optional[float]]:
    """Get stock value and holdings at a specific date using pre-fetched price data.

    Args:
        ticker: Stock ticker symbol
        start_date: Start of review period
        end_date: End of review period
        target_date: Date to get price for (usually eval_date)
        transactions: List of transactions for this stock
        price_data: Pre-fetched price data dictionary
        use_start_date_holdings: If True, use holdings at start_date (for sold stocks)

    Returns:
        Tuple of (stock value in GBP at the target date, holdings at the appropriate date, GBP price)
    """
    # Determine holdings date: start_date for sold stocks, end_date for new & retained stocks
    if use_start_date_holdings:
        holdings_date = start_date
        logger.debug(f"    Using start_date holdings for sold stock: {holdings_date}")
    else:
        holdings_date = end_date
        logger.debug(f"    Using end_date holdings for new/retained stock: {holdings_date}")

    holdings = get_holdings_at_date(transactions, holdings_date)

    if holdings <= 0:
        return None, 0.0, None

    # Adjust holdings for subsequent stock splits (YF prices are split-adjusted)
    split_ratio = get_subsequent_stock_splits(transactions, holdings_date)
    if split_ratio != 1.0:
        holdings *= split_ratio
        logger.debug(f"    Adjusted holdings for subsequent splits: {split_ratio}x -> {holdings}")

    # Get price from pre-fetched data using backward search
    gbp_price = get_stock_price_from_data(ticker, target_date, price_data)
    if gbp_price is not None:
        logger.debug(f"    Using pre-fetched price for {ticker} at {target_date.strftime('%Y-%m-%d')}: GBP={gbp_price}")
        return holdings * gbp_price, holdings, gbp_price
    else:
        logger.debug(f"    No price data available for {ticker}")
        return None, holdings, None


def calculate_start_value_from_transactions(transactions: List, start_date: datetime,
                                            end_date: datetime, eval_date: datetime,
                                            ticker: str, transaction_type: str) -> Tuple[Optional[float], int]:
    """Calculate start value by summing transaction amounts in the date range.

    Args:
        transactions: List of transactions for this stock
        start_date: Start of review period
        end_date: End of review period
        eval_date: Evaluation date
        ticker: Stock ticker
        transaction_type: 'BUY' for new stocks, 'SELL' for sold stocks

    Returns:
        Tuple of (start_value, period_days)
    """
    logger.debug(f"    Calculating {transaction_type} stock performance for {ticker}")
    logger.debug(f"      Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    logger.debug(f"      Evaluation date: {eval_date.strftime('%Y-%m-%d')}")

    # Find first transaction in period
    first_txn = None
    for txn in transactions:
        if start_date <= txn.date <= end_date:
            first_txn = txn
            logger.debug(f"      First transaction in period: {txn.date.strftime('%Y-%m-%d')} - {txn.transaction_type}")
            break

    if not first_txn:
        logger.debug(f"      No transactions found in period for {ticker}")
        return None, 0

    # Calculate total amount from transactions of the specified type during [A,B]
    total_amount = 0.0
    for txn in transactions:
        if start_date <= txn.date <= end_date and txn.transaction_type == transaction_type:
            total_amount += txn.total_amount or 0.0
            logger.debug(f"      {transaction_type} transaction on {txn.date.strftime('%Y-%m-%d')}: £{txn.total_amount or 0.0}")

    period_days = (eval_date - first_txn.date).days
    logger.debug(f"      Total {transaction_type.lower()} amount: £{total_amount}")
    logger.debug(f"      Period days: {period_days}")
    return total_amount, period_days


def calculate_retained_stock_performance_unified(transactions: List, start_date: datetime,
                                                 end_date: datetime, eval_date: datetime,
                                                 ticker: str, price_data: Dict = None) -> Tuple[Optional[float], int]:
    """Calculate performance for retained stocks using the unified approach.

    Args:
        transactions: List of transactions for this stock
        start_date: Start of review period
        end_date: End of review period
        eval_date: Evaluation date
        ticker: Stock ticker
        price_data: Pre-fetched price data

    Returns:
        Tuple of (start_value, period_days)
    """
    logger.debug(f"    Calculating RETAINED stock performance for {ticker}")
    logger.debug(f"      End date: {end_date.strftime('%Y-%m-%d')}")
    logger.debug(f"      Evaluation date: {eval_date.strftime('%Y-%m-%d')}")

    # Get value and holdings at end_date (start of performance period)
    start_value, holdings_at_end, _ = get_stock_valuations_at_date(
        ticker, start_date, end_date, end_date, transactions, price_data, use_start_date_holdings=False
    )

    if start_value is None or holdings_at_end <= 0:
        logger.debug(f"      No valid start value or holdings for {ticker}")
        return None, 0

    # Calculate period in days
    period_days = (eval_date - end_date).days
    logger.debug(f"      Start value: £{start_value:.2f}, Holdings: {holdings_at_end}, Period: {period_days} days")

    return start_value, period_days
