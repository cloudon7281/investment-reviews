"""Market data fetching from Yahoo Finance API.

This module handles all interactions with the Yahoo Finance API including:
- Fetching historical stock prices
- Fetching exchange rates
- Data cleaning (spike filtering, UK pence/pounds transitions)
- Currency conversions
- Price and exchange rate caching
"""

from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
import yfinance as yf
from logger import logger


class MarketDataFetcher:
    """Fetches and caches market data from Yahoo Finance."""

    def __init__(self):
        """Initialize the market data fetcher with empty caches."""
        self.price_cache: Dict[str, pd.DataFrame] = {}
        self.exchange_rate_cache: Dict[str, float] = {}

    def get_current_exchange_rate(self, from_currency: str, to_currency: str = 'GBP') -> float:
        """Get the current live exchange rate between two currencies.

        Uses ticker.info to get real-time rates, not historical data.

        Args:
            from_currency: The source currency code (e.g., 'USD')
            to_currency: The target currency code (default: 'GBP')

        Returns:
            The current exchange rate
        """
        if from_currency == to_currency:
            return 1.0

        cache_key = f"{from_currency}_{to_currency}_live"
        if cache_key in self.exchange_rate_cache:
            return self.exchange_rate_cache[cache_key]

        try:
            # Use Ticker.info to get live exchange rate
            pair_symbol = f"{from_currency}{to_currency}=X"
            ticker = yf.Ticker(pair_symbol)
            info = ticker.info

            # Try regularMarketPrice first (most current)
            if 'regularMarketPrice' in info and info['regularMarketPrice']:
                rate = float(info['regularMarketPrice'])
                logger.debug(f"Got live {from_currency}/{to_currency} rate from ticker.info: {rate:.6f}")
                self.exchange_rate_cache[cache_key] = rate
                return rate

            # Fallback: try getting from recent history
            logger.debug(f"No regularMarketPrice for {pair_symbol}, trying history")
            hist = ticker.history(period='1d')
            if not hist.empty and 'Close' in hist.columns:
                rate = float(hist['Close'].iloc[-1])
                logger.debug(f"Got {from_currency}/{to_currency} rate from history: {rate:.6f}")
                self.exchange_rate_cache[cache_key] = rate
                return rate

            logger.warning(f"Could not get exchange rate for {pair_symbol}, defaulting to 1.0")
            return 1.0

        except Exception as e:
            logger.error(f"Error getting exchange rate for {pair_symbol}: {str(e)}")
            return 1.0

    def batch_get_ticker_info(self, tickers: List[str]) -> Dict[str, Dict]:
        """Get comprehensive ticker info for multiple tickers in a single API call.

        Returns:
            Dict mapping ticker to full info dictionary from Yahoo Finance API
        """
        logger.debug(f"Getting ticker info for {tickers}")
        try:
            # Use yf.Tickers (plural) for batch info fetching
            tickers_obj = yf.Tickers(tickers)
            info_dict = {}

            for ticker in tickers:
                try:
                    info = tickers_obj.tickers[ticker].info
                    # Store the full info dict for future extensibility
                    info_dict[ticker] = info
                    logger.debug(f"Got info for {ticker}: currency={info.get('currency', 'USD')}, exchange={info.get('exchange', '')}")
                except Exception as e:
                    logger.warning(f"Could not get info for {ticker}: {e}")
                    # Return minimal default info
                    info_dict[ticker] = {
                        'currency': 'USD',
                        'exchange': '',
                        'quoteType': '',
                        'shortName': ticker,
                        'longName': ticker
                    }

            return info_dict
        except Exception as e:
            logger.error(f"Error getting ticker info for {tickers}: {e}")
            logger.error("Cannot continue with invalid ticker information. Please check tickers and try again.")
            # Re-raise the exception instead of returning garbage data
            raise RuntimeError(f"Failed to get ticker information: {e}") from e

    def batch_get_stock_prices(self, tickers: List[str], start_date: datetime, end_date: datetime,
                               use_live_rates: bool = False, ticker_info_func=None) -> Dict[str, pd.DataFrame]:
        """Get historical prices for multiple tickers over a date range, always returning GBP values.

        Args:
            tickers: List of ticker symbols
            start_date: Start of date range
            end_date: End of date range
            use_live_rates: If True, use live exchange rates from ticker.info for current valuations.
                           If False, use historical rates from yf.download (for value-over-time)

        Returns:
            Dict mapping ticker to DataFrame with 'Close' column in GBP
        """
        logger.debug(f"Getting price data for {tickers} from {start_date} to {end_date}")
        uncached_tickers = [t for t in tickers if t not in self.price_cache]

        if uncached_tickers:
            try:
                # Add 21-day buffer before start_date to ensure we get data AT the start date
                # Covers: 14-day backward lookback in _get_stock_price_from_data() + 7 days for weekends/holidays
                buffer_start_date = start_date - timedelta(days=21)

                # Request data up to tomorrow to catch any finalized rates published under next day's date
                # But we'll use the most recent available rate regardless of date
                buffer_end_date = end_date + timedelta(days=1)

                # Step 1: Get ticker info for all uncached tickers (single API call)
                if ticker_info_func:
                    ticker_info = ticker_info_func(uncached_tickers)
                else:
                    ticker_info = self.batch_get_ticker_info(uncached_tickers)

                # Step 2: Get price data for all tickers (single API call)
                data = yf.download(uncached_tickers, start=buffer_start_date, end=buffer_end_date, progress=False, auto_adjust=False)

                # Log what was actually downloaded
                if len(uncached_tickers) == 1:
                    logger.info(f"Downloaded data for {uncached_tickers[0]}: {len(data) if not data.empty else 0} rows")
                    if not data.empty:
                        logger.info(f"  Date range: {data.index[0]} to {data.index[-1]}")
                        logger.debug(f"  Data shape: {data.shape}")
                        logger.debug(f"  Columns: {data.columns.tolist()}")
                else:
                    logger.info(f"Downloaded data for {len(uncached_tickers)} tickers: {len(data) if not data.empty else 0} rows")
                    if not data.empty:
                        logger.info(f"  Date range: {data.index[0]} to {data.index[-1]}")
                        logger.debug(f"  Data shape: {data.shape}")

                # Step 3: Get exchange rates for non-GBP currencies
                currencies_needed = set()
                for ticker in uncached_tickers:
                    currency = ticker_info[ticker].get('currency', 'USD')
                    if currency not in ['GBP', 'GBp']:
                        currencies_needed.add(currency)

                exchange_rates = {}

                if use_live_rates:
                    # Use live rates from ticker.info for current valuations
                    logger.info("Using live exchange rates from ticker.info for current valuation")
                    for currency in currencies_needed:
                        if currency in ['GBP', 'GBp']:
                            continue
                        live_rate = self.get_current_exchange_rate(currency, 'GBP')
                        # Create a Series with the live rate for all dates
                        exchange_rates[currency] = pd.Series([live_rate] * len(data.index), index=data.index)
                        logger.info(f"  {currency}/GBP live rate: {live_rate:.6f}")
                elif currencies_needed:
                    logger.debug(f"Fetching exchange rates for currencies: {currencies_needed}")
                    for currency in currencies_needed:
                        if currency in ['GBP', 'GBp']:
                            # Skip GBP to GBP conversion
                            continue
                        pair_symbol = f"{currency}GBP=X"
                        try:
                            logger.debug(f"Requesting {pair_symbol} from {buffer_start_date} to {buffer_end_date}")
                            rate_data = yf.download(pair_symbol, start=buffer_start_date, end=buffer_end_date, progress=False)
                            if not rate_data.empty:
                                exchange_rates[currency] = rate_data['Close']
                                logger.debug(f"Got {currency}/GBP exchange rate data: {len(rate_data)} points")
                                logger.debug(f"  Returned date range: {rate_data.index[0]} to {rate_data.index[-1]}")
                                # Log last 3 rates (extract scalar value carefully)
                                for idx in rate_data.index[-3:]:
                                    rate_val = rate_data.loc[idx, 'Close']
                                    # Handle both scalar and Series return types
                                    if hasattr(rate_val, 'iloc'):
                                        rate_val = rate_val.iloc[0]
                                    logger.debug(f"    {idx.date()}: {float(rate_val):.6f}")
                            else:
                                # Try two-step conversion via USD if direct pair doesn't exist
                                logger.warning(f"No direct {currency}/GBP data, trying two-step conversion via USD")
                                try:
                                    usd_pair = f"{currency}USD=X"
                                    gbp_pair = "USDGBP=X"

                                    usd_data = yf.download(usd_pair, start=buffer_start_date, end=buffer_end_date, progress=False)
                                    gbp_data = yf.download(gbp_pair, start=buffer_start_date, end=buffer_end_date, progress=False)

                                    if not usd_data.empty and not gbp_data.empty:
                                        # Extract Close prices, handling multi-level columns
                                        usd_close = usd_data['Close']
                                        gbp_close = gbp_data['Close']

                                        # Handle multi-level columns (when downloading single ticker, YF may return multi-level)
                                        if hasattr(usd_close, 'columns'):
                                            usd_close = usd_close.iloc[:, 0]
                                        if hasattr(gbp_close, 'columns'):
                                            gbp_close = gbp_close.iloc[:, 0]

                                        # Multiply the two rates: CZK/USD * USD/GBP = CZK/GBP
                                        # Align the indices
                                        combined_rate = usd_close * gbp_close.reindex(usd_close.index, method='ffill')
                                        exchange_rates[currency] = combined_rate
                                        logger.debug(f"Got {currency}/GBP via USD conversion: {len(combined_rate)} points")
                                    else:
                                        logger.warning(f"Two-step conversion failed for {currency}, using 1.0")
                                        exchange_rates[currency] = pd.Series([1.0], index=[buffer_end_date])
                                except Exception as e2:
                                    logger.warning(f"Two-step conversion failed for {currency}: {e2}")
                                    exchange_rates[currency] = pd.Series([1.0], index=[buffer_end_date])
                        except Exception as e:
                            logger.warning(f"Error fetching exchange rate for {currency}: {e}")
                            exchange_rates[currency] = pd.Series([1.0], index=[buffer_end_date])

                # Step 4: Process each ticker and convert to GBP
                for ticker in uncached_tickers:
                    currency = ticker_info[ticker].get('currency', 'USD')

                    # Extract price data for this ticker
                    if len(uncached_tickers) == 1:
                        # Single ticker case
                        if data.empty:
                            # No historical data - try to use live price from ticker.info
                            logger.warning(f"No historical data from yf.download() for {ticker}, trying ticker.info")
                            live_price = ticker_info[ticker].get('regularMarketPrice')
                            if live_price:
                                # Convert to GBP if needed
                                if currency not in ['GBP', 'GBp']:
                                    if use_live_rates:
                                        exchange_rate = self.get_current_exchange_rate(currency, 'GBP')
                                    elif currency in exchange_rates:
                                        # Use most recent exchange rate from historical data
                                        exchange_rate = float(exchange_rates[currency].iloc[-1])
                                    else:
                                        logger.warning(f"No exchange rate available for {currency}, using 1:1")
                                        exchange_rate = 1.0
                                    live_price = live_price * exchange_rate
                                    logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.4f} {currency} = £{live_price:.4f}")
                                    currency = 'GBP'  # Mark as converted to avoid double conversion
                                elif currency == 'GBp':
                                    live_price = live_price / 100
                                    logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.2f}p = £{live_price:.4f}")
                                    currency = 'GBP'  # Mark as converted to avoid double conversion
                                else:
                                    logger.info(f"Using live price from ticker.info for {ticker}: £{live_price:.4f}")
                                # Create single-row DataFrame with today's price
                                df = pd.DataFrame({'Close': [live_price]}, index=[end_date])
                            else:
                                logger.warning(f"No live price available for {ticker} in ticker.info")
                                self.price_cache[ticker] = pd.DataFrame()
                                continue
                        else:
                            close_prices = data['Close'].squeeze()
                            volume = data['Volume'].squeeze()
                            df = pd.DataFrame({'Close': close_prices})
                    else:
                        # Multi-ticker case
                        if ticker in data['Close'].columns:
                            close_prices = data['Close'][ticker].squeeze()
                            volume = data['Volume'][ticker].squeeze()
                            df = pd.DataFrame({'Close': close_prices})
                        else:
                            # No historical data - try to use live price from ticker.info
                            logger.warning(f"No historical data from yf.download() for {ticker}, trying ticker.info")
                            live_price = ticker_info[ticker].get('regularMarketPrice')
                            if live_price:
                                # Convert to GBP if needed
                                if currency not in ['GBP', 'GBp']:
                                    if use_live_rates:
                                        exchange_rate = self.get_current_exchange_rate(currency, 'GBP')
                                    elif currency in exchange_rates:
                                        # Use most recent exchange rate from historical data
                                        exchange_rate = float(exchange_rates[currency].iloc[-1])
                                    else:
                                        logger.warning(f"No exchange rate available for {currency}, using 1:1")
                                        exchange_rate = 1.0
                                    live_price = live_price * exchange_rate
                                    logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.4f} {currency} = £{live_price:.4f}")
                                    currency = 'GBP'  # Mark as converted to avoid double conversion
                                elif currency == 'GBp':
                                    live_price = live_price / 100
                                    logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.2f}p = £{live_price:.4f}")
                                    currency = 'GBP'  # Mark as converted to avoid double conversion
                                else:
                                    logger.info(f"Using live price from ticker.info for {ticker}: £{live_price:.4f}")
                                # Create single-row DataFrame with today's price
                                df = pd.DataFrame({'Close': [live_price]}, index=[end_date])
                            else:
                                logger.warning(f"No live price available for {ticker} in ticker.info")
                                self.price_cache[ticker] = pd.DataFrame()
                                continue

                    # Filter out outliers: single-day spikes that are implausible
                    # Yahoo Finance sometimes returns bad data with huge spikes (e.g., VWRL.L Oct 6)
                    # Strategy: Remove any row where price differs >20% from both previous AND next day
                    # (requires price to be surrounded by "normal" values to be suspicious)
                    initial_rows = len(df)
                    filtered_indices = []

                    logger.info(f"Spike filter: Checking {ticker} ({initial_rows} rows from {df.index[0].date() if len(df) > 0 else 'N/A'} to {df.index[-1].date() if len(df) > 0 else 'N/A'})")

                    # Build a list of valid (non-NaN) price indices
                    valid_indices = [i for i in range(len(df)) if pd.notna(df.iloc[i]['Close'])]

                    # Check each valid price point against its neighbors
                    for valid_idx in range(1, len(valid_indices) - 1):
                        i = valid_indices[valid_idx]  # Current row index
                        prev_i = valid_indices[valid_idx - 1]  # Previous valid row
                        next_i = valid_indices[valid_idx + 1]  # Next valid row

                        prev_price = df.iloc[prev_i]['Close']
                        curr_price = df.iloc[i]['Close']
                        next_price = df.iloc[next_i]['Close']

                        # All three should be valid (we filtered for non-NaN), but double-check
                        if prev_price > 0 and curr_price > 0 and next_price > 0:
                            # Check if this is a V-shaped spike (reversal, not trend)
                            # Pattern: price goes up then down, or down then up
                            # AND the magnitude is >20% in both directions

                            prev_diff = abs(curr_price - prev_price) / prev_price
                            next_diff = abs(curr_price - next_price) / next_price

                            # Check if it's a reversal (price movement changes direction)
                            went_up = curr_price > prev_price
                            goes_down = next_price < curr_price
                            went_down = curr_price < prev_price
                            goes_up = next_price > curr_price

                            is_reversal = (went_up and goes_down) or (went_down and goes_up)

                            if is_reversal and prev_diff > 0.20 and next_diff > 0.20:
                                # This is a V-shaped spike - probably bad data
                                filtered_indices.append(i)
                                direction = "up-then-down" if went_up else "down-then-up"
                                logger.info(f"Filtering suspicious {direction} spike for {ticker} at {df.index[i].date()}: "
                                          f"prev={prev_price:.2f}, curr={curr_price:.2f}, next={next_price:.2f}")

                    # Remove filtered indices
                    if filtered_indices:
                        df = df.drop(df.index[filtered_indices])
                        logger.info(f"Filtered out {len(filtered_indices)} suspicious price spikes for {ticker} (kept {len(df)}/{initial_rows} rows)")

                    # Handle UK stock price transitions for both GBP and GBp
                    # This handles all permutations: YF might say GBP but have pence data,
                    # or say GBp but have pounds data, or transition mid-stream
                    if currency in ['GBP', 'GBp']:
                        df = self._handle_uk_stock_transitions(ticker, df, currency)

                    # Convert to GBP if needed
                    if currency not in ['GBP', 'GBp']:
                        if currency in exchange_rates:
                            # Convert prices to GBP using exchange rates
                            gbp_prices = self._convert_prices_to_gbp(df['Close'], exchange_rates[currency], df.index)
                            df['Close'] = gbp_prices
                            logger.debug(f"Converted {ticker} prices from {currency} to GBP")
                        else:
                            logger.warning(f"No exchange rate available for {currency}, using 1:1 conversion")

                    # Check if we have any valid (non-NaN) price data
                    # If not, fall back to ticker.info
                    if df.empty or df['Close'].isna().all():
                        logger.warning(f"All price data is NaN for {ticker}, falling back to ticker.info")
                        live_price = ticker_info[ticker].get('regularMarketPrice')
                        if live_price:
                            # Convert to GBP if needed
                            if currency not in ['GBP', 'GBp']:
                                if use_live_rates:
                                    exchange_rate = self.get_current_exchange_rate(currency, 'GBP')
                                elif currency in exchange_rates:
                                    # Use most recent exchange rate from historical data
                                    exchange_rate = float(exchange_rates[currency].iloc[-1])
                                else:
                                    logger.warning(f"No exchange rate available for {currency}, using 1:1")
                                    exchange_rate = 1.0
                                live_price = live_price * exchange_rate
                                logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.4f} {currency} = £{live_price:.4f}")
                                currency = 'GBP'  # Mark as converted to avoid double conversion
                            elif currency == 'GBp':
                                live_price = live_price / 100
                                logger.info(f"Using live price from ticker.info for {ticker}: {ticker_info[ticker].get('regularMarketPrice'):.2f}p = £{live_price:.4f}")
                                currency = 'GBP'  # Mark as converted to avoid double conversion
                            else:
                                logger.info(f"Using live price from ticker.info for {ticker}: £{live_price:.4f}")
                            df = pd.DataFrame({'Close': [live_price]}, index=[end_date])
                        else:
                            logger.warning(f"No live price available for {ticker} in ticker.info")
                            df = pd.DataFrame()  # Empty DataFrame

                    # Store in cache
                    self.price_cache[ticker] = df
                    logger.debug(f"Cached price data for {ticker}: {len(df)} points")

            except RuntimeError as e:
                # Re-raise RuntimeError from ticker info failures - these are fatal
                logger.error(f"Fatal error fetching ticker information: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Error fetching prices for {uncached_tickers}: {str(e)}")
                logger.exception("Full traceback:")
                # Initialize empty DataFrames for failed tickers
                for ticker in uncached_tickers:
                    self.price_cache[ticker] = pd.DataFrame()

        return {ticker: self.price_cache[ticker] for ticker in tickers}

    def _handle_uk_stock_transitions(self, ticker: str, df: pd.DataFrame, currency: str) -> pd.DataFrame:
        """Handle UK stock price transitions between pence and pounds.

        Detects 80x+ price changes in either direction and uses the currency field
        to determine which prices need conversion.

        Args:
            ticker: Stock ticker symbol
            df: DataFrame with price data
            currency: Currency from Yahoo Finance ('GBP' or 'GBp')

        Returns:
            DataFrame with normalized prices
        """
        # Sort by date to ensure chronological order
        df = df.sort_index()

        # Look for price transitions in EITHER direction (80x change)
        last_valid_price = None
        transition_index = None
        transition_direction = None  # 'pence_to_pounds' or 'pounds_to_pence'

        for i in range(len(df)):
            price_value = df['Close'].iloc[i]
            current_price = price_value.item() if hasattr(price_value, 'item') else price_value
            if pd.isna(current_price):
                logger.debug(f"Skipping NaN price at {df.index[i]}")
                continue

            if last_valid_price is not None:
                # Check for transition in EITHER direction
                if last_valid_price > current_price * 80:
                    # Price dropped by >80x: pence -> pounds
                    logger.warning(f"Detected pence->pounds transition in {ticker} at {df.index[i]}: {last_valid_price} -> {current_price}")
                    transition_index = i
                    transition_direction = 'pence_to_pounds'
                    break
                elif current_price > last_valid_price * 80:
                    # Price increased by >80x: pounds -> pence
                    logger.warning(f"Detected pounds->pence transition in {ticker} at {df.index[i]}: {last_valid_price} -> {current_price}")
                    transition_index = i
                    transition_direction = 'pounds_to_pence'
                    break
                else:
                    logger.debug(f"No price transition in {ticker} at {df.index[i]}: {last_valid_price} -> {current_price}")

            last_valid_price = current_price

        # Handle transition if found, or convert all if currency is GBp
        if transition_index is not None:
            # We always want final prices in pounds (GBP), regardless of what YF claims
            # The transition direction tells us which prices need conversion
            if transition_direction == 'pence_to_pounds':
                # Earlier prices are in pence, later are in pounds
                logger.warning(f"Converting {ticker} prices before {df.index[transition_index]} from pence to pounds (dividing by 100)")
                df.loc[:df.index[transition_index-1], 'Close'] /= 100
            else:  # pounds_to_pence
                # Earlier prices are in pounds, later are in pence
                logger.warning(f"Converting {ticker} prices from {df.index[transition_index]} onwards from pence to pounds (dividing by 100)")
                df.loc[df.index[transition_index]:, 'Close'] /= 100
        elif currency == 'GBp':
            # No transition found, but YF says currency is GBp (pence)
            # Convert all prices to pounds
            logger.debug(f"No transition found for {ticker}, currency={currency}, converting all prices to GBP (dividing by 100)")
            df['Close'] = df['Close'] / 100
        # else: No transition and currency='GBP' - prices are already in pounds, leave as-is

        return df

    def _convert_prices_to_gbp(self, prices: pd.Series, exchange_rates: pd.Series, price_dates: pd.DatetimeIndex) -> pd.Series:
        """Convert prices to GBP using exchange rates."""
        # Align exchange rates with price dates
        gbp_prices = pd.Series(index=price_dates, dtype=float)

        # Normalize both indices to date-only (ignore time/timezone) for matching
        # Stock prices and exchange rates may have different timezones
        price_dates_normalized = pd.DatetimeIndex([pd.Timestamp(d.date()) for d in price_dates])
        rate_dates_normalized = pd.DatetimeIndex([pd.Timestamp(d.date()) for d in exchange_rates.index])

        # Create a mapping from normalized date to exchange rate
        rate_by_date = {}
        for i, norm_date in enumerate(rate_dates_normalized):
            rate_value = exchange_rates.iloc[i]
            rate = float(rate_value.iloc[0] if isinstance(rate_value, pd.Series) else rate_value)
            rate_by_date[norm_date] = rate

        # Debug: Show last 3 rates in the mapping
        if rate_by_date:
            sorted_dates = sorted(rate_by_date.keys())
            logger.debug(f"  Exchange rate mapping (last 3):")
            for d in sorted_dates[-3:]:
                logger.debug(f"    {d.date()}: {rate_by_date[d]:.6f}")

        # For current valuations, use the most recent rate available
        # (YF may publish finalized rates under next day's date)
        most_recent_rate_date = max(rate_by_date.keys())
        most_recent_rate = rate_by_date[most_recent_rate_date]

        for i, date in enumerate(price_dates):
            norm_date = price_dates_normalized[i]

            # Find the closest exchange rate date (forward fill by date only)
            available_dates = [d for d in rate_by_date.keys() if d <= norm_date]

            if available_dates:
                closest_date = max(available_dates)
                rate = rate_by_date[closest_date]
            else:
                # Date is before all available rates - use earliest
                rate = rate_by_date[min(rate_by_date.keys())]

            # Special case: if this is the last (most recent) price date and there's a newer rate available,
            # use the most recent rate (handles YF publishing finalized rates under next day)
            if i == len(price_dates) - 1 and most_recent_rate_date > norm_date:
                logger.debug(f"  Using most recent rate for current valuation: {most_recent_rate:.6f} from {most_recent_rate_date.date()}")
                rate = most_recent_rate

            gbp_prices[date] = prices[date] * rate

            # Debug log for first and last conversions
            if i == 0 or i == len(price_dates) - 1:
                logger.debug(f"  {date.date()}: price={prices[date]:.2f} * rate={rate:.6f} = £{gbp_prices[date]:.2f}")

        return gbp_prices
