"""Pure financial metric calculations.

This module contains generic financial calculations that operate on
standard data structures (dates, values, price series) with no knowledge
of StockTransactions or portfolio-specific structures.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import pyxirr
from logger import logger

# The recent-high window, in calendar days ending at the evaluation date.
RECENT_HIGH_WINDOW_DAYS = 90

# Observations averaged for the smoothed high (10 trading days, i.e. two market weeks).
SMOOTHING_WINDOW_OBSERVATIONS = 10

# Quantile of the closing prices used for the percentile high.
HIGH_PERCENTILE = 0.9


def _finite(value) -> Optional[float]:
    """Return value as a float, or None if it is missing or not finite."""
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def calculate_mwrr(dates: List[datetime], values: List[float]) -> Optional[float]:
    """Calculate Money-Weighted Rate of Return (MWRR) using XIRR.

    This is a generic MWRR calculation that works on any cashflow series.

    Args:
        dates: List of dates for each cashflow
        values: List of cashflow values (negative for outflows, positive for inflows)

    Returns:
        Annualized MWRR as decimal (e.g., 0.15 for 15%) or None if undefined

    Example:
        # Investment of $100 on Jan 1, value of $120 on Dec 31
        dates = [datetime(2024, 1, 1), datetime(2024, 12, 31)]
        values = [-100.0, 120.0]
        mwrr = calculate_mwrr(dates, values)  # Returns ~0.20 (20% return)
    """
    # Validate: need at least one positive and one negative cashflow
    if not any(v > 0 for v in values) or not any(v < 0 for v in values):
        logger.debug("MWRR undefined: need both positive and negative cashflows")
        return None

    try:
        # pyxirr.xirr can take dates and values as separate lists
        mwrr = pyxirr.xirr(dates, values)
        return mwrr
    except Exception as e:
        logger.warning(f"XIRR calculation failed: {e}")
        return None


def calculate_highs_and_volatility(price_data: Dict[str, pd.DataFrame],
                                   eval_date: Optional[datetime] = None) -> Dict[str, Dict[str, float]]:
    """Calculate recent highs and volatility for each stock.

    Args:
        price_data: Dictionary mapping ticker to DataFrame with 'Close' column
        eval_date: Optional evaluation date ending the window. If None, the window
                  ends at the last date present in each ticker's data.

    Returns:
        Dictionary mapping ticker to {'recent_high', 'smoothed_high',
        'percentile_high', 'annualized_volatility'}

    Note:
        - The window is RECENT_HIGH_WINDOW_DAYS calendar days ending at the evaluation
          date.  It is a calendar window, not a row count: the fetched series carries a
          buffer before the requested start, so counting rows would silently reach
          further back than 90 days (investment-reviews#26).
        - 'recent_high' is the highest close in the window, so a single-day spike sets it.
        - 'smoothed_high' is the highest SMOOTHING_WINDOW_OBSERVATIONS-day rolling mean
          close, and 'percentile_high' the HIGH_PERCENTILE quantile of the closes.  Both
          discount short spikes, so a stop-loss read against them is less twitchy.
        - Volatility is calculated using log returns and annualized (252 trading days)
    """
    empty_result = {
        'recent_high': None,
        'smoothed_high': None,
        'percentile_high': None,
        'annualized_volatility': None
    }

    results = {}
    for ticker, df in price_data.items():
        try:
            if df.empty:
                logger.warning(f"No price data available for {ticker}")
                results[ticker] = dict(empty_result)
                continue

            # The window always ends at the evaluation date; with no evaluation date the
            # data itself ends there, so its last row is the anchor.
            window_end = eval_date if eval_date is not None else df.index[-1].to_pydatetime()
            window_start = window_end - timedelta(days=RECENT_HIGH_WINDOW_DAYS)

            mask = (df.index.date >= window_start.date()) & (df.index.date <= window_end.date())
            window = df[mask]

            if window.empty:
                logger.warning(f"No price data available for {ticker} in {RECENT_HIGH_WINDOW_DAYS}-day period up to {window_end.strftime('%Y-%m-%d')}")
                results[ticker] = dict(empty_result)
                continue

            closes = window['Close']
            observed_days = (window.index[-1].date() - window.index[0].date()).days + 1
            if observed_days < RECENT_HIGH_WINDOW_DAYS:
                logger.warning(f"{ticker}: only {observed_days} days of the {RECENT_HIGH_WINDOW_DAYS}-day window are covered by the fetched data; highs are understated")

            recent_high = _finite(closes.max())
            smoothed_high = _finite(closes.rolling(SMOOTHING_WINDOW_OBSERVATIONS).mean().max())
            percentile_high = _finite(closes.quantile(HIGH_PERCENTILE))

            # Calculate volatility using log returns
            log_returns = np.log(closes / closes.shift(1))
            daily_vol = log_returns.std()
            annualized_volatility = _finite(daily_vol * np.sqrt(252))  # Annualize

            results[ticker] = {
                'recent_high': recent_high,
                'smoothed_high': smoothed_high,
                'percentile_high': percentile_high,
                'annualized_volatility': annualized_volatility
            }
            logger.debug(f"Calculated highs and volatility for {ticker} over {RECENT_HIGH_WINDOW_DAYS} days to {window_end.strftime('%Y-%m-%d')}: {results[ticker]}")
        except Exception as e:
            logger.error(f"Error calculating highs and volatility for {ticker}: {str(e)}")
            results[ticker] = dict(empty_result)
    return results


def price_vs_highs(current_price: Optional[float],
                   highs: Optional[Dict[str, float]]) -> Dict[str, Optional[float]]:
    """Express a current price as a fraction of each of the recent highs.

    Args:
        current_price: Current price in GBP, or None if unavailable
        highs: One ticker's entry from calculate_highs_and_volatility, or None

    Returns:
        Dictionary carrying each high level and the corresponding fraction of it, with
        None wherever either the high or the price is missing.
    """
    highs = highs or {}
    result = {}
    for high_key, pct_key in (('recent_high', 'current_price_pct_of_high'),
                              ('smoothed_high', 'current_price_pct_of_smoothed_high'),
                              ('percentile_high', 'current_price_pct_of_percentile_high')):
        high = highs.get(high_key)
        result[high_key] = high
        result[pct_key] = current_price / high if high and high > 0 and current_price is not None else None
    return result
