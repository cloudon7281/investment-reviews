"""Value over time calculation.

This module calculates portfolio valuations over a specified time period,
broken down by category (ISA, Taxable, Pension) and by tag.
"""

from datetime import datetime, timedelta
from typing import Dict
import pandas as pd
from logger import logger
import holdings_calculator


def calculate_value_over_time(n_days: int, stock_data: Dict,
                              market_data_fetcher) -> pd.DataFrame:
    """Calculate portfolio valuations over time by tag and category.

    Args:
        n_days: Number of days to look back (generates n+1 rows including today)
        stock_data: Dict mapping (ticker, category) tuples to stock data dicts
                   (as built by full_history_processor Phase 1). Each dict contains:
                   'current_ticker', 'account_type', 'tag', 'transactions'
        market_data_fetcher: MarketDataFetcher instance for accessing price cache

    Returns:
        DataFrame with columns: date, whole_portfolio, isa, taxable, pension, and one column per tag
        All monetary values are floats in GBP
    """
    logger.info(f"Calculating value over time for {n_days} days")

    # Phase 1: Data Collection
    # Note: Price data should already be cached from process_full_history() call
    # which fetches the extended date range when value_over_time is requested
    today = datetime.now().date()
    start_date = today - timedelta(days=n_days)

    # Generate list of dates (oldest to newest)
    date_range = [start_date + timedelta(days=i) for i in range(n_days + 1)]
    logger.info(f"Date range: {date_range[0]} to {date_range[-1]} ({len(date_range)} dates)")

    # Extract data from pre-built stock_data dict
    ticker_category_pairs = list(stock_data.keys())
    ticker_to_current = {key: data['current_ticker'] for key, data in stock_data.items()}
    ticker_to_category = {key: data['account_type'].lower() for key, data in stock_data.items()}
    ticker_to_tag = {key: data['tag'] for key, data in stock_data.items() if data['tag']}
    all_tags = {data['tag'] for data in stock_data.values() if data['tag']}

    logger.info(f"Processing {len(ticker_category_pairs)} ticker-category pairs")
    logger.info(f"Found {len(all_tags)} unique tags: {sorted(all_tags)}")

    # Price data should already be cached from process_full_history()
    # Just extract it from the cache for use
    unique_current_tickers = list(set(ticker_to_current.values()))
    logger.info(f"Using cached price data for {len(unique_current_tickers)} unique tickers")

    # Verify cache has data, if not fetch it (fallback for edge cases)
    uncached_tickers = [t for t in unique_current_tickers if t not in market_data_fetcher.price_cache or market_data_fetcher.price_cache[t].empty]
    if uncached_tickers:
        logger.warning(f"Cache missing data for {len(uncached_tickers)} tickers, fetching now...")
        # Specify exact evaluation range - _batch_get_stock_prices handles all buffering
        price_start_date = datetime.combine(start_date, datetime.min.time())
        price_end_date = datetime.combine(today, datetime.min.time())
        market_data_fetcher.batch_get_stock_prices(uncached_tickers, price_start_date, price_end_date)

    # Use cached price data
    price_data = {ticker: market_data_fetcher.price_cache[ticker] for ticker in unique_current_tickers if ticker in market_data_fetcher.price_cache}
    logger.info(f"Using price data for {len(price_data)} tickers from cache")

    # Phase 2: Daily Valuation Loop
    results = []

    for current_date in date_range:
        logger.debug(f"Processing date: {current_date}")
        current_datetime = datetime.combine(current_date, datetime.min.time())

        # Initialize accumulators for this date
        valuations = {
            'whole_portfolio': 0.0,
            'isa': 0.0,
            'taxable': 0.0,
            'pension': 0.0
        }

        # Initialize tag accumulators
        for tag in all_tags:
            valuations[tag] = 0.0

        # Calculate value for each stock
        for ticker_key in ticker_category_pairs:
            stock_info = stock_data[ticker_key]
            transactions = stock_info['transactions']
            current_ticker = ticker_to_current[ticker_key]
            stock_category = ticker_to_category[ticker_key]
            stock_tag = ticker_to_tag.get(ticker_key)

            # Get holdings at this date
            holdings = holdings_calculator.get_holdings_at_date(transactions, current_datetime)

            if holdings <= 0:
                continue

            # Calculate value using unified helper (handles splits and price lookback)
            value, gbp_price = holdings_calculator.calculate_stock_value(
                current_ticker,
                holdings,
                current_datetime,
                current_datetime,
                transactions,
                price_data,
                allow_forward_fill=True  # Use forward fill for historical data gaps
            )

            if value is None or gbp_price is None:
                logger.debug(f"  {ticker_key[0]}: No price data available for {current_date}")
                continue

            logger.debug(f"  {ticker_key[0]} ({stock_category}): {holdings:.2f} shares @ £{gbp_price:.2f} = £{value:.2f}")

            # Accumulate values
            valuations['whole_portfolio'] += value
            valuations[stock_category] += value

            if stock_tag:
                valuations[stock_tag] += value

        # Build result row
        row = {
            'date': current_date,
            'whole_portfolio': valuations['whole_portfolio'],
            'isa': valuations['isa'],
            'taxable': valuations['taxable'],
            'pension': valuations['pension']
        }

        # Add tag columns (alphabetically sorted)
        for tag in sorted(all_tags):
            row[tag] = valuations[tag]

        results.append(row)
        logger.debug(f"  Total for {current_date}: £{valuations['whole_portfolio']:,.2f}")

    # Phase 3: Build DataFrame
    df = pd.DataFrame(results)

    # Ensure column order: date, whole_portfolio, isa, taxable, pension, then tags alphabetically
    ordered_columns = ['date', 'whole_portfolio', 'isa', 'taxable', 'pension'] + sorted(all_tags)
    df = df[ordered_columns]

    logger.info(f"Value over time calculation complete: {len(df)} rows, {len(df.columns)} columns")

    return df
