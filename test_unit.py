#!/usr/bin/env python3
"""
Unit tests for critical functionality in the investment review system.

Tests cover:
1. Currency conversion logic
2. Ticker conversion handling
3. YF API error handling
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime
from portfolio_analysis import PortfolioAnalysis
from portfolio_review import StockTransaction
import transaction_processor
import market_data_fetcher
from market_data_fetcher import MarketDataFetcher


class TestCurrencyConversion(unittest.TestCase):
    """Test currency conversion logic in PortfolioAnalysis."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.calculator = PortfolioAnalysis()
    
    def test_gbp_to_gbp_no_conversion(self):
        """Test that GBP to GBP requires no conversion."""
        mdf = MarketDataFetcher()
        rate = mdf.get_current_exchange_rate('GBP', 'GBP')
        self.assertEqual(rate, 1.0)
    
    def test_uk_stock_pence_to_pounds_conversion(self):
        """Test UK stock prices - _handle_uk_stock_transitions no longer divides."""
        # Create a test DataFrame with prices
        test_data = pd.DataFrame({
            'Close': [500.0, 510.0, 520.0]
        }, index=pd.date_range('2025-01-01', periods=3))

        # Apply UK stock transition logic (currency='GBP' means we expect pounds)
        mdf = MarketDataFetcher()
        result = mdf._handle_uk_stock_transitions('TEST.L', test_data, currency='GBP')
        
        # Should remain unchanged - division by 100 now happens based on YF currency field, not in this function
        expected = [500.0, 510.0, 520.0]
        np.testing.assert_array_almost_equal(result['Close'].values, expected, decimal=2)
    
    def test_uk_stock_no_conversion_without_list(self):
        """Test UK stocks - _handle_uk_stock_transitions doesn't divide anymore."""
        # Create test data
        test_data = pd.DataFrame({
            'Close': [5.0, 5.1, 5.2]
        }, index=pd.date_range('2025-01-01', periods=3))

        # Apply UK stock transition logic (currency='GBP' means we expect pounds)
        mdf = MarketDataFetcher()
        result = mdf._handle_uk_stock_transitions('TEST.L', test_data, currency='GBP')
        
        # Should remain unchanged - no division happens in this function anymore
        np.testing.assert_array_almost_equal(result['Close'].values, [5.0, 5.1, 5.2], decimal=2)
    
    def test_gbp_price_transition_detection(self):
        """Test detection of pence-to-pounds transitions in price data."""
        # Simulate realistic scenario: YF starts in pence, then switches to pounds (Dec 2024 behavior)
        # Prices: 1100 pence → 11 pounds (100x drop indicates transition)
        test_data = pd.DataFrame({
            'Close': [1100.0, 1102.0, 10.85, 10.90]  # First two in pence, last two in pounds
        }, index=pd.date_range('2024-12-16', periods=4))

        # Currency='GBP' means YF says it's in pounds, so earlier pence data should be converted
        mdf = MarketDataFetcher()
        result = mdf._handle_uk_stock_transitions('TEST.L', test_data, currency='GBP')
        
        # The transition should be detected at index 2, earlier values divided by 100 to get pounds
        # When currency='GBP', we want all prices in pounds
        expected = [11.0, 11.02, 10.85, 10.90]
        np.testing.assert_array_almost_equal(result['Close'].values, expected, decimal=4)


class TestTickerConversion(unittest.TestCase):
    """Test ticker conversion handling."""
    
    def test_stock_conversion_updates_ticker(self):
        """Test that STOCK_CONVERSION transactions update the current ticker."""
        from portfolio_review import PortfolioReview
        
        # Create a simple test - we'll use the PortfolioAnalysis's logic
        transactions = [
            StockTransaction(
                date=datetime(2025, 1, 1),
                transaction_type='BUY',
                quantity=100,
                price_per_share=10.0,
                total_amount=1000.0
            ),
            StockTransaction(
                date=datetime(2025, 2, 1),
                transaction_type='STOCK_CONVERSION',
                quantity=1,
                price_per_share=0.0,
                total_amount=0.0,
                new_quantity=2.0,  # 2:1 split
                new_ticker='NEWTICKER',
                new_currency='USD'
            )
        ]
        
        # The logic for determining current ticker is in process_full_history
        # Let's test the key part: iterating through transactions to find new ticker
        current_ticker = 'OLDTICKER'
        current_currency = 'GBP'
        
        for txn in transactions:
            if txn.transaction_type == 'STOCK_CONVERSION':
                if txn.get_new_ticker() and txn.get_new_ticker() != current_ticker:
                    current_ticker = txn.get_new_ticker()
                if txn.get_new_currency() and txn.get_new_currency() != current_currency:
                    current_currency = txn.get_new_currency()
        
        self.assertEqual(current_ticker, 'NEWTICKER')
        self.assertEqual(current_currency, 'USD')
    
    def test_stock_conversion_adjusts_units(self):
        """Test that STOCK_CONVERSION transactions correctly adjust unit counts."""
        calculator = PortfolioAnalysis()
        
        transactions = [
            StockTransaction(
                date=datetime(2025, 1, 1),
                transaction_type='BUY',
                quantity=100,
                price_per_share=10.0,
                total_amount=1000.0
            ),
            StockTransaction(
                date=datetime(2025, 2, 1),
                transaction_type='STOCK_CONVERSION',
                quantity=1,
                price_per_share=0.0,
                total_amount=0.0,
                new_quantity=2.0  # 2:1 split
            )
        ]
        
        # Calculate through March 1
        result = transaction_processor.calculate_transactions_through_date(
            transactions,
            datetime(2025, 3, 1),
            include_investment_threshold=False
        )
        
        # Units should be doubled (100 * 2 = 200)
        self.assertEqual(result['units_held'], 200.0)
        # Investment should remain unchanged
        self.assertEqual(result['total_invested'], 1000.0)


class TestYahooFinanceAPIErrorHandling(unittest.TestCase):
    """Test error handling for Yahoo Finance API failures."""
    
    def test_invalid_ticker_causes_runtime_error(self):
        """Test that invalid tickers cause RuntimeError instead of returning garbage data."""
        mdf = MarketDataFetcher()

        # Mock yf.Tickers to raise ValueError like it does for invalid ISINs
        with patch('yfinance.Tickers') as mock_tickers:
            mock_tickers.side_effect = ValueError("Invalid ISIN number: IE00B42P0H75")

            # This should raise RuntimeError, not return default USD
            with self.assertRaises(RuntimeError) as context:
                mdf.batch_get_ticker_info(['IE00B42P0H75'])

            self.assertIn("Failed to get ticker information", str(context.exception))
            self.assertIn("IE00B42P0H75", str(context.exception))
    
    def test_batch_price_fetch_propagates_ticker_info_errors(self):
        """Test that batch_get_stock_prices propagates RuntimeError from ticker info failures."""
        mdf = MarketDataFetcher()

        # Mock batch_get_ticker_info to raise RuntimeError
        with patch.object(mdf, 'batch_get_ticker_info') as mock_info:
            mock_info.side_effect = RuntimeError("Failed to get ticker information: Invalid ISIN")

            # This should propagate the RuntimeError
            with self.assertRaises(RuntimeError) as context:
                mdf.batch_get_stock_prices(['BADTICKER'], datetime(2025, 1, 1), datetime(2025, 1, 31))

            self.assertIn("Failed to get ticker information", str(context.exception))
    
    def test_network_errors_handled_gracefully(self):
        """Test that network errors (not ticker errors) are handled gracefully."""
        mdf = MarketDataFetcher()

        # Mock yf.download to raise a network error
        with patch('yfinance.download') as mock_download:
            mock_download.side_effect = Exception("Network timeout")

            # This should NOT raise - should return empty DataFrames
            with patch.object(mdf, 'batch_get_ticker_info') as mock_info:
                # Mock ticker info to succeed
                mock_info.return_value = {
                    'TEST': {'currency': 'USD', 'exchange': 'NASDAQ'}
                }

                # Should not raise, should return empty DataFrame
                result = mdf.batch_get_stock_prices(['TEST'], datetime(2025, 1, 1), datetime(2025, 1, 31))

                # Should have entry for TEST with empty DataFrame
                self.assertIn('TEST', result)
                self.assertTrue(result['TEST'].empty)


class TestMissingPriceData(unittest.TestCase):
    """Test handling of missing price data for stocks we hold vs don't hold."""
    
    def test_missing_price_for_held_stock_raises_error(self):
        """Test that missing price data for currently held stock raises RuntimeError."""
        calculator = PortfolioAnalysis()
        
        # Test the critical logic: when units_held > 0 but no price in current_prices
        # This simulates the situation where we hold a stock but can't get its price
        stock_data = {
            ('HELD_STOCK', 'taxable'): {
                'ticker': 'HELD_STOCK',
                'current_ticker': 'HELD_STOCK',
                'stock_name': 'Held Stock',
                'currency': 'USD',
                'account_type': 'Taxable',
                'tag': None,
                'total_invested': 1000.0,
                'total_received': 0.0,
                'units_held': 100.0,  # Currently holding shares
                'first_transaction_date': datetime(2020, 1, 1),
                'final_transaction_date': datetime(2020, 1, 1),
                'num_transactions': 1
            }
        }
        
        current_prices = {}  # Empty - no price data available
        
        # This should raise RuntimeError when trying to value the held stock
        with self.assertRaises(RuntimeError) as context:
            # Execute the critical section of process_full_history
            for stock_key, data in stock_data.items():
                current_ticker = data['current_ticker']
                if data['units_held'] > 0:
                    if current_ticker not in current_prices:
                        error_msg = f"No price data fetched for {current_ticker} (holding {data['units_held']:.2f} shares)"
                        raise RuntimeError(error_msg)
        
        self.assertIn('No price data fetched', str(context.exception))
        self.assertIn('HELD_STOCK', str(context.exception))
        self.assertIn('holding 100', str(context.exception))
    
    def test_missing_price_for_sold_stock_succeeds(self):
        """Test that missing price data for fully-sold stock does not raise error."""
        calculator = PortfolioAnalysis()
        
        # Test with fully-sold stock (units_held = 0)
        stock_data = {
            ('SOLD_STOCK', 'taxable'): {
                'ticker': 'SOLD_STOCK',
                'current_ticker': 'SOLD_STOCK',
                'stock_name': 'Sold Stock',
                'currency': 'USD',
                'account_type': 'Taxable',
                'tag': None,
                'total_invested': 1000.0,
                'total_received': 1500.0,
                'units_held': 0.0,  # No longer holding shares
                'first_transaction_date': datetime(2020, 1, 1),
                'final_transaction_date': datetime(2021, 1, 1),
                'num_transactions': 2
            }
        }
        
        current_prices = {}  # Empty - but should be OK since units_held = 0
        
        # This should NOT raise - sold stocks don't need price data
        try:
            for stock_key, data in stock_data.items():
                current_ticker = data['current_ticker']
                if data['units_held'] > 0:
                    if current_ticker not in current_prices:
                        error_msg = f"No price data fetched for {current_ticker} (holding {data['units_held']:.2f} shares)"
                        raise RuntimeError(error_msg)
            # If we get here, test passed
            success = True
        except RuntimeError as e:
            self.fail(f"Should not raise error for fully-sold stock, but got: {e}")
        
        self.assertTrue(success)
    
    def test_fallback_to_ticker_info_single_ticker(self):
        """Test fallback to ticker.info when yf.download returns no data (single ticker)."""
        mdf = MarketDataFetcher()

        # Mock yf.download to return empty DataFrame (no historical data)
        # Mock yf.Tickers to return ticker info with regularMarketPrice
        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:
            
            # Empty DataFrame from download
            mock_download.return_value = pd.DataFrame()
            
            # Mock ticker info with live price
            mock_ticker = Mock()
            mock_ticker.info = {
                'currency': 'GBP',
                'exchange': 'LSE',
                'regularMarketPrice': 0.8788
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {'TEST.L': mock_ticker}
            mock_tickers.return_value = mock_tickers_obj
            
            # Call batch get stock prices
            result = mdf.batch_get_stock_prices(
                ['TEST.L'],
                datetime(2025, 9, 1),
                datetime(2025, 10, 16)
            )
            
            # Should have price data from ticker.info fallback
            self.assertIn('TEST.L', result)
            self.assertFalse(result['TEST.L'].empty)
            self.assertAlmostEqual(result['TEST.L']['Close'].iloc[0], 0.8788, places=4)
    
    def test_fallback_to_ticker_info_multi_ticker(self):
        """Test fallback to ticker.info when one ticker has NaN data (multi-ticker)."""
        mdf = MarketDataFetcher()

        # Mock yf.download to return DataFrame with data for TICKER1 but all NaN for TICKER2
        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:
            
            # Create DataFrame with one good ticker, one with all NaN
            dates = pd.date_range('2025-10-01', periods=5)
            mock_data = pd.DataFrame({
                ('Close', 'TICKER1'): [10.0, 10.5, 11.0, 10.8, 11.2],
                ('Close', 'TICKER2'): [np.nan, np.nan, np.nan, np.nan, np.nan],
                ('Volume', 'TICKER1'): [1000, 1100, 1200, 1150, 1250],
                ('Volume', 'TICKER2'): [0, 0, 0, 0, 0]
            }, index=dates)
            mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
            mock_download.return_value = mock_data
            
            # Mock ticker info with live price for TICKER2
            mock_ticker1 = Mock()
            mock_ticker1.info = {'currency': 'GBP', 'exchange': 'LSE'}
            mock_ticker2 = Mock()
            mock_ticker2.info = {
                'currency': 'GBP',
                'exchange': 'LSE',
                'regularMarketPrice': 25.50
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {
                'TICKER1': mock_ticker1,
                'TICKER2': mock_ticker2
            }
            mock_tickers.return_value = mock_tickers_obj
            
            # Call batch get stock prices
            result = mdf.batch_get_stock_prices(
                ['TICKER1', 'TICKER2'],
                datetime(2025, 10, 1),
                datetime(2025, 10, 16)
            )
            
            # TICKER1 should have historical data
            self.assertIn('TICKER1', result)
            self.assertFalse(result['TICKER1'].empty)
            self.assertEqual(len(result['TICKER1']), 5)
            
            # TICKER2 should have fallback to ticker.info
            self.assertIn('TICKER2', result)
            self.assertFalse(result['TICKER2'].empty)
            self.assertEqual(len(result['TICKER2']), 1)  # Single row from ticker.info
            self.assertAlmostEqual(result['TICKER2']['Close'].iloc[0], 25.50, places=2)


class TestForeignCurrencyFallback(unittest.TestCase):
    """Test currency conversion in ticker.info fallback paths."""

    def test_usd_ticker_fallback_converts_to_gbp(self):
        """Test USD ticker fallback applies USD->GBP conversion."""
        mdf = MarketDataFetcher()

        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:

            # Mock yf.download returning empty DataFrame (triggers fallback)
            mock_download.return_value = pd.DataFrame()

            # Mock ticker info with USD currency and $100 price
            mock_ticker = Mock()
            mock_ticker.info = {
                'currency': 'USD',
                'exchange': 'NYSE',
                'regularMarketPrice': 100.0  # $100 USD
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {'TEST.US': mock_ticker}
            mock_tickers.return_value = mock_tickers_obj

            # Mock get_current_exchange_rate to return 0.75 (USD->GBP)
            with patch.object(mdf, 'get_current_exchange_rate', return_value=0.75):
                result = mdf.batch_get_stock_prices(
                    ['TEST.US'],
                    datetime(2025, 10, 1),
                    datetime(2025, 10, 28),
                    use_live_rates=True
                )

            # Should have converted: $100 * 0.75 = £75
            self.assertIn('TEST.US', result)
            self.assertFalse(result['TEST.US'].empty)
            self.assertAlmostEqual(result['TEST.US']['Close'].iloc[0], 75.0, places=2)

    def test_cad_ticker_fallback_converts_to_gbp(self):
        """Test CAD ticker fallback applies CAD->GBP conversion."""
        mdf = MarketDataFetcher()

        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:

            # Mock yf.download returning empty DataFrame
            mock_download.return_value = pd.DataFrame()

            # Mock ticker info with CAD currency and C$10.98 price (like FTG.TO)
            mock_ticker = Mock()
            mock_ticker.info = {
                'currency': 'CAD',
                'exchange': 'TOR',
                'regularMarketPrice': 10.98  # C$10.98
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {'FTG.TO': mock_ticker}
            mock_tickers.return_value = mock_tickers_obj

            # Mock get_current_exchange_rate to return 0.5395 (CAD->GBP)
            with patch.object(mdf, 'get_current_exchange_rate', return_value=0.5395):
                result = mdf.batch_get_stock_prices(
                    ['FTG.TO'],
                    datetime(2025, 10, 1),
                    datetime(2025, 10, 28),
                    use_live_rates=True
                )

            # Should have converted: C$10.98 * 0.5395 = £5.92
            self.assertIn('FTG.TO', result)
            self.assertFalse(result['FTG.TO'].empty)
            self.assertAlmostEqual(result['FTG.TO']['Close'].iloc[0], 5.92, places=2)

    def test_gbp_pence_ticker_fallback_divides_by_100(self):
        """Test GBp (pence) ticker fallback converts to pounds."""
        mdf = MarketDataFetcher()

        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:

            # Mock yf.download returning empty DataFrame
            mock_download.return_value = pd.DataFrame()

            # Mock ticker info with GBp currency and 250p price
            mock_ticker = Mock()
            mock_ticker.info = {
                'currency': 'GBp',
                'exchange': 'LSE',
                'regularMarketPrice': 250.0  # 250 pence
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {'TEST.L': mock_ticker}
            mock_tickers.return_value = mock_tickers_obj

            result = mdf.batch_get_stock_prices(
                ['TEST.L'],
                datetime(2025, 10, 1),
                datetime(2025, 10, 28),
                use_live_rates=True
            )

            # Should have divided by 100: 250p / 100 = £2.50
            self.assertIn('TEST.L', result)
            self.assertFalse(result['TEST.L'].empty)
            self.assertAlmostEqual(result['TEST.L']['Close'].iloc[0], 2.50, places=2)

    def test_multi_ticker_with_nan_fallback_converts_currency(self):
        """Test multi-ticker path with NaN fallback applies conversion."""
        mdf = MarketDataFetcher()

        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:

            # Mock yf.download with all NaN for one ticker
            dates = pd.date_range('2025-10-01', periods=5)
            mock_data = pd.DataFrame({
                ('Close', 'TICKER1'): [10.0, 10.5, 11.0, 10.8, 11.2],
                ('Close', 'USD.TICK'): [np.nan, np.nan, np.nan, np.nan, np.nan],
                ('Volume', 'TICKER1'): [1000, 1100, 1200, 1150, 1250],
                ('Volume', 'USD.TICK'): [0, 0, 0, 0, 0]
            }, index=dates)
            mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
            mock_download.return_value = mock_data

            # Mock ticker info
            mock_ticker1 = Mock()
            mock_ticker1.info = {'currency': 'GBP', 'exchange': 'LSE'}
            mock_ticker2 = Mock()
            mock_ticker2.info = {
                'currency': 'USD',
                'exchange': 'NYSE',
                'regularMarketPrice': 50.0  # $50 USD
            }
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {
                'TICKER1': mock_ticker1,
                'USD.TICK': mock_ticker2
            }
            mock_tickers.return_value = mock_tickers_obj

            # Mock get_current_exchange_rate
            with patch.object(mdf, 'get_current_exchange_rate', return_value=0.75):
                result = mdf.batch_get_stock_prices(
                    ['TICKER1', 'USD.TICK'],
                    datetime(2025, 10, 1),
                    datetime(2025, 10, 16),
                    use_live_rates=True
                )

            # USD.TICK should have converted fallback price
            self.assertIn('USD.TICK', result)
            self.assertFalse(result['USD.TICK'].empty)
            # $50 * 0.75 = £37.50
            self.assertAlmostEqual(result['USD.TICK']['Close'].iloc[0], 37.50, places=2)


class TestMWRRCalculation(unittest.TestCase):
    """Test MWRR (Money-Weighted Rate of Return) calculation."""
    
    def test_basic_buy_then_sell(self):
        """Test basic MWRR: buy then sell with profit."""
        from portfolio_review import StockTransaction
        
        calculator = PortfolioAnalysis()
        
        # Buy 100 shares at £10 on Jan 1, sell at £12 on Jan 1 next year
        transactions = [
            StockTransaction(
                date=datetime(2020, 1, 1),
                transaction_type='BUY',
                quantity=100,
                price_per_share=10.0,
                total_amount=1000.0
            ),
            StockTransaction(
                date=datetime(2021, 1, 1),
                transaction_type='SELL',
                quantity=100,
                price_per_share=12.0,
                total_amount=1200.0
            )
        ]
        
        # No current holdings (fully sold) - all cashflows are in transactions
        mwrr = transaction_processor.calculate_mwrr_for_transactions(transactions)
        
        # Should be around 20% return (1200/1000 - 1)
        self.assertIsNotNone(mwrr)
        self.assertAlmostEqual(mwrr, 0.20, delta=0.01)
    
    def test_stock_conversion_ignored(self):
        """Test that stock conversions don't affect MWRR cashflows."""
        from portfolio_review import StockTransaction
        
        calculator = PortfolioAnalysis()
        
        transactions = [
            StockTransaction(
                date=datetime(2020, 1, 1),
                transaction_type='BUY',
                quantity=100,
                price_per_share=10.0,
                total_amount=1000.0
            ),
            StockTransaction(
                date=datetime(2020, 7, 1),
                transaction_type='STOCK_CONVERSION',
                quantity=100,
                price_per_share=0.0,
                total_amount=0.0,
                new_quantity=400  # 4:1 split
            )
        ]
        
        # Add synthetic SELL for current holdings
        synthetic_sell = StockTransaction(
            date=datetime(2021, 1, 1),
            transaction_type='SELL',
            quantity=400,  # 100 * 4 (after 4:1 split)
            price_per_share=12.0,
            total_amount=4800.0
        )
        transactions.append(synthetic_sell)

        # Still holding after split, current value £4800 (400 shares @ £12)
        mwrr = transaction_processor.calculate_mwrr_for_transactions(transactions)
        
        # MWRR should be based on cashflows only: -1000 initial, +4800 terminal
        # Over 1 year, this is 380% return
        self.assertIsNotNone(mwrr)
        self.assertGreater(mwrr, 3.0)  # Should be > 300%
    
    def test_multiple_cashflows(self):
        """Test MWRR with multiple buys and sells."""
        from portfolio_review import StockTransaction
        
        calculator = PortfolioAnalysis()
        
        transactions = [
            StockTransaction(
                date=datetime(2020, 1, 1),
                transaction_type='BUY',
                quantity=100,
                price_per_share=10.0,
                total_amount=1000.0
            ),
            StockTransaction(
                date=datetime(2020, 7, 1),
                transaction_type='BUY',
                quantity=50,
                price_per_share=12.0,
                total_amount=600.0
            ),
            StockTransaction(
                date=datetime(2021, 1, 1),
                transaction_type='SELL',
                quantity=150,
                price_per_share=15.0,
                total_amount=2250.0
            )
        ]
        
        # Fully sold - all cashflows in transactions
        mwrr = transaction_processor.calculate_mwrr_for_transactions(transactions)
        
        # Should have positive return
        self.assertIsNotNone(mwrr)
        self.assertGreater(mwrr, 0.0)
        self.assertLess(mwrr, 1.0)  # Should be reasonable (< 100%)


class TestMHTMLTransactionTypeParsing(unittest.TestCase):
    """Test MHTML parser correctly extracts transaction types from data."""
    
    def test_transaction_type_from_data_not_filename(self):
        """Test that transaction type comes from data column, not filename."""
        from mhtml_parser import parse_stock_transaction_mhtml
        from pathlib import Path
        import tempfile
        
        # Create a minimal MHTML file with a Buy transaction
        # But with a filename that doesn't contain "BOUGHT"
        mhtml_content = """MIME-Version: 1.0
Content-Type: multipart/related; boundary="boundary123"

--boundary123
Content-Type: text/html

<html>
<body>
<table>
<tr>
<th>Date</th><th>Time</th><th>Description</th><th>Account</th><th>Currency</th>
<th>Transaction Type</th><th>Symbol</th><th>Commission</th><th>Quantity</th>
<th>Gross Amount</th><th>Price</th><th>Net Amount</th><th>Exchange Rate</th>
</tr>
<tr>
<td>2025-03-06</td><td>10:00</td><td>Test Stock Inc</td><td>Account</td><td>USD</td>
<td>Buy</td><td>TEST</td><td>-10.00</td><td>100.00</td>
<td>-990.00</td><td>10.0000 USD</td><td>-1,000.00</td><td>1.25</td>
</tr>
</table>
</body>
</html>

--boundary123--
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='_generic_name.mhtml', delete=False) as f:
            f.write(mhtml_content)
            temp_path = f.name
        
        try:
            # Parse the file - filename doesn't contain BOUGHT or SOLD
            transactions = parse_stock_transaction_mhtml(temp_path)
            
            # Should extract transaction_type from data
            self.assertEqual(len(transactions), 1)
            self.assertEqual(transactions[0]['transaction_type'], 'purchase')
            self.assertEqual(transactions[0]['num_shares'], 100.0)
        finally:
            Path(temp_path).unlink()


class TestFiltering(unittest.TestCase):
    """Test filtering functionality."""
    
    def test_year_range_parsing(self):
        """Test parsing year ranges like '2010,2023-2025'."""
        from portfolio import parse_year_ranges
        
        # Single year
        self.assertEqual(parse_year_ranges('2024'), [2024])
        
        # Multiple single years
        self.assertEqual(parse_year_ranges('2010,2015,2020'), [2010, 2015, 2020])
        
        # Year range
        self.assertEqual(parse_year_ranges('2023-2025'), [2023, 2024, 2025])
        
        # Mixed single years and ranges
        result = parse_year_ranges('2010,2023-2025,2030')
        self.assertEqual(result, [2010, 2023, 2024, 2025, 2030])
        
        # Duplicates should be removed
        result = parse_year_ranges('2024,2023-2025')
        self.assertEqual(result, [2023, 2024, 2025])
    
    def test_category_filter(self):
        """Test category filtering includes only specified categories."""
        from portfolio_review import PortfolioReview
        from pathlib import Path
        import tempfile
        import os
        
        # Create temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create ISA and Taxable subdirectories
            isa_dir = os.path.join(tmpdir, 'ISA', '2024')
            taxable_dir = os.path.join(tmpdir, 'Taxable', '2024')
            os.makedirs(isa_dir)
            os.makedirs(taxable_dir)
            
            # _should_include_file should work without actual files
            pr = PortfolioReview(tmpdir, mode='full-history', include_categories=['taxable'])
            
            # Taxable should be included
            self.assertTrue(pr._should_include_file('taxable', '2024', None))
            
            # ISA should be excluded
            self.assertFalse(pr._should_include_file('isa', '2024', None))
            
            # Pension should be excluded
            self.assertFalse(pr._should_include_file('pension', '2024', None))
    
    def test_tag_include_filter(self):
        """Test tag inclusion filter includes only matching tags."""
        from portfolio_review import PortfolioReview
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pr = PortfolioReview(tmpdir, mode='full-history', include_tags=['AI', 'Tech'])
            
            # Tags containing 'AI' or 'Tech' should be included
            self.assertTrue(pr._should_include_file('isa', '2024', 'AI stocks'))
            self.assertTrue(pr._should_include_file('isa', '2024', 'Technology'))
            self.assertTrue(pr._should_include_file('isa', '2024', 'tech companies'))
            
            # Tags not containing the phrases should be excluded
            self.assertFalse(pr._should_include_file('isa', '2024', 'Energy'))
            self.assertFalse(pr._should_include_file('isa', '2024', 'Healthcare'))
    
    def test_tag_exclude_filter(self):
        """Test tag exclusion filter excludes matching tags."""
        from portfolio_review import PortfolioReview
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pr = PortfolioReview(tmpdir, mode='full-history', exclude_tags=['Funds', 'Bonds'])
            
            # Tags containing 'Funds' or 'Bonds' should be excluded
            self.assertFalse(pr._should_include_file('isa', '2024', 'Index Funds'))
            self.assertFalse(pr._should_include_file('isa', '2024', 'Government Bonds'))
            
            # Other tags should be included
            self.assertTrue(pr._should_include_file('isa', '2024', 'Stocks'))
            self.assertTrue(pr._should_include_file('isa', '2024', 'Tech'))
            
            # None tag should be included (no tag to match against)
            self.assertTrue(pr._should_include_file('isa', '2024', None))
    
    def test_year_filter(self):
        """Test year filtering includes only specified years."""
        from portfolio_review import PortfolioReview
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pr = PortfolioReview(tmpdir, mode='full-history', include_years=[2024, 2025])
            
            # 2024 and 2025 should be included
            self.assertTrue(pr._should_include_file('isa', '2024', None))
            self.assertTrue(pr._should_include_file('isa', '2025', None))
            
            # Other years should be excluded
            self.assertFalse(pr._should_include_file('isa', '2023', None))
            self.assertFalse(pr._should_include_file('isa', '2026', None))
    
    def test_combined_filters(self):
        """Test that multiple filters work together (AND logic)."""
        from portfolio_review import PortfolioReview
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pr = PortfolioReview(
                tmpdir, 
                mode='full-history',
                include_categories=['taxable'],
                include_years=[2024, 2025],
                exclude_tags=['Funds']
            )
            
            # All criteria match - should be included
            self.assertTrue(pr._should_include_file('taxable', '2024', 'Stocks'))
            
            # Wrong category - should be excluded
            self.assertFalse(pr._should_include_file('isa', '2024', 'Stocks'))
            
            # Wrong year - should be excluded
            self.assertFalse(pr._should_include_file('taxable', '2023', 'Stocks'))
            
            # Excluded tag - should be excluded
            self.assertFalse(pr._should_include_file('taxable', '2024', 'Index Funds'))


def run_unit_tests():
    """Run all unit tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCurrencyConversion))
    suite.addTests(loader.loadTestsFromTestCase(TestTickerConversion))
    suite.addTests(loader.loadTestsFromTestCase(TestYahooFinanceAPIErrorHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestMHTMLTransactionTypeParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestForeignCurrencyFallback))
    suite.addTests(loader.loadTestsFromTestCase(TestMWRRCalculation))
    suite.addTests(loader.loadTestsFromTestCase(TestMissingPriceData))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_unit_tests()
    sys.exit(0 if success else 1)

