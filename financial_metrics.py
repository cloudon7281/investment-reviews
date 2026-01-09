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
        eval_date: Optional evaluation date. If provided, calculates 90-day period
                  up to this date. If None, uses the last 90 days of available data.

    Returns:
        Dictionary mapping ticker to {'recent_high': float, 'annualized_volatility': float}

    Note:
        - Uses 90-day window for calculations
        - Volatility is calculated using log returns and annualized (252 trading days)
    """
    results = {}
    for ticker, df in price_data.items():
        try:
            # Determine the 90-day period to analyze
            if eval_date is not None:
                # Calculate 90-day period up to eval_date
                start_date = eval_date - timedelta(days=90)

                # Filter data to the 90-day period up to eval_date
                mask = (df.index.date >= start_date.date()) & (df.index.date <= eval_date.date())
                last_90_days = df[mask]

                if last_90_days.empty:
                    logger.warning(f"No price data available for {ticker} in 90-day period up to {eval_date.strftime('%Y-%m-%d')}")
                    results[ticker] = {'recent_high': None, 'annualized_volatility': None}
                    continue

                logger.debug(f"Calculated highs and volatility for {ticker} using 90-day period up to {eval_date.strftime('%Y-%m-%d')}")
            else:
                # Use last 90 days of available data
                last_90_days = df.tail(90)
                logger.debug(f"Calculated highs and volatility for {ticker} using last 90 days of available data")

            # Common calculations for both modes
            recent_high = last_90_days['Close'].max()

            # Calculate volatility using log returns
            last_90_days_copy = last_90_days.copy()
            last_90_days_copy['log_return'] = np.log(last_90_days_copy['Close'] / last_90_days_copy['Close'].shift(1))
            daily_vol = last_90_days_copy['log_return'].std()
            annualized_volatility = daily_vol * np.sqrt(252)  # Annualize

            results[ticker] = {
                'recent_high': recent_high,
                'annualized_volatility': annualized_volatility
            }
            logger.debug(f"Calculated highs and volatility for {ticker}: {results[ticker]}")
        except Exception as e:
            logger.error(f"Error calculating highs and volatility for {ticker}: {str(e)}")
            results[ticker] = {
                'recent_high': None,
                'annualized_volatility': None
            }
    return results
