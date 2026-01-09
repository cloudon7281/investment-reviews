"""Periodic review mode processing.

This module handles periodic portfolio review analysis, which compares
performance between two time periods by classifying stocks as new, retained,
or sold based on their transaction history.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from logger import logger
from portfolio_review import PortfolioReview, StockTransaction
from collections import defaultdict
import transaction_processor
import holdings_calculator
import financial_metrics


def process_periodic_review(portfolio_review: PortfolioReview, start_date: datetime,
                            end_date: datetime, eval_date: Optional[datetime],
                            market_data_fetcher) -> Dict[str, pd.DataFrame]:
    """Process a periodic review analysis.

    Args:
        portfolio_review: The portfolio review object containing all transaction data
        start_date: Start of the review period (date A)
        end_date: End of the review period (date B)
        eval_date: Evaluation date (date C), defaults to today
        market_data_fetcher: MarketDataFetcher instance for price fetching

    Returns:
        Dictionary with 'summary', 'per_tag', 'new', 'retained', and 'sold' DataFrames
    """
    if eval_date is None:
        eval_date = datetime.now()

    logger.info(f"Processing periodic review from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}, evaluated on {eval_date.strftime('%Y-%m-%d')}")

    # Step 1: Classify stocks
    classification = classify_stocks_by_review_period(portfolio_review, start_date, end_date)

    # Step 2: Set up stock currencies and fetch all prices in batch
    all_ticker_category_pairs = []
    for category in ['new', 'retained', 'sold']:
        all_ticker_category_pairs.extend(classification[category])

    if all_ticker_category_pairs:
        # Determine current tickers after any conversions (like full-history mode does)
        all_tickers = []
        ticker_to_current_ticker = {}  # Map original ticker -> current ticker after conversions

        for ticker, category in all_ticker_category_pairs:
            transactions = portfolio_review.get_transaction_history(ticker, category)

            # Use transaction processor to get current ticker after any conversions
            results = transaction_processor.calculate_transactions_through_date(
                transactions,
                datetime.now(),
                include_investment_threshold=False
            )

            # Get current ticker (or use original if no conversions)
            current_ticker = results['current_ticker'] if results['current_ticker'] else ticker

            all_tickers.append(current_ticker)
            ticker_to_current_ticker[ticker] = current_ticker

            if current_ticker != ticker:
                logger.info(f"Using current ticker {current_ticker} for {ticker} (post-conversion)")

        logger.info(f"Fetching prices for all stocks from {start_date.strftime('%Y-%m-%d')} to {eval_date.strftime('%Y-%m-%d')}")

        # Fetch all prices in a single batch call (using date range A to C)
        current_ticker_price_data = market_data_fetcher.batch_get_stock_prices(all_tickers, start_date, eval_date)
        logger.info(f"Retrieved price data for {len(current_ticker_price_data)} stocks")

        # Map price data back to original tickers for lookup
        price_data = {}
        for original_ticker, current_ticker in ticker_to_current_ticker.items():
            if current_ticker in current_ticker_price_data:
                price_data[original_ticker] = current_ticker_price_data[current_ticker]
            else:
                logger.warning(f"No price data found for current ticker {current_ticker} (original: {original_ticker})")

        # Calculate recent highs and volatility using current tickers
        highs_and_vol_current = financial_metrics.calculate_highs_and_volatility(current_ticker_price_data, eval_date)

        # Map highs and volatility back to original tickers
        highs_and_vol = {}
        for original_ticker, current_ticker in ticker_to_current_ticker.items():
            if current_ticker in highs_and_vol_current:
                highs_and_vol[original_ticker] = highs_and_vol_current[current_ticker]
    else:
        logger.info("No stocks to process")
        price_data = {}
        highs_and_vol = {}

    # Step 3: Calculate performance for each category
    results = {}
    category_transactions = {}
    category_current_values = {}
    all_tag_transactions = defaultdict(list)
    all_tag_current_values = defaultdict(float)

    for category in ['new', 'retained', 'sold']:
        if classification[category]:
            df, transactions, current_value, tag_txns, tag_values = calculate_periodic_performance(
                classification[category],
                portfolio_review,
                start_date,
                end_date,
                eval_date,
                category,
                price_data,  # Pass the pre-fetched price data
                highs_and_vol  # Pass the highs and volatility data
            )
            results[category] = df
            category_transactions[category] = transactions
            category_current_values[category] = current_value
            # Collect tag-level data across categories
            for tag, txns in tag_txns.items():
                all_tag_transactions[tag].extend(txns)
            for tag, value in tag_values.items():
                all_tag_current_values[tag] += value
        else:
            results[category] = pd.DataFrame()
            category_transactions[category] = []
            category_current_values[category] = 0.0

    # Calculate category-level MWRRs
    category_mwrrs = transaction_processor.calculate_aggregated_mwrr(
        category_transactions
    )

    # Calculate tag-level MWRRs
    tag_mwrrs = transaction_processor.calculate_aggregated_mwrr(
        all_tag_transactions
    )

    # Step 4: Create summary
    results['summary'] = create_periodic_review_summary(results, start_date, end_date, eval_date, category_mwrrs)

    # Step 5: Create tag-level summary (keep individual DataFrames clean)
    results['per_tag'] = create_tag_summary(results, start_date, end_date, eval_date, tag_mwrrs)

    logger.info(f"Periodic review processing completed: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['sold'])} sold")

    return results


def classify_stocks_by_review_period(portfolio_review: PortfolioReview, start_date: datetime,
                                     end_date: datetime) -> Dict[str, List[Tuple[str, str]]]:
    """Classify stocks into new, retained, sold, and out-of-scope categories.

    Args:
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period

    Returns:
        Dictionary with lists of (ticker, category) tuples for each category
    """
    logger.info(f"Classifying stocks for period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    classification = {'new': [], 'retained': [], 'sold': [], 'out_of_scope': []}

    # Tolerance for floating point precision issues (e.g., 1e-12 instead of 0)
    HOLDINGS_TOLERANCE = 1e-6

    all_tickers = portfolio_review.get_all_tickers()
    logger.info(f"Found {len(all_tickers)} total tickers to classify")

    for ticker, category in all_tickers:
        logger.debug(f"Classifying ticker: {ticker} in {category}")
        transactions = portfolio_review.get_transaction_history(ticker, category)

        if not transactions:
            logger.debug(f"  No transactions found for {ticker} - marking as out_of_scope")
            classification['out_of_scope'].append((ticker, category))
            continue

        # Sort transactions by date
        transactions.sort(key=lambda x: x.date)

        first_transaction_date = transactions[0].date
        last_transaction_date = transactions[-1].date

        logger.debug(f"  First transaction: {first_transaction_date.strftime('%Y-%m-%d')}")
        logger.debug(f"  Last transaction: {last_transaction_date.strftime('%Y-%m-%d')}")

        # Check if stock is out of scope
        if first_transaction_date > end_date:
            logger.debug(f"  {ticker} is out of scope (first transaction after period: {first_transaction_date.strftime('%Y-%m-%d')})")
            classification['out_of_scope'].append((ticker, category))
            continue

        # Get holdings at start and end of period
        holdings_at_start = holdings_calculator.get_holdings_at_date(transactions, start_date)
        holdings_at_end = holdings_calculator.get_holdings_at_date(transactions, end_date)

        logger.debug(f"  Holdings at start ({start_date.strftime('%Y-%m-%d')}): {holdings_at_start}")
        logger.debug(f"  Holdings at end ({end_date.strftime('%Y-%m-%d')}): {holdings_at_end}")

        # Apply tolerance for floating point precision issues
        holdings_at_start_effective = holdings_at_start if abs(holdings_at_start) > HOLDINGS_TOLERANCE else 0.0
        holdings_at_end_effective = holdings_at_end if abs(holdings_at_end) > HOLDINGS_TOLERANCE else 0.0

        logger.debug(f"  Effective holdings at start: {holdings_at_start_effective}")
        logger.debug(f"  Effective holdings at end: {holdings_at_end_effective}")

        # Classify based on transaction history and holdings
        if first_transaction_date >= start_date and first_transaction_date <= end_date:
            # First transaction in period = new stock
            logger.debug(f"  {ticker} classified as NEW (first transaction in period)")
            classification['new'].append((ticker, category))
        elif holdings_at_start_effective > 0 and holdings_at_end_effective > 0:
            # Held throughout period = retained
            logger.debug(f"  {ticker} classified as RETAINED (held at both start and end)")
            classification['retained'].append((ticker, category))
        elif holdings_at_start_effective > 0 and holdings_at_end_effective == 0:
            # Sold during period = sold
            logger.debug(f"  {ticker} classified as SOLD (held at start, not at end)")
            classification['sold'].append((ticker, category))
        else:
            # Everything else = out of scope
            logger.debug(f"  {ticker} classified as OUT_OF_SCOPE (other case)")
            classification['out_of_scope'].append((ticker, category))

    logger.info(f"Classification complete: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['sold'])} sold, {len(classification['out_of_scope'])} out_of_scope")

    return classification


def calculate_periodic_performance(ticker_category_pairs: List[Tuple[str, str]], portfolio_review: PortfolioReview,
                                   start_date: datetime, end_date: datetime, eval_date: datetime, category: str,
                                   price_data: Dict = None, highs_and_vol: Dict = None) -> Tuple[pd.DataFrame, List, float, Dict, Dict]:
    """Calculate performance for a specific category of stocks.

    Args:
        ticker_category_pairs: List of (ticker, category) tuples in this category
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        category: Category name ('new', 'retained', or 'sold')
        price_data: Pre-fetched price data
        highs_and_vol: Pre-computed highs and volatility data

    Returns:
        Tuple of (DataFrame with performance data, list of all transactions, total current value,
                 dict of tag->transactions, dict of tag->current_value)
    """
    logger.info(f"Calculating performance for {len(ticker_category_pairs)} {category} stocks")
    results = []
    all_transactions = []
    total_current_value = 0.0
    tag_transactions = defaultdict(list)
    tag_current_values = defaultdict(float)

    for ticker, stock_category in ticker_category_pairs:
        logger.debug(f"Processing {category} stock: {ticker} in {stock_category}")
        try:
            transactions = portfolio_review.get_transaction_history(ticker, stock_category)
            stock_name = portfolio_review.get_stock_name(ticker, stock_category)
            logger.debug(f"  Stock name: {stock_name}")
            logger.debug(f"  Transaction count: {len(transactions)}")

            if category == 'new':
                # New stocks: investment during [A,B] → value at C
                logger.debug(f"  Calculating NEW stock performance for {ticker}")
                start_value, period_days = holdings_calculator.calculate_start_value_from_transactions(transactions, start_date, end_date, eval_date, ticker, 'BUY')
            elif category == 'retained':
                # Retained stocks: value at B → value at C
                logger.debug(f"  Calculating RETAINED stock performance for {ticker}")
                start_value, period_days = holdings_calculator.calculate_retained_stock_performance_unified(transactions, start_date, end_date, eval_date, ticker, price_data)
                # For retained stocks, "Days Held" should be from first EVER transaction to eval_date
                if transactions:
                    first_ever_txn = min(transactions, key=lambda t: t.date)
                    period_days = (eval_date - first_ever_txn.date).days
            elif category == 'sold':
                # Sold stocks: actual sales during [A,B] → value at C (counterfactual)
                logger.debug(f"  Calculating SOLD stock performance for {ticker}")
                start_value, _ = holdings_calculator.calculate_start_value_from_transactions(transactions, start_date, end_date, eval_date, ticker, 'SELL')
                # For sold stocks, set period_days to None (will display as blank)
                period_days = None
            else:
                logger.debug(f"  Unknown category {category} for {ticker}")
                continue

            logger.debug(f"  Start value: {start_value}, Period days: {period_days}")
            if start_value is None:
                logger.debug(f"  Skipping {ticker} - start_value is None")
                continue

            # Get current value and holdings at eval_date using pre-fetched price data
            if category == 'sold':
                # For sold stocks, use holdings at start_date for counterfactual calculation
                current_value, current_holdings, current_price = holdings_calculator.get_stock_valuations_at_date(ticker, start_date, end_date, eval_date, transactions, price_data, use_start_date_holdings=True)
            else:
                # For new & retained stocks, use holdings at end_date
                current_value, current_holdings, current_price = holdings_calculator.get_stock_valuations_at_date(ticker, start_date, end_date, eval_date, transactions, price_data)
            logger.debug(f"  Current value: {current_value}, Current holdings: {current_holdings}")

            if current_value is None:
                continue

            # Calculate P&L and ROI
            pnl = current_value - start_value
            simple_roi = pnl / start_value if start_value > 0 else 0.0

            # Calculate MWRR for periodic review using synthetic transactions
            # This isolates period performance by treating start_value and current_value as cashflows

            synthetic_transactions = []
            if category == 'new':
                # For new stocks: use actual BUY transactions in period + terminal value
                period_transactions = [txn for txn in transactions if start_date <= txn.date <= end_date]
                synthetic_transactions = period_transactions
            elif category == 'retained':
                # For retained: fake BUY at start_date with start_value, fake SELL at eval_date with current_value
                synthetic_transactions = [
                    StockTransaction(
                        date=start_date,
                        transaction_type='BUY',
                        quantity=0,  # Quantity doesn't matter for MWRR
                        price_per_share=0.0,
                        total_amount=start_value
                    )
                ]
            elif category == 'sold':
                # For sold: fake BUY at start_date with sale proceeds, fake SELL at eval_date with counterfactual value
                # start_value might be 0 if stock was transferred (not sold)
                # In that case, use the absolute value of transfer amounts from period
                if start_value == 0:
                    # Sum absolute values of SELL/TRANSFER transactions in period to get "proceeds"
                    period_outflows = [txn for txn in transactions
                                      if start_date <= txn.date <= end_date
                                      and txn.transaction_type in ['SELL', 'TRANSFER']]
                    start_value = sum(abs(txn.total_amount) for txn in period_outflows)

                synthetic_transactions = [
                    StockTransaction(
                        date=start_date,
                        transaction_type='BUY',
                        quantity=0,
                        price_per_share=0.0,
                        total_amount=start_value
                    )
                ]

            mwrr = transaction_processor.calculate_mwrr_for_transactions(synthetic_transactions)

            # Get tag for this ticker (needed for tag-level aggregation)
            tag = portfolio_review.get_stock_tag(ticker, stock_category)

            # Collect synthetic transactions for aggregated MWRR
            all_transactions.extend(synthetic_transactions)
            total_current_value += current_value
            tag_transactions[tag].extend(synthetic_transactions)
            tag_current_values[tag] += current_value

            # Use the holdings returned from the value calculation (consistent with current_value)
            units_held = current_holdings

            # Get highs and volatility data
            recent_high = None
            volatility = None
            current_price_pct_of_high = None
            if highs_and_vol and ticker in highs_and_vol:
                recent_high = highs_and_vol[ticker]['recent_high']
                volatility = highs_and_vol[ticker]['annualized_volatility']

                # Calculate current price as percentage of recent high (both in GBP)
                if recent_high and recent_high > 0 and current_price is not None:
                    current_price_pct_of_high = current_price / recent_high

            # tag was already retrieved above for tag-level aggregation

            result_record = {
                'ticker': ticker,
                'company_name': stock_name,
                'tag': tag,
                'units_held': units_held,
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'simple_roi': simple_roi,
                'mwrr': mwrr,
                'period_days': period_days,
                'current_price': (current_price, 'GBP'),
                'recent_high': (recent_high, 'GBP'),
                'volatility': volatility,
                'current_price_pct_of_high': current_price_pct_of_high
            }
            logger.debug(f"    Result record for {ticker}: {result_record}")
            results.append(result_record)

        except Exception as e:
            logger.error(f"Error calculating performance for {ticker}: {str(e)}")
            continue

    return pd.DataFrame(results), all_transactions, total_current_value, tag_transactions, tag_current_values


def _calculate_periodic_summary_metrics(df: pd.DataFrame) -> Tuple[float, float, float, float]:
    """Calculate summary metrics from a DataFrame with periodic review data.

    Args:
        df: DataFrame with 'start_value', 'current_value', and 'pnl' columns (tuple format)

    Returns:
        Tuple of (start_value, current_value, pnl, roi)
    """
    # Extract values from tuples (all are GBP)
    total_start = sum(val[0] for val in df['start_value'])
    total_current = sum(val[0] for val in df['current_value'])
    total_pnl = sum(val[0] for val in df['pnl'])

    # Calculate ROI
    roi = total_pnl / total_start if total_start > 0 else 0.0

    return total_start, total_current, total_pnl, roi


def create_periodic_review_summary(results: Dict[str, pd.DataFrame], start_date: datetime,
                                   end_date: datetime, eval_date: datetime,
                                   category_mwrrs: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Create a summary of the periodic review.

    Args:
        results: Dictionary with 'new', 'retained', and 'sold' DataFrames
        start_date: Start of review period
        end_date: End of review period
        eval_date: Evaluation date
        category_mwrrs: Dict mapping category ('new'/'retained'/'sold') to MWRR

    Returns:
        Summary DataFrame
    """
    if category_mwrrs is None:
        category_mwrrs = {}
    summary_data = []

    for category in ['new', 'retained', 'sold']:
        df = results.get(category, pd.DataFrame())
        if df.empty:
            summary_data.append({
                'category': category.title(),
                'count': 0,
                'start_value': (0.0, 'GBP'),
                'current_value': (0.0, 'GBP'),
                'pnl': (0.0, 'GBP'),
                'roi': 0.0,
                'mwrr': None
            })
        else:
            # Calculate summary metrics using helper
            total_start, total_current, total_pnl, roi = _calculate_periodic_summary_metrics(df)

            # Get aggregated MWRR for this category
            mwrr = category_mwrrs.get(category, None)

            summary_data.append({
                'category': category.title(),
                'count': len(df),
                'start_value': (total_start, 'GBP'),
                'current_value': (total_current, 'GBP'),
                'pnl': (total_pnl, 'GBP'),
                'roi': roi,
                'mwrr': mwrr
            })

    return pd.DataFrame(summary_data)


def create_tag_summary(results: Dict[str, pd.DataFrame], start_date: datetime, end_date: datetime,
                      eval_date: datetime, tag_mwrrs: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Create tag-level summary for periodic review.

    Args:
        results: Dictionary with 'new', 'retained', 'sold' DataFrames
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        tag_mwrrs: Optional dict mapping tag names to their aggregated MWRR values

    Returns:
        DataFrame with tag-level summary data
    """
    if tag_mwrrs is None:
        tag_mwrrs = {}
    tag_summary_data = []

    # Process each category
    for category in ['new', 'retained', 'sold']:
        if results[category].empty:
            continue

        # Group by tag
        tag_groups = results[category].groupby('tag', dropna=False)

        for tag, group_df in tag_groups:
            # Calculate summary metrics using helper
            start_value, current_value, pnl, roi = _calculate_periodic_summary_metrics(group_df)
            count = len(group_df)

            # Get aggregated MWRR for this tag (if available)
            mwrr = tag_mwrrs.get(tag, None)

            # Use format "Category - Tag Name" for display
            tag_name = tag if pd.notna(tag) else 'No Tag'
            display_name = f"{category.title()} - {tag_name}"

            tag_summary_data.append({
                'category': display_name,
                'tag': tag_name,
                'count': count,
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'roi': roi,
                'mwrr': mwrr,
                'sort_category': category,  # Keep original category for sorting
                'sort_pnl': pnl  # Keep P&L for sorting
            })

    # Create DataFrame (no sorting - that's a display concern for PortfolioReporter)
    tag_summary_df = pd.DataFrame(tag_summary_data)

    return tag_summary_df
