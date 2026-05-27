"""Periodic review mode processing.

This module handles periodic portfolio review analysis, which compares
performance between two time periods by classifying stocks as new, retained,
or sold based on their transaction history.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from logger import logger
from portfolio_review import PortfolioReview
import transaction_processor
import holdings_calculator
import financial_metrics


# ---------------------------------------------------------------------------
# Benchmark definitions
#
# Each entry: (tag, yahoo_ticker, display_name)
#
# Ticker selection rationale:
#   - US Equities:       ^DJI, ^GSPC, ^IXIC  — Yahoo-native index tickers, highly reliable
#   - European Equities: ^STOXX50E            — Yahoo-native index ticker
#   - UK Equities:       ^FTSE               — FTSE 100, reliable; ^FTMC excluded (unreliable on Yahoo)
#   - World Equities:    SWDA.L              — London-listed iShares Core MSCI World ETF
#                                               (preferred over IWDA.AS which is less reliable on Yahoo)
#   - Government Bonds:  IGLT.L              — iShares UK Gilts UCITS ETF, London-listed
#   - Corporate Bonds:   SLXX.L              — iShares GBP Corp Bond UCITS ETF, London-listed
# ---------------------------------------------------------------------------
BENCHMARKS: List[Tuple[str, str, str]] = [
    ('Benchmarks - US Equities',       '^DJI',      'Dow Jones Industrial Average'),
    ('Benchmarks - US Equities',       '^GSPC',     'S&P 500'),
    ('Benchmarks - US Equities',       '^IXIC',     'Nasdaq Composite'),
    ('Benchmarks - European Equities', '^STOXX50E', 'Euro Stoxx 50'),
    ('Benchmarks - UK Equities',       '^FTSE',     'FTSE 100'),
    ('Benchmarks - World Equities',    'SWDA.L',    'iShares Core MSCI World (SWDA.L)'),
    ('Benchmarks - Government Bonds',  'IGLT.L',    'iShares UK Gilts (IGLT.L)'),
    ('Benchmarks - Corporate Bonds',   'SLXX.L',    'iShares GBP Corp Bond (SLXX.L)'),
]

# Normalised start value for each benchmark (£)
BENCHMARK_NORMALISED_START = 1000.0


def calculate_benchmark_performance(price_data: Dict, start_date: datetime,
                                    eval_date: datetime) -> pd.DataFrame:
    """Calculate normalised benchmark performance for all defined benchmarks.

    Each benchmark's start value is normalised to BENCHMARK_NORMALISED_START (£1000) so
    that relative performance can be compared directly.  These rows must NOT be
    included in portfolio total calculations (is_benchmark=True).

    Args:
        price_data: Pre-fetched price data keyed by ticker (GBP, from MarketDataFetcher)
        start_date: Period start date — price used to normalise start value
        eval_date: Evaluation date — price used to compute current value

    Returns:
        DataFrame with one row per successfully-fetched benchmark ticker, containing
        the same columns as periodic_review_detail rows plus is_benchmark=True.
    """
    results = []
    for tag, ticker, display_name in BENCHMARKS:
        start_price = holdings_calculator.get_stock_price_from_data(ticker, start_date, price_data)
        eval_price = holdings_calculator.get_stock_price_from_data(ticker, eval_date, price_data)

        if start_price is None or start_price == 0:
            logger.warning(f"Benchmark {ticker}: no start price at {start_date.date()}, skipping")
            continue
        if eval_price is None:
            logger.warning(f"Benchmark {ticker}: no eval price at {eval_date.date()}, skipping")
            continue

        scale = BENCHMARK_NORMALISED_START / start_price
        current_value = eval_price * scale
        pnl = current_value - BENCHMARK_NORMALISED_START
        roi = pnl / BENCHMARK_NORMALISED_START

        results.append({
            'ticker': ticker,
            'company_name': display_name,
            'tag': tag,
            'start_value': (BENCHMARK_NORMALISED_START, 'GBP'),
            'current_value': (current_value, 'GBP'),
            'pnl': (pnl, 'GBP'),
            'simple_roi': roi,
            'is_benchmark': True,
        })
        logger.debug(f"Benchmark {ticker}: start={BENCHMARK_NORMALISED_START:.2f}, "
                     f"current={current_value:.2f}, roi={roi:.2%}")

    logger.info(f"Benchmark performance calculated for {len(results)}/{len(BENCHMARKS)} tickers")
    return pd.DataFrame(results)


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
    for cat in ['new', 'sold']:
        all_ticker_category_pairs.extend(classification[cat])
    # retained and increased share the same (ticker, category) pairs; deduplicate using retained
    for entry in classification['retained']:
        all_ticker_category_pairs.append((entry[0], entry[1]))

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

    # Build set of (ticker, category) pairs that are in the 'increased' bucket,
    # so the retained pass can identify them for name-suffixing and holdings capping.
    increased_tickers = {(entry[0], entry[1]) for entry in classification['increased']}

    for cat in ['new', 'retained', 'sold', 'increased']:
        if classification[cat]:
            if cat == 'retained':
                df = calculate_periodic_performance(
                    classification[cat],
                    portfolio_review,
                    start_date,
                    end_date,
                    eval_date,
                    cat,
                    price_data,
                    highs_and_vol,
                    increased_tickers=increased_tickers,
                    market_data_fetcher=market_data_fetcher
                )
            else:
                df = calculate_periodic_performance(
                    classification[cat],
                    portfolio_review,
                    start_date,
                    end_date,
                    eval_date,
                    cat,
                    price_data,
                    highs_and_vol,
                    market_data_fetcher=market_data_fetcher
                )
            results[cat] = df
        else:
            results[cat] = pd.DataFrame()

    # Step 4: Fetch benchmark prices and calculate benchmark performance.
    # Benchmarks are fetched separately so they never pollute portfolio price_data or
    # category_current_values.  Each row is flagged is_benchmark=True so any future
    # summation site can filter them out explicitly.
    benchmark_tickers = [ticker for _, ticker, _ in BENCHMARKS]
    logger.info(f"Fetching benchmark prices for {len(benchmark_tickers)} tickers")
    benchmark_price_data = market_data_fetcher.batch_get_stock_prices(
        benchmark_tickers, start_date, eval_date
    )
    results['benchmarks'] = calculate_benchmark_performance(benchmark_price_data, start_date, eval_date)

    # Step 5: Create summary
    results['summary'] = create_periodic_review_summary(
        results, start_date, end_date, eval_date,
        benchmarks_df=results['benchmarks']
    )

    # Step 6: Create tag-level summary (keep individual DataFrames clean)
    results['per_tag'] = create_tag_summary(
        results, start_date, end_date, eval_date,
        benchmarks_df=results['benchmarks']
    )

    logger.info(f"Periodic review processing completed: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['increased'])} increased, {len(classification['sold'])} sold, {len(results['benchmarks'])} benchmarks")

    return results


def classify_stocks_by_review_period(portfolio_review: PortfolioReview, start_date: datetime,
                                     end_date: datetime) -> Dict[str, List]:
    """Classify stocks into new, retained, increased, sold, and out-of-scope categories.

    Args:
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period

    Returns:
        Dictionary with:
        - 'new': list of (ticker, category) tuples
        - 'retained': list of (ticker, category, holdings_at_start, holdings_at_end) tuples
        - 'increased': list of (ticker, category, holdings_at_start, holdings_at_end) tuples
        - 'sold': list of (ticker, category) tuples
        - 'out_of_scope': list of (ticker, category) tuples
    """
    logger.info(f"Classifying stocks for period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    classification = {'new': [], 'retained': [], 'increased': [], 'sold': [], 'out_of_scope': []}

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
        if holdings_at_end_effective > 0 and holdings_at_start_effective == 0:
            # No holdings at start but held at end = new (or repurchased) stock
            logger.debug(f"  {ticker} classified as NEW (first transaction in period)")
            classification['new'].append((ticker, category))
        elif holdings_at_start_effective > 0 and holdings_at_end_effective > 0:
            # Held throughout period = retained (and possibly increased)
            if holdings_at_end_effective > holdings_at_start_effective:
                logger.debug(f"  {ticker} classified as RETAINED+INCREASED (held at both ends, position grew from {holdings_at_start_effective} to {holdings_at_end_effective})")
                classification['retained'].append((ticker, category, holdings_at_start_effective, holdings_at_end_effective))
                classification['increased'].append((ticker, category, holdings_at_start_effective, holdings_at_end_effective))
            else:
                logger.debug(f"  {ticker} classified as RETAINED (held at both start and end)")
                classification['retained'].append((ticker, category, holdings_at_start_effective, holdings_at_end_effective))
        elif holdings_at_start_effective > 0 and holdings_at_end_effective == 0:
            # Sold during period = sold
            logger.debug(f"  {ticker} classified as SOLD (held at start, not at end)")
            classification['sold'].append((ticker, category))
        else:
            # Everything else = out of scope
            logger.debug(f"  {ticker} classified as OUT_OF_SCOPE (other case)")
            classification['out_of_scope'].append((ticker, category))

    logger.info(f"Classification complete: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['increased'])} increased, {len(classification['sold'])} sold, {len(classification['out_of_scope'])} out_of_scope")

    return classification


def calculate_periodic_performance(ticker_category_pairs: List, portfolio_review: PortfolioReview,
                                   start_date: datetime, end_date: datetime, eval_date: datetime, category: str,
                                   price_data: Dict = None, highs_and_vol: Dict = None,
                                   increased_tickers: set = None,
                                   market_data_fetcher=None) -> pd.DataFrame:
    """Calculate performance for a specific category of stocks.

    Args:
        ticker_category_pairs: List of (ticker, category) tuples for new/sold, or
                               (ticker, category, holdings_at_start, holdings_at_end) for retained/increased
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        category: Category name ('new', 'retained', 'increased', or 'sold')
        price_data: Pre-fetched price data
        highs_and_vol: Pre-computed highs and volatility data
        increased_tickers: Set of (ticker, category) pairs that are in the 'increased' bucket;
                           used by the retained path to cap holdings and suffix names
        market_data_fetcher: MarketDataFetcher instance for currency conversion in doubling
                             metrics (pass-through from process_periodic_review)

    Returns:
        DataFrame with performance data
    """
    if increased_tickers is None:
        increased_tickers = set()

    logger.info(f"Calculating performance for {len(ticker_category_pairs)} {category} stocks")
    results = []

    for entry in ticker_category_pairs:
        # Unpack: retained/increased have 4 elements; new/sold have 2
        if len(entry) == 4:
            ticker, stock_category, holdings_at_start, holdings_at_end = entry
        else:
            ticker, stock_category = entry
            holdings_at_start = None
            holdings_at_end = None

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
                is_increased = (ticker, stock_category) in increased_tickers
                if is_increased:
                    # Cap holdings to start-of-period holdings to isolate original position
                    stock_name = stock_name + ' (retained)'
                    logger.debug(f"  Stock is also INCREASED; capping holdings to {holdings_at_start}, name -> '{stock_name}'")
                    start_value, period_days = holdings_calculator.calculate_retained_stock_performance_unified(
                        transactions, start_date, end_date, eval_date, ticker, price_data,
                        holdings_override=holdings_at_start
                    )
                else:
                    start_value, period_days = holdings_calculator.calculate_retained_stock_performance_unified(
                        transactions, start_date, end_date, eval_date, ticker, price_data
                    )
                # For retained stocks, "Days Held" should be from first EVER transaction to eval_date
                if transactions:
                    first_ever_txn = min(transactions, key=lambda t: t.date)
                    period_days = (eval_date - first_ever_txn.date).days
            elif category == 'increased':
                # Increased stocks: delta investment during [A,B] → value at C
                # Calculated like 'New': use actual BUY amounts in [start_date, end_date]
                logger.debug(f"  Calculating INCREASED stock performance for {ticker}")
                start_value, period_days = holdings_calculator.calculate_start_value_from_transactions(transactions, start_date, end_date, eval_date, ticker, 'BUY')
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
            elif category == 'increased':
                # For increased: current value is based on delta holdings at eval_date
                delta_holdings = holdings_at_end - holdings_at_start
                current_price = holdings_calculator.get_stock_price_from_data(ticker, eval_date, price_data)
                if current_price is None:
                    logger.debug(f"  No current price for {ticker}, skipping")
                    continue
                current_holdings = delta_holdings
                current_value = delta_holdings * current_price
                logger.debug(f"  INCREASED: delta_holdings={delta_holdings}, current_price={current_price}, current_value={current_value}")
            elif category == 'retained' and (ticker, stock_category) in increased_tickers:
                # For capped retained: current value is based on start holdings (not end holdings)
                current_price = holdings_calculator.get_stock_price_from_data(ticker, eval_date, price_data)
                if current_price is None:
                    logger.debug(f"  No current price for {ticker}, skipping")
                    continue
                current_holdings = holdings_at_start
                current_value = holdings_at_start * current_price
                logger.debug(f"  RETAINED(capped): holdings_at_start={holdings_at_start}, current_price={current_price}, current_value={current_value}")
            else:
                # For new & retained (uncapped) stocks, use holdings at end_date
                current_value, current_holdings, current_price = holdings_calculator.get_stock_valuations_at_date(ticker, start_date, end_date, eval_date, transactions, price_data)
            logger.debug(f"  Current value: {current_value}, Current holdings: {current_holdings}")

            if current_value is None:
                continue

            # Calculate P&L and ROI
            pnl = current_value - start_value
            simple_roi = pnl / start_value if start_value > 0 else 0.0

            # Get tag for this ticker (needed for display grouping)
            tag = portfolio_review.get_stock_tag(ticker, stock_category)

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

            # Compute lifetime doubling metrics for holding categories
            if category in ('new', 'retained', 'increased'):
                # current_price is in GBP; calculate_doubling_metrics expects native currency.
                # Back-convert to native using the current exchange rate.
                stock_currency = portfolio_review.get_stock_currency(ticker, stock_category)
                if stock_currency and stock_currency not in ('GBP', 'GBp') and market_data_fetcher is not None:
                    ex_rate = market_data_fetcher.get_current_exchange_rate(stock_currency, 'GBP')
                    current_price_native = current_price / ex_rate if ex_rate and ex_rate > 0 else current_price
                else:
                    current_price_native = current_price
                logger.debug(f"  Doubling metrics for {ticker}: currency={stock_currency}, current_price_gbp={current_price:.4f}, current_price_native={current_price_native:.4f}")
                progress_to_doubling, doubling_count = transaction_processor.calculate_doubling_metrics(
                    transactions, current_price_native
                )
            else:
                progress_to_doubling = None
                doubling_count = None

            result_record = {
                'ticker': ticker,
                'company_name': stock_name,
                'tag': tag,
                'units_held': units_held,
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'simple_roi': simple_roi,
                'period_days': period_days,
                'current_price': (current_price, 'GBP'),
                'recent_high': (recent_high, 'GBP'),
                'volatility': volatility,
                'current_price_pct_of_high': current_price_pct_of_high,
                'progress_to_doubling': progress_to_doubling,
                'doubling_count': doubling_count,
            }
            logger.debug(f"    Result record for {ticker}: {result_record}")
            results.append(result_record)

        except Exception as e:
            logger.error(f"Error calculating performance for {ticker}: {str(e)}")
            continue

    return pd.DataFrame(results)


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
                                   benchmarks_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Create a summary of the periodic review.

    Args:
        results: Dictionary with 'new', 'retained', 'increased', and 'sold' DataFrames
        start_date: Start of review period
        end_date: End of review period
        eval_date: Evaluation date
        benchmarks_df: Optional DataFrame of benchmark rows (is_benchmark=True).
            When provided a 'Benchmarks' summary row is appended.  Benchmark values
            are NOT added to portfolio totals (see is_benchmark flag).

    Returns:
        Summary DataFrame
    """
    summary_data = []

    for category in ['new', 'retained', 'increased', 'sold']:
        df = results.get(category, pd.DataFrame())
        # Filter out any is_benchmark rows that may have leaked in (defensive guard)
        if not df.empty and 'is_benchmark' in df.columns:
            df = df[df['is_benchmark'] != True]  # noqa: E712
        if df.empty:
            summary_data.append({
                'category': category.title(),
                'count': 0,
                'start_value': (0.0, 'GBP'),
                'current_value': (0.0, 'GBP'),
                'pnl': (0.0, 'GBP'),
                'roi': 0.0,
                'is_benchmark': False,
            })
        else:
            # Calculate summary metrics using helper
            total_start, total_current, total_pnl, roi = _calculate_periodic_summary_metrics(df)

            summary_data.append({
                'category': category.title(),
                'count': len(df),
                'start_value': (total_start, 'GBP'),
                'current_value': (total_current, 'GBP'),
                'pnl': (total_pnl, 'GBP'),
                'roi': roi,
                'is_benchmark': False,
            })

    # Append a single 'Benchmarks' category row (excluded from portfolio totals)
    if benchmarks_df is not None and not benchmarks_df.empty:
        total_start, total_current, total_pnl, roi = _calculate_periodic_summary_metrics(benchmarks_df)
        summary_data.append({
            'category': 'Benchmarks',
            'count': len(benchmarks_df),
            'start_value': (total_start, 'GBP'),
            'current_value': (total_current, 'GBP'),
            'pnl': (total_pnl, 'GBP'),
            'roi': roi,
            'is_benchmark': True,
        })

    return pd.DataFrame(summary_data)


def create_tag_summary(results: Dict[str, pd.DataFrame], start_date: datetime, end_date: datetime,
                      eval_date: datetime,
                      benchmarks_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Create tag-level summary for periodic review.

    Args:
        results: Dictionary with 'new', 'retained', 'increased', 'sold' DataFrames
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        benchmarks_df: Optional DataFrame of benchmark rows.  When provided, one
            summary row per benchmark tag is appended with is_benchmark=True.
            These rows are excluded from portfolio totals.

    Returns:
        DataFrame with tag-level summary data
    """
    tag_summary_data = []

    # Process each portfolio category
    for category in ['new', 'retained', 'increased', 'sold']:
        cat_df = results[category]
        # Exclude any is_benchmark rows that may have leaked in (defensive guard)
        if not cat_df.empty and 'is_benchmark' in cat_df.columns:
            cat_df = cat_df[cat_df['is_benchmark'] != True]  # noqa: E712
        if cat_df.empty:
            continue

        # Group by tag
        tag_groups = cat_df.groupby('tag', dropna=False)

        for tag, group_df in tag_groups:
            # Calculate summary metrics using helper
            start_value, current_value, pnl, roi = _calculate_periodic_summary_metrics(group_df)
            count = len(group_df)

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
                'is_benchmark': False,
                'sort_category': category,  # Keep original category for sorting
                'sort_pnl': pnl  # Keep P&L for sorting
            })

    # Append one row per benchmark tag (excluded from portfolio totals)
    if benchmarks_df is not None and not benchmarks_df.empty:
        for tag_name, group_df in benchmarks_df.groupby('tag', dropna=False):
            start_value, current_value, pnl, roi = _calculate_periodic_summary_metrics(group_df)
            tag_summary_data.append({
                'category': tag_name,
                'tag': tag_name,
                'count': len(group_df),
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'roi': roi,
                'is_benchmark': True,
                'sort_category': 'benchmark',
                'sort_pnl': pnl,
            })

    # Create DataFrame (no sorting - that's a display concern for PortfolioReporter)
    tag_summary_df = pd.DataFrame(tag_summary_data)

    return tag_summary_df
