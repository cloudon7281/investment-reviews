"""Annual review mode processing.

This module handles annual portfolio review analysis, which calculates
performance metrics from a start date to the current date for the entire
portfolio, grouped by whole portfolio, category, and tag.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from logger import logger
from portfolio_review import PortfolioReview, StockTransaction
from collections import defaultdict
import transaction_processor
import holdings_calculator
import financial_metrics


def process_annual_review(portfolio_review: PortfolioReview, start_date: datetime,
                          market_data_fetcher, price_over_time: bool = False) -> Dict[str, pd.DataFrame]:
    """Process annual review mode.

    Calculates performance metrics from start_date to today for the entire
    portfolio, aggregated by whole portfolio, category, and tag.

    Args:
        portfolio_review: PortfolioReview instance containing full transaction history
        start_date: Start date for the annual review period
        market_data_fetcher: MarketDataFetcher instance for price cache access
        price_over_time: If True, generate price-over-time CSV data

    Returns:
        Dictionary with:
        - 'whole_portfolio': DataFrame with single row for overall portfolio totals
        - 'per_category': DataFrame with one row per category (ISA/Taxable/Pension)
        - 'per_tag': DataFrame with one row per tag
        - 'individual_stocks': DataFrame with per-stock detail (optional, for debugging)
        - 'price_over_time': DataFrame with daily prices per stock (None if not requested)
    """
    logger.info(f"Processing annual review mode from {start_date.strftime('%Y-%m-%d')}")

    eval_date = datetime.now()
    n_days = (eval_date.date() - start_date.date()).days

    # Phase 1: Analyze transactions and collect stocks for the review
    stock_data = {}
    stocks_needing_prices = []
    ticker_to_current_ticker = {}

    ticker_category_pairs = portfolio_review.get_all_tickers()
    logger.info(f"Processing {len(ticker_category_pairs)} stock/category combinations")

    for ticker, category in ticker_category_pairs:
        logger.debug(f"Phase 1: Analyzing {ticker} in {category}")

        stock_name = portfolio_review.get_stock_name(ticker, category)
        account_type = category.upper() if category == 'isa' else category.capitalize()
        tag = portfolio_review.get_stock_tag(ticker, category)
        transactions = portfolio_review.get_transaction_history(ticker, category)

        if not transactions:
            logger.warning(f"No transactions found for {ticker}")
            continue

        # Calculate holdings at start date
        holdings_at_start = holdings_calculator.get_holdings_at_date(transactions, start_date)

        # Calculate holdings at eval_date (today)
        results_through_today = transaction_processor.calculate_transactions_through_date(
            transactions, eval_date, include_investment_threshold=False
        )
        holdings_at_end = results_through_today['units_held']
        current_ticker = results_through_today['current_ticker'] if results_through_today['current_ticker'] else ticker

        ticker_to_current_ticker[ticker] = current_ticker

        # Skip stocks that had no holdings at start AND no holdings now AND no activity
        # We include stocks that:
        # 1. Had holdings at start (retained or sold)
        # 2. Have holdings now (retained or new)
        # 3. Had any transactions since start (activity during period)
        transactions_since_start = [t for t in transactions if t.date > start_date]

        if holdings_at_start <= 1e-6 and holdings_at_end <= 1e-6 and len(transactions_since_start) == 0:
            logger.debug(f"  Skipping {ticker}: no holdings at start or end, no activity")
            continue

        # Calculate bought_since and sold_since from transactions after start_date
        bought_since = 0.0
        sold_since = 0.0
        for txn in transactions_since_start:
            if txn.transaction_type == 'BUY':
                bought_since += txn.total_amount or 0.0
            elif txn.transaction_type == 'SELL':
                sold_since += txn.total_amount or 0.0
            elif txn.transaction_type == 'TRANSFER':
                # Transfers: positive for receiving (like buying), negative for sending (like selling)
                if txn.total_amount > 0:
                    bought_since += txn.total_amount
                else:
                    sold_since += abs(txn.total_amount)

        stock_key = (ticker, category)
        stock_data[stock_key] = {
            'ticker': ticker,
            'current_ticker': current_ticker,
            'stock_name': stock_name,
            'account_type': account_type,
            'tag': tag,
            'holdings_at_start': holdings_at_start,
            'holdings_at_end': holdings_at_end,
            'bought_since': bought_since,
            'sold_since': sold_since,
            'transactions': transactions,
            'transactions_since_start': transactions_since_start
        }

        # Need price for start date valuation (if holdings at start) and current valuation (if holdings now)
        # When price_over_time is requested, also fetch prices for stocks with activity during period
        needs_price = (holdings_at_start > 1e-6 or holdings_at_end > 1e-6 or
                       (price_over_time and len(transactions_since_start) > 0))
        if needs_price:
            stocks_needing_prices.append(current_ticker)
            logger.debug(f"  {ticker}: holdings_at_start={holdings_at_start:.2f}, holdings_at_end={holdings_at_end:.2f}")

    # Phase 2: Fetch prices for the entire period
    logger.info(f"Phase 2: Fetching prices for {len(set(stocks_needing_prices))} unique tickers")
    current_prices = {}
    highs_and_vol = {}

    if stocks_needing_prices:
        unique_tickers = list(set(stocks_needing_prices))
        # Fetch from start_date to today
        price_data = market_data_fetcher.batch_get_stock_prices(
            unique_tickers, start_date, eval_date, use_live_rates=True
        )
        current_prices = price_data
        highs_and_vol = financial_metrics.calculate_highs_and_volatility(price_data)

    # Phase 3: Calculate metrics for each stock
    logger.info("Phase 3: Calculating metrics for each stock")
    results = []

    portfolio_transactions = []
    category_transactions = defaultdict(list)
    tag_transactions = defaultdict(list)

    # Accumulators for summary
    portfolio_start_value = 0.0
    portfolio_bought_since = 0.0
    portfolio_sold_since = 0.0
    portfolio_current_value = 0.0

    category_summaries = defaultdict(lambda: {
        'start_value': 0.0, 'bought_since': 0.0, 'sold_since': 0.0, 'current_value': 0.0
    })
    tag_summaries = defaultdict(lambda: {
        'start_value': 0.0, 'bought_since': 0.0, 'sold_since': 0.0, 'current_value': 0.0
    })

    for stock_key, data in stock_data.items():
        ticker = data['ticker']
        current_ticker = data['current_ticker']
        account_type = data['account_type']
        tag_key = data['tag'] if data['tag'] else 'No Tag'

        # Calculate start_value: holdings_at_start * price_at_start
        start_value = 0.0
        if data['holdings_at_start'] > 1e-6:
            # Need to adjust for stock splits between start_date and now
            # because YF prices are split-adjusted
            split_ratio = holdings_calculator.get_subsequent_stock_splits(
                data['transactions'], start_date
            )
            adjusted_holdings_at_start = data['holdings_at_start'] * split_ratio

            price_at_start = holdings_calculator.get_stock_price_from_data(
                current_ticker, start_date, current_prices
            )
            if price_at_start is not None:
                start_value = adjusted_holdings_at_start * price_at_start
                logger.debug(f"  {ticker}: start_value = {adjusted_holdings_at_start:.2f} * £{price_at_start:.2f} = £{start_value:.2f}")

        # Calculate current_value: holdings_at_end * price_at_eval
        current_value = 0.0
        current_price = None
        if data['holdings_at_end'] > 1e-6:
            value_result, price_result = holdings_calculator.calculate_stock_value(
                current_ticker,
                data['holdings_at_end'],
                eval_date,  # holdings_date
                eval_date,  # target_date
                data['transactions'],
                current_prices
            )
            if value_result is not None:
                current_value = value_result
                current_price = price_result
                logger.debug(f"  {ticker}: current_value = £{current_value:.2f}")

        bought_since = data['bought_since']
        sold_since = data['sold_since']

        # PnL = (current_value + sold_since) - (start_value + bought_since)
        pnl = (current_value + sold_since) - (start_value + bought_since)
        logger.debug(f"  {ticker}: PnL = (£{current_value:.2f} + £{sold_since:.2f}) - (£{start_value:.2f} + £{bought_since:.2f}) = £{pnl:.2f}")

        # Create synthetic transactions for MWRR
        mwrr_transactions = create_annual_mwrr_transactions(
            start_date, start_value,
            data['transactions_since_start'],
            current_value, eval_date
        )

        # Calculate MWRR for this stock
        mwrr = transaction_processor.calculate_mwrr_for_transactions(mwrr_transactions)

        # Collect for aggregated calculations
        portfolio_transactions.extend(mwrr_transactions)
        category_transactions[account_type].extend(mwrr_transactions)
        tag_transactions[tag_key].extend(mwrr_transactions)

        # Accumulate for summaries
        portfolio_start_value += start_value
        portfolio_bought_since += bought_since
        portfolio_sold_since += sold_since
        portfolio_current_value += current_value

        category_summaries[account_type]['start_value'] += start_value
        category_summaries[account_type]['bought_since'] += bought_since
        category_summaries[account_type]['sold_since'] += sold_since
        category_summaries[account_type]['current_value'] += current_value

        tag_summaries[tag_key]['start_value'] += start_value
        tag_summaries[tag_key]['bought_since'] += bought_since
        tag_summaries[tag_key]['sold_since'] += sold_since
        tag_summaries[tag_key]['current_value'] += current_value

        # Get highs and volatility
        recent_high = highs_and_vol.get(current_ticker, {}).get('recent_high')
        volatility = highs_and_vol.get(current_ticker, {}).get('annualized_volatility')
        current_price_pct_of_high = None
        if recent_high and recent_high > 0 and current_price:
            current_price_pct_of_high = current_price / recent_high

        # Build result row
        result = {
            'ticker': ticker,
            'stock_name': data['stock_name'],
            'account_type': account_type,
            'tag': data['tag'],
            'start_value': start_value,
            'bought_since': bought_since,
            'sold_since': sold_since,
            'current_value': current_value,
            'pnl': pnl,
            'mwrr': mwrr,
            'holdings_at_start': data['holdings_at_start'],
            'holdings_at_end': data['holdings_at_end'],
            'current_price': current_price,
            'recent_high': recent_high,
            'current_price_pct_of_high': current_price_pct_of_high,
            'volatility': volatility
        }
        results.append(result)

        logger.info(f"  {ticker} in {account_type}: Start £{start_value:.0f}, "
                   f"Bought £{bought_since:.0f}, Sold £{sold_since:.0f}, "
                   f"Current £{current_value:.0f}, PnL £{pnl:.0f}")

    # Calculate aggregated MWRRs
    logger.info("Calculating aggregated MWRRs")
    portfolio_mwrr = transaction_processor.calculate_mwrr_for_transactions(portfolio_transactions)
    category_mwrrs = transaction_processor.calculate_aggregated_mwrr(category_transactions)
    tag_mwrrs = transaction_processor.calculate_aggregated_mwrr(tag_transactions)

    # Build DataFrames
    individual_stocks_df = pd.DataFrame(results) if results else pd.DataFrame()

    # Create summary DataFrames
    whole_portfolio_df, per_category_df, per_tag_df = create_annual_summaries(
        portfolio_start_value, portfolio_bought_since, portfolio_sold_since,
        portfolio_current_value, portfolio_mwrr,
        category_summaries, category_mwrrs,
        tag_summaries, tag_mwrrs
    )

    logger.info(f"Annual review processing completed: {len(individual_stocks_df)} stocks")

    # Calculate price-over-time if requested
    price_over_time_df = None
    if price_over_time:
        logger.info(f"Calculating price-over-time for {n_days} days")
        price_over_time_df = calculate_price_over_time(
            start_date, stock_data, current_prices
        )

    return {
        'whole_portfolio': whole_portfolio_df,
        'per_category': per_category_df,
        'per_tag': per_tag_df,
        'individual_stocks': individual_stocks_df,
        'price_over_time': price_over_time_df
    }


def create_annual_mwrr_transactions(start_date: datetime, start_value: float,
                                    transactions_since_start: List,
                                    current_value: float, eval_date: datetime) -> List:
    """Create synthetic transactions for annual review MWRR calculation.

    The MWRR models the scenario: "If I bought the portfolio at start_date for
    its value then, made all my actual trades since, and sold today for current
    value, what's my IRR?"

    Args:
        start_date: Start date of the review period
        start_value: Portfolio value at start_date
        transactions_since_start: Actual transactions that occurred after start_date
        current_value: Portfolio value at eval_date
        eval_date: Evaluation date (today)

    Returns:
        List of StockTransaction objects for MWRR calculation
    """
    mwrr_transactions = []

    # Synthetic BUY at start_date with start_value (only if we had holdings)
    if start_value > 0:
        synthetic_buy = StockTransaction(
            date=start_date,
            transaction_type='BUY',
            quantity=0,  # Not used for MWRR
            price_per_share=0.0,
            total_amount=start_value
        )
        mwrr_transactions.append(synthetic_buy)

    # Include all actual transactions since start_date
    mwrr_transactions.extend(transactions_since_start)

    # Synthetic SELL at eval_date with current_value (only if we have holdings now)
    if current_value > 0:
        synthetic_sell = StockTransaction(
            date=eval_date,
            transaction_type='SELL',
            quantity=0,
            price_per_share=0.0,
            total_amount=current_value
        )
        mwrr_transactions.append(synthetic_sell)

    return mwrr_transactions


def create_annual_summaries(portfolio_start_value: float, portfolio_bought_since: float,
                            portfolio_sold_since: float, portfolio_current_value: float,
                            portfolio_mwrr: Optional[float],
                            category_summaries: Dict, category_mwrrs: Dict,
                            tag_summaries: Dict, tag_mwrrs: Dict) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create summary DataFrames for annual review.

    Args:
        portfolio_*: Portfolio-level aggregated values
        portfolio_mwrr: Portfolio MWRR
        category_summaries: Dict of category -> {start_value, bought_since, sold_since, current_value}
        category_mwrrs: Dict of category -> MWRR
        tag_summaries: Dict of tag -> {start_value, bought_since, sold_since, current_value}
        tag_mwrrs: Dict of tag -> MWRR

    Returns:
        Tuple of (whole_portfolio_df, per_category_df, per_tag_df)
    """
    # Whole portfolio
    portfolio_pnl = (portfolio_current_value + portfolio_sold_since) - (portfolio_start_value + portfolio_bought_since)
    whole_portfolio_df = pd.DataFrame([{
        'group': 'Whole Portfolio',
        'start_value': portfolio_start_value,
        'bought_since': portfolio_bought_since,
        'sold_since': portfolio_sold_since,
        'current_value': portfolio_current_value,
        'pnl': portfolio_pnl,
        'mwrr': portfolio_mwrr
    }])

    # Per-category
    category_rows = []
    for category in ['ISA', 'Taxable', 'Pension']:
        if category in category_summaries:
            data = category_summaries[category]
            pnl = (data['current_value'] + data['sold_since']) - (data['start_value'] + data['bought_since'])
            category_rows.append({
                'group': category,
                'start_value': data['start_value'],
                'bought_since': data['bought_since'],
                'sold_since': data['sold_since'],
                'current_value': data['current_value'],
                'pnl': pnl,
                'mwrr': category_mwrrs.get(category)
            })
    per_category_df = pd.DataFrame(category_rows) if category_rows else pd.DataFrame()

    # Per-tag
    tag_rows = []
    for tag_key, data in sorted(tag_summaries.items()):
        pnl = (data['current_value'] + data['sold_since']) - (data['start_value'] + data['bought_since'])
        tag_rows.append({
            'group': tag_key,
            'start_value': data['start_value'],
            'bought_since': data['bought_since'],
            'sold_since': data['sold_since'],
            'current_value': data['current_value'],
            'pnl': pnl,
            'mwrr': tag_mwrrs.get(tag_key)
        })
    per_tag_df = pd.DataFrame(tag_rows) if tag_rows else pd.DataFrame()

    return whole_portfolio_df, per_category_df, per_tag_df


def _format_transactions_for_date(transactions_by_date: Dict, target_date) -> str:
    """Format transactions for a given date into a concise string.

    Args:
        transactions_by_date: Dict mapping date -> list of transactions
        target_date: The date to look up

    Returns:
        Formatted string like "BOUGHT 100", "SOLD 50", "SPLIT x2", or "" if no transactions
    """
    if target_date not in transactions_by_date:
        return ""

    txns = transactions_by_date[target_date]
    parts = []

    for txn in txns:
        txn_type = txn.transaction_type

        if txn_type == 'BUY':
            parts.append(f"BOUGHT {txn.quantity}")
        elif txn_type == 'SELL':
            parts.append(f"SOLD {txn.quantity}")
        elif txn_type == 'TRANSFER':
            # Transfer is bed-and-ISA, show direction based on quantity sign
            if txn.quantity > 0:
                parts.append(f"TRANSFER IN {txn.quantity}")
            else:
                parts.append(f"TRANSFER OUT {abs(txn.quantity)}")
        elif txn_type == 'STOCK_CONVERSION':
            # Determine if it's a split (same ticker) or conversion (different ticker)
            if txn.new_ticker:
                parts.append(f"CONVERTED to {txn.new_ticker}")
            elif txn.new_quantity and txn.quantity:
                # Calculate split ratio
                ratio = txn.new_quantity / txn.quantity
                if ratio >= 1:
                    parts.append(f"SPLIT x{ratio:.2g}")
                else:
                    # Reverse split
                    parts.append(f"REVERSE SPLIT {ratio:.2g}x")
            else:
                parts.append("CONVERTED")

    result = "; ".join(parts)
    if result:
        logger.debug(f"Transaction on {target_date}: {result}")
    return result


def calculate_price_over_time(start_date: datetime, stock_data: Dict,
                              price_data: Dict) -> pd.DataFrame:
    """Calculate individual stock prices over time.

    Unlike value_over_time (which calculates portfolio VALUES), this returns
    individual stock PRICES for each day since start_date.

    Args:
        start_date: Start date for the price history
        stock_data: Dict mapping (ticker, category) to stock data
        price_data: Pre-fetched price data keyed by current_ticker

    Returns:
        DataFrame with columns: date, ticker1, ticker2, ...
        Values are GBP closing prices
    """
    logger.info("Calculating price-over-time")

    eval_date = datetime.now()
    n_days = (eval_date.date() - start_date.date()).days

    # Generate list of dates
    date_range = [start_date.date() + timedelta(days=i) for i in range(n_days + 1)]

    # Get unique tickers that were held at some point during the period
    # Store (original_ticker, current_ticker, stock_name) tuples
    tickers_held = set()
    # Also build a mapping of original_ticker -> date -> list of transactions
    transactions_by_ticker_date = {}

    for stock_key, data in stock_data.items():
        # Include if held at start, held at end, or had any activity
        if (data['holdings_at_start'] > 1e-6 or
            data['holdings_at_end'] > 1e-6 or
            len(data['transactions_since_start']) > 0):
            original_ticker = data['ticker']
            tickers_held.add((original_ticker, data['current_ticker'], data['stock_name']))

            # Build transaction lookup by date
            if original_ticker not in transactions_by_ticker_date:
                transactions_by_ticker_date[original_ticker] = {}

            for txn in data['transactions_since_start']:
                txn_date = txn.date.date()
                if txn_date not in transactions_by_ticker_date[original_ticker]:
                    transactions_by_ticker_date[original_ticker][txn_date] = []
                transactions_by_ticker_date[original_ticker][txn_date].append(txn)

    # Sort by ticker name for consistent column order
    sorted_tickers = sorted(tickers_held, key=lambda x: x[0])

    # Log transaction collection summary
    total_txn_count = sum(
        len(txns) for ticker_txns in transactions_by_ticker_date.values()
        for txns in ticker_txns.values()
    )
    tickers_with_txns = [t for t, dates in transactions_by_ticker_date.items() if dates]
    logger.info(f"Collected {total_txn_count} transactions for {len(tickers_with_txns)} tickers")
    for ticker in tickers_with_txns:
        txn_dates = transactions_by_ticker_date[ticker]
        txn_count = sum(len(txns) for txns in txn_dates.values())
        logger.debug(f"  {ticker}: {txn_count} transactions on {len(txn_dates)} dates")

    logger.info(f"Generating prices for {len(sorted_tickers)} stocks over {len(date_range)} days")

    # Build price matrix with "Name (Ticker)" column headers and transaction columns
    results = []
    for current_date in date_range:
        current_datetime = datetime.combine(current_date, datetime.min.time())
        row = {'date': current_date}

        for original_ticker, current_ticker, stock_name in sorted_tickers:
            # Price column
            price = holdings_calculator.get_stock_price_from_data(
                current_ticker, current_datetime, price_data
            )
            price_column = f"{stock_name} ({original_ticker})"
            row[price_column] = price

            # Transaction column
            txn_column = f"Transactions ({original_ticker})"
            txn_text = _format_transactions_for_date(
                transactions_by_ticker_date.get(original_ticker, {}),
                current_date
            )
            row[txn_column] = txn_text

        results.append(row)

    df = pd.DataFrame(results)

    # Ensure column order: date first, then price and transaction columns paired by ticker
    ordered_columns = ['date']
    for original_ticker, current_ticker, stock_name in sorted_tickers:
        ordered_columns.append(f"{stock_name} ({original_ticker})")
        ordered_columns.append(f"Transactions ({original_ticker})")
    df = df[ordered_columns]

    logger.info(f"Price-over-time complete: {len(df)} rows, {len(df.columns)} columns")

    return df
