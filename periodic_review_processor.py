"""Periodic review mode processing.

This module handles periodic portfolio review analysis, which compares
performance between two time periods by classifying stocks as new, retained,
or sold based on their transaction history.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from logger import logger
from portfolio_review import PortfolioReview
import transaction_processor
import holdings_calculator
import financial_metrics
import thesis_config


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


def calculate_thesis_candidate_performance(theses: List[Dict], price_data: Dict,
                                           highs_and_vol: Dict, held_tickers: set,
                                           start_date: datetime,
                                           eval_date: datetime) -> pd.DataFrame:
    """Calculate normalised performance for every configured thesis candidate.

    Uses the same date boundaries and normalisation as the benchmark analysis: each
    candidate starts at BENCHMARK_NORMALISED_START (£1000) at start_date and is valued
    at eval_date.  Candidates without usable price data are omitted.

    Args:
        theses: Thesis definitions as returned by thesis_config.load_thesis_config
        price_data: Pre-fetched candidate price data keyed by ticker (GBP)
        highs_and_vol: Pre-computed highs and volatility data keyed by ticker
        held_tickers: Upper-cased tickers held in the portfolio at the end of the period
        start_date: Period start date — price used to normalise start value
        eval_date: Evaluation date — price used to compute current value

    Returns:
        DataFrame with one row per candidate that has valid performance data.
    """
    results = []
    for thesis in theses:
        for candidate in thesis['candidates']:
            ticker = candidate['ticker']
            start_price = holdings_calculator.get_stock_price_from_data(ticker, start_date, price_data)
            eval_price = holdings_calculator.get_stock_price_from_data(ticker, eval_date, price_data)

            if start_price is None or start_price == 0:
                logger.warning(f"Thesis candidate {ticker}: no start price at {start_date.date()}, skipping")
                continue
            if eval_price is None:
                logger.warning(f"Thesis candidate {ticker}: no eval price at {eval_date.date()}, skipping")
                continue

            scale = BENCHMARK_NORMALISED_START / start_price
            current_value = eval_price * scale
            pnl = current_value - BENCHMARK_NORMALISED_START
            roi = pnl / BENCHMARK_NORMALISED_START

            is_held = ticker.upper() in held_tickers

            candidate_highs = highs_and_vol.get(ticker)
            vs_highs = financial_metrics.price_vs_highs(eval_price, candidate_highs)
            volatility = candidate_highs['annualized_volatility'] if candidate_highs else None
            recent_high = vs_highs['recent_high']

            results.append({
                'thesis': thesis['name'],
                'ticker': ticker,
                'company_name': candidate['name'],
                'is_held': is_held,
                'held': 'Yes' if is_held else '',
                'start_value': (BENCHMARK_NORMALISED_START, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'simple_roi': roi,
                'current_price': (eval_price, 'GBP'),
                'recent_high': (recent_high, 'GBP') if recent_high is not None else None,
                'volatility': volatility,
                'current_price_pct_of_high': vs_highs['current_price_pct_of_high'],
            })
            logger.debug(f"Thesis candidate {ticker} ({thesis['name']}): roi={roi:.2%}, held={is_held}")

    configured = sum(len(thesis['candidates']) for thesis in theses)
    logger.info(f"Thesis candidate performance calculated for {len(results)}/{configured} candidates")
    return pd.DataFrame(results)


def create_thesis_summary(theses: List[Dict], candidates_df: pd.DataFrame) -> pd.DataFrame:
    """Create the per-thesis summary of candidate, held and relative performance.

    Baskets are equal-weighted: the basket return is the arithmetic mean of the
    individual candidate returns.  A holding counts once regardless of position size.

    Args:
        theses: Thesis definitions as returned by thesis_config.load_thesis_config
        candidates_df: DataFrame from calculate_thesis_candidate_performance

    Returns:
        DataFrame with one row per thesis that has at least one valid candidate.
    """
    if candidates_df.empty:
        logger.warning("No thesis candidates have valid returns; thesis summary is empty")
        return pd.DataFrame()

    summary_data = []

    for thesis in theses:
        name = thesis['name']
        configured = len(thesis['candidates'])

        thesis_rows = candidates_df[candidates_df['thesis'] == name]
        if thesis_rows.empty:
            logger.warning(f"Thesis '{name}': no candidates with valid returns, omitting from summary")
            continue

        candidate_return = thesis_rows['simple_roi'].mean()

        held_rows = thesis_rows[thesis_rows['is_held']]
        if held_rows.empty:
            held_return = None
            held_vs_candidates = None
            logger.info(f"Thesis '{name}': no configured candidates are held")
        else:
            held_return = held_rows['simple_roi'].mean()
            held_vs_candidates = held_return - candidate_return

        valid_candidates = len(thesis_rows)
        positive_candidates = int((thesis_rows['simple_roi'] > 0).sum())

        summary_data.append({
            'thesis': name,
            'candidate_return': candidate_return,
            'held_return': held_return,
            'held_vs_candidates': held_vs_candidates,
            'positive_candidates': positive_candidates,
            'valid_candidates': valid_candidates,
            'configured_candidates': configured,
            'breadth': positive_candidates / valid_candidates,
        })
        logger.info(f"Thesis '{name}': {valid_candidates}/{configured} valid candidates, "
                    f"{len(held_rows)} held, candidate basket {candidate_return:.2%}")

    return pd.DataFrame(summary_data)


def process_periodic_review(portfolio_review: PortfolioReview, start_date: datetime,
                            end_date: datetime, eval_date: Optional[datetime],
                            market_data_fetcher,
                            thesis_candidates_path: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """Process a periodic review analysis.

    Args:
        portfolio_review: The portfolio review object containing all transaction data
        start_date: Start of the review period (date A)
        end_date: End of the review period (date B)
        eval_date: Evaluation date (date C), defaults to today
        market_data_fetcher: MarketDataFetcher instance for price fetching
        thesis_candidates_path: Optional path to a thesis candidate configuration file.
            When supplied, 'thesis_candidates' and 'thesis_summary' DataFrames are added.

    Returns:
        Dictionary with 'summary', 'per_tag', 'new', 'retained', and 'sold' DataFrames
    """
    if eval_date is None:
        eval_date = datetime.now()

    logger.info(f"Processing periodic review from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}, evaluated on {eval_date.strftime('%Y-%m-%d')}")

    # Load the thesis configuration up front so a bad file fails before any price fetching
    theses = thesis_config.load_thesis_config(thesis_candidates_path) if thesis_candidates_path else None

    # Prices are fetched from whichever is earlier: the start of the review period, or the
    # start of the recent-high window.  A monthly review would otherwise fetch barely two
    # months of prices, and the 90-day high would silently be a 50-day high
    # (investment-reviews#26).  Every fetch below uses this start, because the price cache
    # is keyed by ticker alone: a ticker first fetched over a short range would be served
    # from cache to the next caller.
    price_fetch_start = min(
        start_date,
        eval_date - timedelta(days=financial_metrics.RECENT_HIGH_WINDOW_DAYS)
    )

    # Step 1: Classify stocks
    classification = classify_stocks_by_review_period(portfolio_review, start_date, end_date)

    # Step 2: Set up stock currencies and fetch all prices in batch
    # One (ticker, account) pair per stock: any account that holds it gives its current
    # ticker.  Increased stocks are also in retained, so 'increased' is not listed.
    all_ticker_category_pairs = []
    for cat in ['new', 'sold', 'retained']:
        all_ticker_category_pairs.extend((entry[0], entry[1][0]) for entry in classification[cat])

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

        logger.info(f"Fetching prices for all stocks from {price_fetch_start.strftime('%Y-%m-%d')} to {eval_date.strftime('%Y-%m-%d')}")

        # Fetch all prices in a single batch call (using date range A to C)
        current_ticker_price_data = market_data_fetcher.batch_get_stock_prices(all_tickers, price_fetch_start, eval_date)
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

    # Build set of tickers that are in the 'increased' bucket,
    # so the retained pass can identify them for name-suffixing and holdings capping.
    increased_tickers = {entry[0] for entry in classification['increased']}

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
        benchmark_tickers, price_fetch_start, eval_date
    )
    results['benchmarks'] = calculate_benchmark_performance(benchmark_price_data, start_date, eval_date)

    # Step 5: Thesis candidate performance (only when a configuration file was supplied).
    # Candidate prices are fetched separately for the same reason as benchmarks: they must
    # never pollute portfolio price_data or category totals.
    results['thesis_candidates'] = pd.DataFrame()
    results['thesis_summary'] = pd.DataFrame()
    if theses:
        candidate_tickers = sorted({c['ticker'] for t in theses for c in t['candidates']})
        logger.info(f"Fetching thesis candidate prices for {len(candidate_tickers)} tickers")
        candidate_price_data = market_data_fetcher.batch_get_stock_prices(
            candidate_tickers, price_fetch_start, eval_date
        )
        candidate_highs_and_vol = financial_metrics.calculate_highs_and_volatility(
            candidate_price_data, eval_date
        )

        # A candidate is held if it is in the portfolio at the end of the review period,
        # i.e. classified as new or retained.  Never recorded in the configuration file.
        held_tickers = {ticker.upper() for ticker, *_ in classification['new']}
        held_tickers |= {ticker.upper() for ticker, *_ in classification['retained']}

        results['thesis_candidates'] = calculate_thesis_candidate_performance(
            theses, candidate_price_data, candidate_highs_and_vol, held_tickers,
            start_date, eval_date
        )
        results['thesis_summary'] = create_thesis_summary(theses, results['thesis_candidates'])

    # Step 6: Create summary
    results['summary'] = create_periodic_review_summary(
        results, start_date, end_date, eval_date,
        benchmarks_df=results['benchmarks']
    )

    # Step 7: Create tag-level summary (keep individual DataFrames clean)
    results['per_tag'] = create_tag_summary(
        results, start_date, end_date, eval_date,
        benchmarks_df=results['benchmarks'],
        thesis_candidates_df=results['thesis_candidates']
    )

    logger.info(f"Periodic review processing completed: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['increased'])} increased, {len(classification['sold'])} sold, {len(results['benchmarks'])} benchmarks")

    return results


def _units_in_price_terms(transactions: List, date: datetime) -> float:
    """Units held at `date`, counted in the units today's prices are quoted in.

    Yahoo's price history is adjusted for every split, so a holding counted before a split
    has to be scaled by the splits that followed it.  Unscaled, a split inside the review
    period reads as a purchase of the extra shares (the Amphenol subdivision, #86).
    """
    return (holdings_calculator.get_holdings_at_date(transactions, date)
            * holdings_calculator.get_subsequent_stock_splits(transactions, date))


def classify_stocks_by_review_period(portfolio_review: PortfolioReview, start_date: datetime,
                                     end_date: datetime) -> Dict[str, List]:
    """Classify stocks into new, retained, increased, sold, and out-of-scope categories.

    A stock is classified once, across every account that holds it: the review decides
    what to do with each stock, so buying more of a stock in a second account is an
    increase, not a new holding, and selling out of one account while another still holds
    it is a partial sale.  Units in each account are counted separately, because a
    corporate action applies to the account its note was filed under, and then summed.

    Args:
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period

    Returns:
        Dictionary of lists keyed 'new', 'retained', 'increased', 'sold' and
        'out_of_scope'.  Each entry is (ticker, accounts, units_at_start, units_at_end),
        where accounts is a tuple of the account categories that held the stock at
        either end of the period, and units are counted in today's (split-adjusted)
        units.  An increased stock appears in both 'retained' and 'increased'.
    """
    logger.info(f"Classifying stocks for period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    classification = {'new': [], 'retained': [], 'increased': [], 'sold': [], 'out_of_scope': []}

    # Tolerance for floating point precision issues (e.g., 1e-12 instead of 0)
    HOLDINGS_TOLERANCE = 1e-6

    accounts_by_ticker = {}
    for ticker, category in portfolio_review.get_all_tickers():
        accounts_by_ticker.setdefault(ticker, []).append(category)
    logger.info(f"Found {len(accounts_by_ticker)} total tickers to classify")

    for ticker, categories in accounts_by_ticker.items():
        logger.debug(f"Classifying ticker: {ticker} in {', '.join(categories)}")
        accounts = []
        units_at_start = 0.0
        units_at_end = 0.0

        for category in categories:
            transactions = portfolio_review.get_transaction_history(ticker, category)
            if not transactions:
                logger.debug(f"  No transactions found for {ticker} in {category}")
                continue

            start = _units_in_price_terms(transactions, start_date)
            end = _units_in_price_terms(transactions, end_date)
            start = start if abs(start) > HOLDINGS_TOLERANCE else 0.0
            end = end if abs(end) > HOLDINGS_TOLERANCE else 0.0
            logger.debug(f"  {category}: {start} units at {start_date.strftime('%Y-%m-%d')}, "
                         f"{end} at {end_date.strftime('%Y-%m-%d')}")

            # An account that held nothing at either end took no part in the period
            if start == 0 and end == 0:
                continue
            accounts.append(category)
            units_at_start += start
            units_at_end += end

        entry = (ticker, tuple(accounts), units_at_start, units_at_end)

        # Classify based on holdings across all accounts
        if not accounts:
            logger.debug(f"  {ticker} classified as OUT_OF_SCOPE (not held at either end of the period)")
            classification['out_of_scope'].append((ticker, tuple(categories), 0.0, 0.0))
        elif units_at_start == 0:
            logger.debug(f"  {ticker} classified as NEW (not held at start)")
            classification['new'].append(entry)
        elif units_at_end == 0:
            logger.debug(f"  {ticker} classified as SOLD (held at start, not at end)")
            classification['sold'].append(entry)
        elif units_at_end - units_at_start > HOLDINGS_TOLERANCE:
            logger.debug(f"  {ticker} classified as RETAINED+INCREASED (position grew from {units_at_start} to {units_at_end})")
            classification['retained'].append(entry)
            classification['increased'].append(entry)
        else:
            logger.debug(f"  {ticker} classified as RETAINED (held at both start and end)")
            classification['retained'].append(entry)

    logger.info(f"Classification complete: {len(classification['new'])} new, {len(classification['retained'])} retained, {len(classification['increased'])} increased, {len(classification['sold'])} sold, {len(classification['out_of_scope'])} out_of_scope")

    return classification


def _traded_in_period(histories: List[List], start_date: datetime, end_date: datetime,
                      transaction_type: str) -> Tuple[Optional[float], float, Optional[datetime]]:
    """One type of trade during [A,B], across accounts: amount, units, and when it began.

    Units are split-adjusted per account, as the classification's are.  Returns
    (None, 0.0, None) when nothing happened in the period.  The date is the first trade
    of that type, or the first transaction of any type when there was none.
    """
    amount, units, in_period, trades = 0.0, 0.0, [], []
    for transactions in histories:
        for txn in transactions:
            if not start_date <= txn.date <= end_date:
                continue
            in_period.append(txn)
            if txn.transaction_type == transaction_type:
                trades.append(txn)
                amount += txn.total_amount or 0.0
                units += txn.quantity * holdings_calculator.get_subsequent_stock_splits(transactions, txn.date)
    if not in_period:
        return None, 0.0, None
    return amount, units, min(txn.date for txn in (trades or in_period))


def _account_label(category: str) -> str:
    """Display name for an account category, as the other modes show it."""
    return category.upper() if category == 'isa' else category.capitalize()


def calculate_periodic_performance(classified: List, portfolio_review: PortfolioReview,
                                   start_date: datetime, end_date: datetime, eval_date: datetime, category: str,
                                   price_data: Dict = None, highs_and_vol: Dict = None,
                                   increased_tickers: set = None,
                                   market_data_fetcher=None) -> pd.DataFrame:
    """Calculate performance for a specific category of stocks.

    Every value is units times price.  The units are the ones the classification counted,
    already summed across accounts and split-adjusted, so they match the price data and
    are not recounted here.

    Args:
        classified: (ticker, accounts, units_at_start, units_at_end) entries from
                    classify_stocks_by_review_period
        portfolio_review: The portfolio review object
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        category: Category name ('new', 'retained', 'increased', or 'sold')
        price_data: Pre-fetched price data
        highs_and_vol: Pre-computed highs and volatility data
        increased_tickers: Tickers that are in the 'increased' bucket; used by the retained
                           path to cap holdings and suffix names
        market_data_fetcher: MarketDataFetcher instance for currency conversion in doubling
                             metrics (pass-through from process_periodic_review)

    Returns:
        DataFrame with performance data
    """
    if increased_tickers is None:
        increased_tickers = set()
    if price_data is None:
        price_data = {}

    logger.info(f"Calculating performance for {len(classified)} {category} stocks")
    results = []

    for ticker, accounts, units_at_start, units_at_end in classified:
        logger.debug(f"Processing {category} stock: {ticker} in {', '.join(accounts)}")
        try:
            histories = [portfolio_review.get_transaction_history(ticker, account) for account in accounts]
            stock_name = portfolio_review.get_stock_name(ticker, accounts[0])
            logger.debug(f"  Stock name: {stock_name}")

            current_price = holdings_calculator.get_stock_price_from_data(ticker, eval_date, price_data)
            if current_price is None:
                logger.debug(f"  No current price for {ticker}, skipping")
                continue

            if category in ('new', 'increased'):
                # New and increased stocks: purchases during [A,B] → value at C.  The units
                # are the net addition, so when the period also saw sales (in this account
                # or another) they are costed at the period's average purchase price, not
                # at every purchase.
                bought, units_bought, first_date = _traded_in_period(histories, start_date, end_date, 'BUY')
                units_held = units_at_end if category == 'new' else units_at_end - units_at_start
                start_value = bought
                if bought is not None and units_bought > units_held:
                    start_value = bought * units_held / units_bought
                    logger.debug(f"  Net {units_held} of {units_bought} units bought; cost {bought} -> {start_value}")
                period_days = (eval_date - first_date).days if first_date else None
            elif category == 'retained':
                # Retained stocks: value at B → value at C.  An increased stock is capped to
                # the units held at the start, so the increase is reported only once.
                if ticker in increased_tickers:
                    stock_name = stock_name + ' (retained)'
                    units_held = units_at_start
                    logger.debug(f"  Stock is also INCREASED; capping holdings to {units_held}, name -> '{stock_name}'")
                else:
                    units_held = units_at_end
                price_at_end = holdings_calculator.get_stock_price_from_data(ticker, end_date, price_data)
                start_value = units_held * price_at_end if price_at_end is not None else None
                # For retained stocks, "Days Held" is from the first EVER transaction to eval_date
                first_ever = min(txn.date for transactions in histories for txn in transactions)
                period_days = (eval_date - first_ever).days
            elif category == 'sold':
                # Sold stocks: actual sales during [A,B] → value at C of what was sold (counterfactual)
                start_value, _, _ = _traded_in_period(histories, start_date, end_date, 'SELL')
                units_held = units_at_start
                period_days = None
            else:
                logger.debug(f"  Unknown category {category} for {ticker}")
                continue

            logger.debug(f"  Start value: {start_value}, Period days: {period_days}")
            if start_value is None:
                logger.debug(f"  Skipping {ticker} - start_value is None")
                continue

            current_value = units_held * current_price
            logger.debug(f"  Current value: {current_value}, Units: {units_held}")

            # Calculate P&L and ROI
            pnl = current_value - start_value
            simple_roi = pnl / start_value if start_value > 0 else 0.0

            # Accounts may tag the same stock differently.  Show every tag rather than
            # choosing one, so the disagreement is visible in the report.
            tags = []
            for account in accounts:
                tag = portfolio_review.get_stock_tag(ticker, account)
                if tag not in tags:
                    tags.append(tag)
            if len(tags) > 1:
                logger.warning(f"{ticker} is tagged differently in each account "
                               f"({', '.join(str(t) for t in tags)}); the review shows every tag")
                tag = ' / '.join(t if t else 'No Tag' for t in tags)
            else:
                tag = tags[0]

            # Get highs and volatility data (all prices in GBP)
            stock_highs = highs_and_vol.get(ticker) if highs_and_vol else None
            vs_highs = financial_metrics.price_vs_highs(current_price, stock_highs)
            volatility = stock_highs['annualized_volatility'] if stock_highs else None

            # Compute lifetime doubling metrics for holding categories
            if category in ('new', 'retained', 'increased'):
                # current_price is in GBP; calculate_doubling_metrics expects native currency.
                # Back-convert to native using the current exchange rate.
                stock_currency = portfolio_review.get_stock_currency(ticker, accounts[0])
                if stock_currency and stock_currency not in ('GBP', 'GBp') and market_data_fetcher is not None:
                    ex_rate = market_data_fetcher.get_current_exchange_rate(stock_currency, 'GBP')
                    current_price_native = current_price / ex_rate if ex_rate and ex_rate > 0 else current_price
                else:
                    current_price_native = current_price
                logger.debug(f"  Doubling metrics for {ticker}: currency={stock_currency}, current_price_gbp={current_price:.4f}, current_price_native={current_price_native:.4f}")
                # Lifetime means since the stock was first bought, so the account that has
                # held it longest.  Histories are not merged: each account carries its own
                # copy of a split, and a merged history would apply it once per account.
                longest_held = min(histories, key=lambda transactions: min(txn.date for txn in transactions))
                progress_to_doubling, doubling_count = transaction_processor.calculate_doubling_metrics(
                    longest_held, current_price_native
                )
            else:
                progress_to_doubling = None
                doubling_count = None

            result_record = {
                'ticker': ticker,
                'company_name': stock_name,
                'tag': tag,
                'accounts': ', '.join(_account_label(account) for account in accounts),
                'units_held': units_held,
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'simple_roi': simple_roi,
                'period_days': period_days,
                'current_price': (current_price, 'GBP'),
                'recent_high': (vs_highs['recent_high'], 'GBP'),
                'smoothed_high': (vs_highs['smoothed_high'], 'GBP'),
                'percentile_high': (vs_highs['percentile_high'], 'GBP'),
                'volatility': volatility,
                'current_price_pct_of_high': vs_highs['current_price_pct_of_high'],
                'current_price_pct_of_smoothed_high': vs_highs['current_price_pct_of_smoothed_high'],
                'current_price_pct_of_percentile_high': vs_highs['current_price_pct_of_percentile_high'],
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
                      benchmarks_df: Optional[pd.DataFrame] = None,
                      thesis_candidates_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Create tag-level summary for periodic review.

    Args:
        results: Dictionary with 'new', 'retained', 'increased', 'sold' DataFrames
        start_date: Start of the review period
        end_date: End of the review period
        eval_date: Evaluation date
        benchmarks_df: Optional DataFrame of benchmark rows.  When provided, one
            summary row per benchmark tag is appended with is_benchmark=True.
            These rows are excluded from portfolio totals.
        thesis_candidates_df: Optional DataFrame of thesis candidate rows.  When
            provided, one candidate-basket row per thesis is appended after the
            benchmark rows.  Like benchmarks these are notional £1000-per-stock
            baskets and are excluded from portfolio totals.

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

    # Append one candidate-basket row per thesis, after the benchmark rows
    if thesis_candidates_df is not None and not thesis_candidates_df.empty:
        for thesis_name, group_df in thesis_candidates_df.groupby('thesis', sort=False):
            start_value, current_value, pnl, roi = _calculate_periodic_summary_metrics(group_df)
            tag_summary_data.append({
                'category': f"Thesis - {thesis_name}",
                'tag': thesis_name,
                'count': len(group_df),
                'start_value': (start_value, 'GBP'),
                'current_value': (current_value, 'GBP'),
                'pnl': (pnl, 'GBP'),
                'roi': roi,
                'is_benchmark': True,
                'sort_category': 'thesis',
                'sort_pnl': pnl,
            })

    # Create DataFrame (no sorting - that's a display concern for PortfolioReporter)
    tag_summary_df = pd.DataFrame(tag_summary_data)

    return tag_summary_df
