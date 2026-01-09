"""Full history mode processing.

This module handles the full history portfolio review mode, which analyzes
all transactions across all stocks to calculate current positions, valuations,
and performance metrics.
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
import value_over_time_processor


def process_full_history(portfolio_review: PortfolioReview, value_over_time_days: int,
                         market_data_fetcher) -> Dict[str, pd.DataFrame]:
    """Process full history mode - three-phase implementation.

    Phase 1: Analyze transactions for each stock
    Phase 2: Fetch current prices and exchange rates
    Phase 3: Calculate final metrics

    Args:
        portfolio_review: PortfolioReview instance containing full transaction history
        value_over_time_days: Optional number of days for value-over-time feature.
                             If specified, fetches historical prices for this many days
                             to avoid re-fetching later.
        market_data_fetcher: MarketDataFetcher instance for price cache access

    Returns:
        Dictionary with:
        - 'individual_stocks': DataFrame with individual stock data (clean, no aggregations)
        - 'whole_portfolio': DataFrame with single row for overall portfolio totals
        - 'per_tag': DataFrame with one row per tag containing tag totals
        - 'per_category': DataFrame with one row per category containing category totals
        - 'value_over_time': DataFrame with daily valuations (None if value_over_time_days not specified)
    """
    logger.info("Processing full history mode - three-phase implementation")

    # Determine price fetch date range based on whether value-over-time is requested
    if value_over_time_days:
        # For value-over-time: need n_days for backward price lookback
        # batch_get_stock_prices will add additional buffer for weekend/holiday handling
        logger.info(f"Value-over-time requested: will request {value_over_time_days} days of price history")
    else:
        logger.info("No value-over-time requested: will fetch current prices only")

    # Phase 1: Analyze transactions for each stock
    stock_data = {}
    stocks_needing_prices = []
    # Build mapping of original ticker to current ticker (after conversions)
    ticker_to_current_ticker = {}

    ticker_category_pairs = portfolio_review.get_all_tickers()
    logger.info(f"Processing {len(ticker_category_pairs)} stock/category combinations")

    for ticker, category in ticker_category_pairs:
        logger.info(f"Phase 1: Analyzing transactions for {ticker} in {category}")

        # Get stock information
        stock_name = portfolio_review.get_stock_name(ticker, category)
        # Capitalize category for display (isa -> ISA, taxable -> Taxable, pension -> Pension)
        account_type = category.upper() if category == 'isa' else category.capitalize()
        tag = portfolio_review.get_stock_tag(ticker, category)
        transactions = portfolio_review.get_transaction_history(ticker, category)

        if not transactions:
            logger.warning(f"No transactions found for {ticker}")
            continue

        # Use unified method to calculate transactions through today
        # For full history, we want to include all transactions (no investment threshold)
        results = transaction_processor.calculate_transactions_through_date(
            transactions,
            datetime.now(),
            include_investment_threshold=True  # Use threshold to exclude dividend accumulations
        )

        # Extract the data we need
        total_invested = results['total_invested']
        total_received = results['total_received']
        units_held = results['units_held']
        gross_units_bought = results['gross_units_bought']
        conversion_adjusted_cost_basis = results['conversion_adjusted_cost_basis']

        # Get current ticker after any conversions (or original if no conversions)
        current_ticker = results['current_ticker'] if results['current_ticker'] else ticker

        # Store mapping of original ticker to current ticker for later price data remapping
        ticker_to_current_ticker[ticker] = current_ticker

        # Get transaction date range
        first_transaction_date = transactions[0].get_date() if transactions else None
        final_transaction_date = transactions[-1].get_date() if transactions else None

        # Store stock data using (ticker, category) tuple as key
        stock_key = (ticker, category)
        stock_data[stock_key] = {
            'ticker': ticker,
            'current_ticker': current_ticker,
            'stock_name': stock_name,
            'account_type': account_type,
            'tag': tag,
            'total_invested': total_invested,
            'total_received': total_received,
            'units_held': units_held,
            'gross_units_bought': gross_units_bought,
            'conversion_adjusted_cost_basis': conversion_adjusted_cost_basis,
            'first_transaction_date': first_transaction_date,
            'final_transaction_date': final_transaction_date,
            'num_transactions': len(transactions),
            'transactions': transactions  # Store for stock split detection
        }

        # If still holding shares, we need current price
        if units_held > 0:
            stocks_needing_prices.append(current_ticker)

            if current_ticker != ticker:
                logger.info(f"  {ticker}: {units_held:.0f} shares held, need current price (using ticker {current_ticker})")
            else:
                logger.info(f"  {ticker}: {units_held:.0f} shares held, need current price")
        else:
            logger.info(f"  {ticker}: Fully sold, no current price needed")

    # Phase 2: Fetch current prices and exchange rates
    logger.info(f"Phase 2: Fetching prices for {len(stocks_needing_prices)} stocks")
    current_prices = {}
    highs_and_vol = {}

    if stocks_needing_prices:
        # Determine date range for price fetch
        today = datetime.now()

        if value_over_time_days:
            # Fetch extended historical data for value-over-time feature
            # Caller specifies exact evaluation range
            # batch_get_stock_prices will add all necessary buffering internally
            price_start_date = today - timedelta(days=value_over_time_days)
        else:
            # Fetch at least 90 days to support volatility calculations
            # Volatility calculation needs 90-day window, so we must fetch at least that much
            # batch_get_stock_prices will add 21-day buffer (total = 111 days)
            price_start_date = today - timedelta(days=90)

        # Use live rates for current valuations, historical rates for value-over-time
        use_live_rates = not bool(value_over_time_days)
        current_ticker_price_data = market_data_fetcher.batch_get_stock_prices(stocks_needing_prices, price_start_date, today, use_live_rates=use_live_rates)

        # Use current_ticker_price_data directly - it's already keyed by current ticker
        # (No remapping needed - calculate_stock_value looks up by current_ticker)
        current_prices = current_ticker_price_data

        # Calculate recent highs and volatility using current tickers
        # (Already keyed by current_ticker, no remapping needed)
        highs_and_vol = financial_metrics.calculate_highs_and_volatility(current_ticker_price_data)

    # Phase 3: Calculate final metrics
    logger.info("Phase 3: Calculating final metrics")
    results = []

    # Build transaction aggregators for MWRR calculation at different scopes
    portfolio_transactions = []
    category_transactions = defaultdict(list)
    tag_transactions = defaultdict(list)

    for stock_key, data in stock_data.items():
        ticker = stock_key[0]  # Extract ticker from tuple
        category = stock_key[1]  # Extract category from tuple
        # Capitalize category for display
        account_type = category.upper() if category == 'isa' else category.capitalize()
        current_value = 0.0
        current_price = None

        # Calculate current value if still holding shares using unified valuation logic
        current_ticker = data['current_ticker']
        if data['units_held'] > 0:
            # Use the helper function that handles stock splits and price lookback
            # Holdings were calculated through datetime.now(), use final_transaction_date as holdings_date
            current_value, current_price = holdings_calculator.calculate_stock_value(
                current_ticker,
                data['units_held'],
                data['final_transaction_date'],
                datetime.now(),
                data['transactions'],
                current_prices
            )

            if current_value is None or current_price is None:
                error_msg = f"No price data available for {current_ticker} (holding {data['units_held']:.2f} shares)"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.debug(f"  {ticker}: {data['units_held']:.0f} shares @ £{current_price:.2f} = £{current_value:.2f}")

        # Calculate performance metrics
        total_pnl = data['total_received'] + current_value - data['total_invested']

        # Calculate simple ROI (P&L / total invested)
        simple_roi = total_pnl / data['total_invested'] if data['total_invested'] > 0 else 0.0

        # Get transactions for this specific stock
        stock_transactions = None
        for category_stocks in portfolio_review.stock_notes.values():
            for stock in category_stocks:
                if stock.ticker == ticker and stock.category == category:
                    stock_transactions = stock.transactions
                    break
            if stock_transactions:
                break

        # Calculate Money-Weighted Rate of Return (MWRR) for this individual stock
        mwrr = None
        if stock_transactions:
            # For stocks that are still held, create explicit synthetic SELL transaction
            # This makes MWRR calculation semantically clear and matches periodic_review approach
            mwrr_transactions = list(stock_transactions)
            if data['units_held'] > 0:
                # Add synthetic SELL at today with current market value
                synthetic_sell = StockTransaction(
                    date=datetime.now(),
                    transaction_type='SELL',
                    quantity=data['units_held'],
                    price_per_share=current_value / data['units_held'],
                    total_amount=current_value
                )
                mwrr_transactions.append(synthetic_sell)
            
            # Calculate MWRR (current value is now in synthetic transaction)
            mwrr = transaction_processor.calculate_mwrr_for_transactions(mwrr_transactions)

            # Collect transactions for aggregated MWRR calculations
            # Use mwrr_transactions (includes synthetic SELL) for aggregations
            portfolio_transactions.extend(mwrr_transactions)

            # Use capitalized category name to match summary DataFrame
            category_key = account_type  # Already capitalized (ISA/Taxable/Pension)
            category_transactions[category_key].extend(mwrr_transactions)

            tag_key = data['tag'] if data['tag'] else 'No Tag'
            tag_transactions[tag_key].extend(mwrr_transactions)

        # Get highs and volatility data
        recent_high = None
        volatility = None
        current_price_pct_of_high = None
        if current_ticker in highs_and_vol:
            recent_high = highs_and_vol[current_ticker]['recent_high']
            volatility = highs_and_vol[current_ticker]['annualized_volatility']

            # Calculate current price as percentage of recent high
            if recent_high and recent_high > 0 and data['units_held'] > 0:
                current_price = current_value / data['units_held']
                current_price_pct_of_high = current_price / recent_high

        # Calculate current price per share (for display)
        current_price_per_share = None
        if data['units_held'] > 0 and current_value > 0:
            current_price_per_share = current_value / data['units_held']

        # Calculate unrealized profit (profit from currently held units)
        unrealized_profit = 0.0
        if data['units_held'] > 0 and data['gross_units_bought'] > 0 and current_price_per_share is not None:
            average_cost_per_unit = data['conversion_adjusted_cost_basis'] / data['gross_units_bought']
            unrealized_profit = data['units_held'] * (current_price_per_share - average_cost_per_unit)
            logger.debug(f"  {ticker}: Unrealized profit = {data['units_held']:.2f} × (£{current_price_per_share:.2f} - £{average_cost_per_unit:.2f}) = £{unrealized_profit:.2f}")

        # Build result record
        result = {
            'ticker': ticker,
            'stock_name': data['stock_name'],
            'account_type': data['account_type'],
            'tag': data['tag'],
            'total_invested': data['total_invested'],
            'total_received': data['total_received'],
            'current_value': current_value,
            'total_pnl': total_pnl,
            'unrealized_profit': unrealized_profit,
            'simple_roi': simple_roi,
            'mwrr': mwrr,
            'units_held': data['units_held'],
            'current_price': current_price_per_share,
            'first_transaction_date': data['first_transaction_date'],
            'final_transaction_date': data['final_transaction_date'],
            'num_transactions': data['num_transactions'],
            'recent_high': recent_high,
            'volatility': volatility,
            'current_price_pct_of_high': current_price_pct_of_high
        }

        results.append(result)
        logger.info(f"  {ticker} in {account_type}: Invested £{data['total_invested']:.2f}, "
                   f"Received £{data['total_received']:.2f}, "
                   f"Current £{current_value:.2f}, "
                   f"P&L £{total_pnl:.2f}")

    # Calculate aggregated MWRRs for portfolio, categories, and tags
    logger.info("Calculating aggregated MWRRs for portfolio, categories, and tags")

    # Portfolio-level MWRR
    # Note: Held stocks already have synthetic SELL transactions, so no terminal value needed
    portfolio_mwrr = transaction_processor.calculate_mwrr_for_transactions(portfolio_transactions)
    logger.info(f"Portfolio MWRR: {portfolio_mwrr*100:.2f}%" if portfolio_mwrr else "Portfolio MWRR: N/A")

    # Category-level MWRRs
    # Note: Held stocks already have synthetic SELL transactions, so no terminal values needed
    category_mwrrs = transaction_processor.calculate_aggregated_mwrr(category_transactions)

    # Tag-level MWRRs
    # Note: Held stocks already have synthetic SELL transactions, so no terminal values needed
    tag_mwrrs = transaction_processor.calculate_aggregated_mwrr(tag_transactions)

    # Convert to DataFrame
    df = pd.DataFrame(results)

    # Create clean individual stocks DataFrame (no aggregations)
    individual_stocks_df = df.copy()

    # Calculate aggregations for summary DataFrames
    whole_portfolio_df, per_tag_df, per_category_df = create_portfolio_summaries(
        df, portfolio_mwrr, category_mwrrs, tag_mwrrs
    )

    logger.info(f"Full history processing completed: {len(individual_stocks_df)} stocks processed")

    # Calculate value-over-time if requested
    value_over_time_df = None
    if value_over_time_days:
        logger.info(f"Calculating value-over-time for {value_over_time_days} days")
        value_over_time_df = value_over_time_processor.calculate_value_over_time(
            value_over_time_days, stock_data, market_data_fetcher
        )

    return {
        'individual_stocks': individual_stocks_df,
        'whole_portfolio': whole_portfolio_df,
        'per_tag': per_tag_df,
        'per_category': per_category_df,
        'value_over_time': value_over_time_df
    }


def _calculate_summary_row(df: pd.DataFrame, name: str, mwrr: Optional[float] = None) -> Dict:
    """Calculate summary statistics for a dataframe.

    Helper function to eliminate code duplication between whole portfolio and group summaries.

    Args:
        df: DataFrame containing individual stock data
        name: Display name for this summary row
        mwrr: Optional MWRR value for this group

    Returns:
        Dictionary with summary statistics
    """
    total_invested = df['total_invested'].sum()
    total_received = df['total_received'].sum()
    total_current = df['current_value'].sum()
    total_pnl = df['total_pnl'].sum()
    total_unrealized = df['unrealized_profit'].sum()
    roi = total_pnl / total_invested if total_invested > 0 else 0

    return {
        'tag': name,
        'total_invested': total_invested,
        'total_received': total_received,
        'current_value': total_current,
        'total_pnl': total_pnl,
        'unrealized_profit': total_unrealized,
        'roi': roi,
        'mwrr': mwrr
    }


def create_portfolio_summaries(df: pd.DataFrame,
                                portfolio_mwrr: Optional[float] = None,
                                category_mwrrs: Optional[Dict[str, float]] = None,
                                tag_mwrrs: Optional[Dict[str, float]] = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create portfolio summary DataFrames.

    Args:
        df: DataFrame containing individual stock data
        portfolio_mwrr: MWRR for whole portfolio
        category_mwrrs: Dict of MWRR by category
        tag_mwrrs: Dict of MWRR by tag

    Returns:
        Tuple of (whole_portfolio_df, per_tag_df, per_category_df)
    """
    if df.empty:
        empty_df = pd.DataFrame(columns=['tag', 'total_invested', 'total_received', 'current_value', 'total_pnl', 'roi'])
        return empty_df, empty_df, empty_df

    # Create whole portfolio DataFrame using helper
    whole_portfolio_df = pd.DataFrame([_calculate_summary_row(df, 'Whole Portfolio', portfolio_mwrr)])

    # Calculate per-tag summaries
    per_tag_df = calculate_group_summaries(df, 'tag', 'tag', tag_mwrrs)

    # Calculate per-category summaries
    per_category_df = calculate_group_summaries(df, 'account_type', 'account_type', category_mwrrs)

    return whole_portfolio_df, per_tag_df, per_category_df


def calculate_group_summaries(df: pd.DataFrame, group_column: str, name_column: str,
                               group_mwrrs: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Calculate summaries for grouped data (by tag or category).

    Args:
        df: DataFrame containing individual stock data
        group_column: Column name to group by (e.g., 'tag', 'account_type')
        name_column: Column name for display purposes (unused but kept for consistency)
        group_mwrrs: Dict mapping group names to their aggregated MWRR values

    Returns:
        DataFrame with summary statistics for each group
    """
    if group_mwrrs is None:
        group_mwrrs = {}
    rows = []
    for group_value, group_df in df.groupby(group_column, dropna=False):
        group_name = group_value if pd.notna(group_value) else 'No Tag'

        # Use helper to calculate basic statistics
        row = _calculate_summary_row(group_df, group_name, group_mwrrs.get(group_name))

        # Calculate first and last transaction dates
        first_transaction = group_df['first_transaction_date'].min()
        last_transaction = group_df['final_transaction_date'].max()

        # Add transaction dates to the row from helper
        row['first_transaction_date'] = first_transaction
        row['final_transaction_date'] = last_transaction

        rows.append(row)

    return pd.DataFrame(rows)
