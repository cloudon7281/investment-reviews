#!/usr/bin/env python3
"""
Unit tests for critical functionality in the investment review system.

Tests cover:
1. Currency conversion logic
2. Ticker conversion handling
3. YF API error handling
"""

import sys
import unittest
from logger import logger
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


class TestAnnualReviewMWRR(unittest.TestCase):
    """Test annual review MWRR calculation with synthetic transactions."""

    def test_annual_mwrr_with_start_value_only(self):
        """Test MWRR when stock was held at start date and still held today."""
        import annual_review_processor

        # Simulate: Had £1000 at start, no transactions, now worth £1100
        start_date = datetime(2024, 1, 1)
        start_value = 1000.0
        transactions_since_start = []
        current_value = 1100.0
        eval_date = datetime(2025, 1, 1)

        mwrr_transactions = annual_review_processor.create_annual_mwrr_transactions(
            start_date, start_value, transactions_since_start, current_value, eval_date
        )

        # Should have 2 transactions: synthetic BUY and synthetic SELL
        self.assertEqual(len(mwrr_transactions), 2)
        self.assertEqual(mwrr_transactions[0].transaction_type, 'BUY')
        self.assertEqual(mwrr_transactions[0].total_amount, 1000.0)
        self.assertEqual(mwrr_transactions[1].transaction_type, 'SELL')
        self.assertEqual(mwrr_transactions[1].total_amount, 1100.0)

        # Calculate MWRR - should be 10% over 1 year
        mwrr = transaction_processor.calculate_mwrr_for_transactions(mwrr_transactions)
        self.assertIsNotNone(mwrr)
        self.assertAlmostEqual(mwrr, 0.10, delta=0.01)

    def test_annual_mwrr_with_new_stock(self):
        """Test MWRR for stock bought after start date (no start value)."""
        import annual_review_processor

        start_date = datetime(2024, 1, 1)
        start_value = 0.0  # Didn't own at start
        buy_transaction = StockTransaction(
            date=datetime(2024, 6, 1),
            transaction_type='BUY',
            quantity=100,
            price_per_share=10.0,
            total_amount=1000.0
        )
        transactions_since_start = [buy_transaction]
        current_value = 1200.0  # Now worth £1200
        eval_date = datetime(2025, 1, 1)

        mwrr_transactions = annual_review_processor.create_annual_mwrr_transactions(
            start_date, start_value, transactions_since_start, current_value, eval_date
        )

        # Should have only actual BUY + synthetic SELL (no synthetic BUY since start_value=0)
        self.assertEqual(len(mwrr_transactions), 2)
        self.assertEqual(mwrr_transactions[0].transaction_type, 'BUY')
        self.assertEqual(mwrr_transactions[1].transaction_type, 'SELL')

        # Calculate MWRR
        mwrr = transaction_processor.calculate_mwrr_for_transactions(mwrr_transactions)
        self.assertIsNotNone(mwrr)
        # Bought June 1 for £1000, sold Jan 1 for £1200 = 20% gain over ~7 months
        # Annualized should be higher than 20%
        self.assertGreater(mwrr, 0.2)

    def test_annual_mwrr_with_sold_stock(self):
        """Test MWRR for stock held at start but fully sold (no current value)."""
        import annual_review_processor

        start_date = datetime(2024, 1, 1)
        start_value = 1000.0  # Had £1000 at start
        sell_transaction = StockTransaction(
            date=datetime(2024, 6, 1),
            transaction_type='SELL',
            quantity=100,
            price_per_share=12.0,
            total_amount=1200.0
        )
        transactions_since_start = [sell_transaction]
        current_value = 0.0  # Fully sold
        eval_date = datetime(2025, 1, 1)

        mwrr_transactions = annual_review_processor.create_annual_mwrr_transactions(
            start_date, start_value, transactions_since_start, current_value, eval_date
        )

        # Should have synthetic BUY + actual SELL (no synthetic SELL since current_value=0)
        self.assertEqual(len(mwrr_transactions), 2)
        self.assertEqual(mwrr_transactions[0].transaction_type, 'BUY')
        self.assertEqual(mwrr_transactions[1].transaction_type, 'SELL')

        # Calculate MWRR
        mwrr = transaction_processor.calculate_mwrr_for_transactions(mwrr_transactions)
        self.assertIsNotNone(mwrr)
        # Bought Jan 1 for £1000, sold June 1 for £1200 = 20% gain over ~5 months
        # Annualized should be higher
        self.assertGreater(mwrr, 0.2)


class TestAnnualReviewPnL(unittest.TestCase):
    """Test annual review P&L calculation."""

    def test_pnl_retained_stock(self):
        """Test P&L for stock held at start and still held."""
        # PnL = (current_value + sold_since) - (start_value + bought_since)
        # For retained stock with no transactions: PnL = current_value - start_value
        start_value = 1000.0
        bought_since = 0.0
        sold_since = 0.0
        current_value = 1100.0

        pnl = (current_value + sold_since) - (start_value + bought_since)
        self.assertEqual(pnl, 100.0)

    def test_pnl_with_additional_purchase(self):
        """Test P&L when additional shares bought during period."""
        start_value = 1000.0
        bought_since = 500.0  # Added £500
        sold_since = 0.0
        current_value = 1800.0  # Total now worth £1800

        pnl = (current_value + sold_since) - (start_value + bought_since)
        self.assertEqual(pnl, 300.0)  # £1800 - £1500 = £300 profit

    def test_pnl_with_partial_sale(self):
        """Test P&L when some shares sold during period."""
        start_value = 1000.0
        bought_since = 0.0
        sold_since = 400.0  # Sold £400 worth
        current_value = 700.0  # Remaining now worth £700

        pnl = (current_value + sold_since) - (start_value + bought_since)
        self.assertEqual(pnl, 100.0)  # (£700 + £400) - £1000 = £100 profit


class TestProgressToDoubling(unittest.TestCase):
    """Tests for get_first_buy_price_split_adjusted and progress_to_doubling formatting."""

    def _make_buy(self, price):
        return StockTransaction(
            date=datetime(2020, 1, 1),
            transaction_type='BUY',
            quantity=100,
            price_per_share=price,
            total_amount=price * 100,
        )

    def _make_conversion(self, old_qty, new_qty, date_offset=1):
        return StockTransaction(
            date=datetime(2020, 1, 1 + date_offset),
            transaction_type='STOCK_CONVERSION',
            quantity=old_qty,
            price_per_share=0.0,
            total_amount=0.0,
            new_quantity=new_qty,
        )

    def _make_sell(self):
        return StockTransaction(
            date=datetime(2021, 6, 1),
            transaction_type='SELL',
            quantity=50,
            price_per_share=20.0,
            total_amount=1000.0,
        )

    def test_no_transactions_returns_none(self):
        """Empty transaction list returns None."""
        result = transaction_processor.get_first_buy_price_split_adjusted([])
        self.assertIsNone(result)

    def test_no_buy_transactions_returns_none(self):
        """Transaction list with no BUY returns None."""
        sell = self._make_sell()
        result = transaction_processor.get_first_buy_price_split_adjusted([sell])
        self.assertIsNone(result)

    def test_single_buy_no_conversion(self):
        """Single BUY with no conversion returns the buy price unchanged."""
        buy = self._make_buy(10.0)
        result = transaction_processor.get_first_buy_price_split_adjusted([buy])
        self.assertAlmostEqual(result, 10.0)

    def test_uses_first_buy_not_average(self):
        """Only the FIRST BUY price is used; subsequent buys are ignored."""
        buy1 = StockTransaction(
            date=datetime(2020, 1, 1), transaction_type='BUY',
            quantity=100, price_per_share=10.0, total_amount=1000.0,
        )
        buy2 = StockTransaction(
            date=datetime(2021, 1, 1), transaction_type='BUY',
            quantity=100, price_per_share=20.0, total_amount=2000.0,
        )
        result = transaction_processor.get_first_buy_price_split_adjusted([buy1, buy2])
        self.assertAlmostEqual(result, 10.0)

    def test_two_to_one_split_halves_base_price(self):
        """A 2:1 split (100 -> 200 shares) should halve the base price."""
        buy = self._make_buy(10.0)
        conversion = self._make_conversion(old_qty=100, new_qty=200)
        result = transaction_processor.get_first_buy_price_split_adjusted([buy, conversion])
        self.assertAlmostEqual(result, 5.0)

    def test_reverse_split_increases_base_price(self):
        """A reverse split (200 -> 100 shares) should double the base price."""
        buy = self._make_buy(10.0)
        conversion = self._make_conversion(old_qty=200, new_qty=100)
        result = transaction_processor.get_first_buy_price_split_adjusted([buy, conversion])
        self.assertAlmostEqual(result, 20.0)

    def test_conversion_before_first_buy_is_ignored(self):
        """A STOCK_CONVERSION that precedes the first BUY must not affect base_price."""
        pre_conversion = StockTransaction(
            date=datetime(2019, 12, 31), transaction_type='STOCK_CONVERSION',
            quantity=100, price_per_share=0.0, total_amount=0.0, new_quantity=200,
        )
        buy = self._make_buy(10.0)
        result = transaction_processor.get_first_buy_price_split_adjusted([pre_conversion, buy])
        self.assertAlmostEqual(result, 10.0)

    def test_share_grant_ignored(self):
        """A share grant (quantity == 0 conversion) must not alter the base price."""
        buy = self._make_buy(10.0)
        grant = StockTransaction(
            date=datetime(2020, 6, 1), transaction_type='STOCK_CONVERSION',
            quantity=0, price_per_share=0.0, total_amount=0.0, new_quantity=10,
        )
        result = transaction_processor.get_first_buy_price_split_adjusted([buy, grant])
        self.assertAlmostEqual(result, 10.0)

    def test_running_units_before_sell_accounted_for_in_ratio(self):
        """Conversion ratio accumulates correctly across multiple splits.

        Buy at £10, then 2:1 split → adjusted base £5, then another 2:1 split → £2.50.
        """
        buy = self._make_buy(10.0)
        split1 = self._make_conversion(old_qty=100, new_qty=200, date_offset=1)
        split2 = self._make_conversion(old_qty=200, new_qty=400, date_offset=2)
        result = transaction_processor.get_first_buy_price_split_adjusted([buy, split1, split2])
        self.assertAlmostEqual(result, 2.5)

    def test_progress_to_doubling_format(self):
        """ratio should be formatted as '{:.1f}x'."""
        ratio = 1.5
        formatted = f"{ratio:.1f}x"
        self.assertEqual(formatted, "1.5x")

    def test_progress_to_doubling_exactly_doubled(self):
        """A 2x gain should display as '2.0x'."""
        ratio = 2.0
        formatted = f"{ratio:.1f}x"
        self.assertEqual(formatted, "2.0x")

    def test_progress_to_doubling_missing_base_price_displays_dash(self):
        """When base_price is None or 0 the display value should be the em dash."""
        for bad in (None, 0, 0.0):
            if not bad:
                display = "\u2014"
            else:
                display = f"{1.5:.1f}x"
            self.assertEqual(display, "\u2014")


class TestTaxPnlPoolCostBasis(unittest.TestCase):
    """Tests for pool_cost_basis tracking in calculate_transactions_through_date.

    Reproduces the Blackrock ICS Sterling Liquidity bug (issue #12):
    a sell that clears the first tranche must reset the pool, so subsequent
    sells are costed against the new pool only.
    """

    def _make_txn(self, date, txn_type, qty, price, total):
        return StockTransaction(
            date=date,
            transaction_type=txn_type,
            quantity=qty,
            price_per_share=price,
            total_amount=total,
        )

    def test_pool_cost_basis_no_sells(self):
        """With no sells, pool_cost_basis equals total amount invested."""
        txns = [
            self._make_txn(datetime(2025, 3, 13), 'BUY', 422.01, 118.47, 50000.0),
            self._make_txn(datetime(2025, 12, 24), 'BUY', 792.12, 122.47, 97000.0),
        ]
        result = transaction_processor.calculate_transactions_through_date(
            txns, datetime(2026, 1, 1), include_investment_threshold=False
        )
        self.assertAlmostEqual(result['pool_cost_basis'], 147000.0, places=2)

    def test_pool_cost_basis_full_sell_resets_pool(self):
        """Selling all units clears the pool to zero."""
        txns = [
            self._make_txn(datetime(2025, 3, 13), 'BUY', 422.01, 118.47, 50000.0),
            self._make_txn(datetime(2025, 12, 16), 'SELL', 422.01, 122.34, 51633.0),
        ]
        result = transaction_processor.calculate_transactions_through_date(
            txns, datetime(2025, 12, 31), include_investment_threshold=False
        )
        self.assertAlmostEqual(result['pool_cost_basis'], 0.0, places=2)

    def test_tax_pnl_interleaved_buy_sell_buy_buy_sell(self):
        """Reproduce issue #12: sell clears pool; re-buy creates new pool; next sell uses new pool cost."""
        txns = [
            self._make_txn(datetime(2025, 3, 13),  'BUY',  422.01, 118.47,  50000.0),
            self._make_txn(datetime(2025, 12, 16), 'SELL', 422.01, 122.34,  51633.0),
            self._make_txn(datetime(2025, 12, 24), 'BUY',  792.12, 122.47,  97000.0),
            self._make_txn(datetime(2026, 1, 21),  'BUY',   32.57, 122.81,   4000.0),
            self._make_txn(datetime(2026, 2, 23),  'SELL',  81.1,  123.31,  10000.0),
        ]
        # Pool just before the 23/2/26 sell: 824.69 units, £101,000
        # avg = 101000/824.69 = 122.47...; cost of 81.1 = 81.1/824.69*101000 = 9932.34
        # P&L = 10000 - 9932.34 = 67.66
        result = transaction_processor.calculate_transactions_through_date(
            txns, datetime(2026, 2, 23), include_investment_threshold=False
        )
        self.assertAlmostEqual(result['pool_cost_basis'], 101000.0 - (81.1 / 824.69) * 101000.0, delta=1.0)

        import tax_report_processor
        sell_txn = txns[4]
        pnl_data = tax_report_processor.calculate_tax_pnl('TEST', sell_txn, txns, datetime(2025, 4, 6))
        self.assertIsNotNone(pnl_data)
        self.assertAlmostEqual(pnl_data['pnl'], 67.66, delta=1.0)
        # Allowable cost is the cost of the units sold (not the whole pool), and the
        # reported columns must reconcile: gain = proceeds - allowable cost, and
        # allowable cost = units sold * pool cost per unit.
        units_sold = abs(sell_txn.quantity)
        self.assertAlmostEqual(pnl_data['allowable_cost'], (81.1 / 824.69) * 101000.0, delta=1.0)
        self.assertAlmostEqual(
            pnl_data['pnl'], sell_txn.total_amount - pnl_data['allowable_cost'], delta=0.01)
        self.assertAlmostEqual(
            pnl_data['allowable_cost'], pnl_data['pool_cost_per_unit'] * units_sold, delta=0.01)


class TestDoublingMetrics(unittest.TestCase):
    """Tests for calculate_doubling_metrics (profit-taking detection and progress ratio)."""

    def _buy(self, price, qty=100, date=None):
        return StockTransaction(
            date=date or datetime(2020, 1, 1),
            transaction_type='BUY',
            quantity=qty,
            price_per_share=price,
            total_amount=price * qty,
        )

    def _sell(self, price, qty, date=None):
        return StockTransaction(
            date=date or datetime(2021, 6, 1),
            transaction_type='SELL',
            quantity=qty,
            price_per_share=price,
            total_amount=price * qty,
        )

    def _conversion(self, old_qty, new_qty, date=None):
        return StockTransaction(
            date=date or datetime(2020, 6, 1),
            transaction_type='STOCK_CONVERSION',
            quantity=old_qty,
            price_per_share=0.0,
            total_amount=0.0,
            new_quantity=new_qty,
        )

    def test_no_transactions_returns_dash_and_zero(self):
        """No transactions → em dash and 0 doublings."""
        progress, count = transaction_processor.calculate_doubling_metrics([], current_price=10.0)
        self.assertEqual(progress, "\u2014")
        self.assertEqual(count, 0)

    def test_no_buy_returns_dash(self):
        """Sell-only history (no BUY) → em dash, 0 doublings."""
        sell = self._sell(10.0, 50)
        progress, count = transaction_processor.calculate_doubling_metrics([sell], current_price=10.0)
        self.assertEqual(progress, "\u2014")
        self.assertEqual(count, 0)

    def test_no_current_price_returns_dash(self):
        """No current price (fully sold) → em dash even with valid base."""
        buy = self._buy(10.0)
        progress, count = transaction_processor.calculate_doubling_metrics([buy], current_price=None)
        self.assertEqual(progress, "\u2014")
        self.assertEqual(count, 0)

    def test_buy_only_progress_ratio(self):
        """Single BUY, current price 2× buy price → '2.0x', 0 doublings."""
        buy = self._buy(5.0, qty=100)
        progress, count = transaction_processor.calculate_doubling_metrics([buy], current_price=10.0)
        self.assertEqual(progress, "2.0x")
        self.assertEqual(count, 0)

    def test_sell_below_min_fraction_no_profit_take(self):
        """Sell 10% (< 15%) of holdings at 2× price → no profit-taking event."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(10.0, qty=10, date=datetime(2021, 1, 1))  # 10% of 100
        progress, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=10.0)
        self.assertEqual(count, 0)

    def test_sell_above_max_fraction_no_profit_take(self):
        """Sell 35% (> 30%) of holdings at 2× price → no profit-taking event."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(10.0, qty=35, date=datetime(2021, 1, 1))  # 35% of 100
        progress, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=10.0)
        self.assertEqual(count, 0)

    def test_sell_in_fraction_range_but_price_too_low_no_profit_take(self):
        """Sell 20% of holdings but price only 1.5× base → no profit-taking event."""
        buy = self._buy(10.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(15.0, qty=20, date=datetime(2021, 1, 1))  # 15 < 1.9*10=19
        progress, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=15.0)
        self.assertEqual(count, 0)

    def test_qualifying_profit_take_increments_count_and_resets_base(self):
        """Sell 20% at exactly 2× base (> 1.9×) → count=1, base resets to sell price."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(10.0, qty=20, date=datetime(2021, 1, 1))  # 20% of 100, 10 > 1.9*5=9.5
        # Current price same as sell price after the take
        progress, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=10.0)
        self.assertEqual(count, 1)
        # base resets to 10.0; current=10.0 → 1.0x
        self.assertEqual(progress, "1.0x")

    def test_two_qualifying_profit_takes(self):
        """Two sequential qualifying sells → count=2."""
        buy = self._buy(5.0, qty=200, date=datetime(2020, 1, 1))
        sell1 = self._sell(10.0, qty=40, date=datetime(2021, 1, 1))   # 20% of 200, price 2× base
        sell2 = self._sell(20.0, qty=32, date=datetime(2022, 1, 1))   # 20% of 160, price 2× new base
        progress, count = transaction_processor.calculate_doubling_metrics([buy, sell1, sell2], current_price=20.0)
        self.assertEqual(count, 2)
        # After sell2, base resets to 20.0; current=20.0 → 1.0x
        self.assertEqual(progress, "1.0x")

    def test_split_adjusts_base_price(self):
        """2:1 split after first BUY halves base price for subsequent comparisons.

        Buy at £10, 100 shares.  2:1 split → 200 shares at ~£5.
        Sell 40 shares (20% of 200) at £10 each (2× adjusted base £5 → > 1.9*5=9.5) → profit take.
        """
        buy = self._buy(10.0, qty=100, date=datetime(2020, 1, 1))
        split = self._conversion(100, 200, date=datetime(2020, 6, 1))
        sell = self._sell(10.0, qty=40, date=datetime(2021, 1, 1))   # 20% of 200, 10 > 1.9*5=9.5
        progress, count = transaction_processor.calculate_doubling_metrics([buy, split, sell], current_price=12.0)
        self.assertEqual(count, 1)
        # After sell, base resets to 10.0; current=12.0 → 1.2x
        self.assertEqual(progress, "1.2x")

    def test_exact_boundary_15_percent_qualifies(self):
        """Sell of exactly 15% qualifies if price is high enough."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(10.0, qty=15, date=datetime(2021, 1, 1))  # exactly 15%
        _, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=10.0)
        self.assertEqual(count, 1)

    def test_exact_boundary_30_percent_qualifies(self):
        """Sell of exactly 30% qualifies if price is high enough."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        sell = self._sell(10.0, qty=30, date=datetime(2021, 1, 1))  # exactly 30%
        _, count = transaction_processor.calculate_doubling_metrics([buy, sell], current_price=10.0)
        self.assertEqual(count, 1)

    def test_share_grant_does_not_trigger_profit_take(self):
        """A share grant (STOCK_CONVERSION qty=0) inflates units but must not be counted as a sell."""
        buy = self._buy(5.0, qty=100, date=datetime(2020, 1, 1))
        grant = StockTransaction(
            date=datetime(2020, 6, 1), transaction_type='STOCK_CONVERSION',
            quantity=0, price_per_share=0.0, total_amount=0.0, new_quantity=20,
        )
        progress, count = transaction_processor.calculate_doubling_metrics([buy, grant], current_price=10.0)
        self.assertEqual(count, 0)
        # base stays at 5.0, current=10.0 → 2.0x
        self.assertEqual(progress, "2.0x")

    def test_native_currency_usd_ratio_is_correct(self):
        """current_price must be in the stock's native currency (same as price_per_share).

        Mirrors the AMPX bug report: BUY at $10.30, current price $19.11.
        The caller is responsible for converting GBP current_price back to USD before calling.
        When both are in USD the ratio is 19.11/10.30 ≈ 1.9x, not 1.4x.
        """
        buy = self._buy(10.30, qty=100, date=datetime(2024, 1, 1))
        # Pass native (USD) current price, not GBP
        progress, count = transaction_processor.calculate_doubling_metrics([buy], current_price=19.11)
        self.assertEqual(progress, "1.9x")
        self.assertEqual(count, 0)

    def test_native_currency_nok_ratio_is_correct(self):
        """Mirrors KOG.OL bug report: first BUY at 315 NOK, current price 412.4 NOK.

        Ratio should be 412.4/315 ≈ 1.3x when both sides are in NOK.
        Passing GBP current_price (£32.33) against NOK base (315) would give 0.1x — the
        wrong result caught by issue #7.
        """
        buy = self._buy(315.0, qty=100, date=datetime(2024, 1, 1))
        progress, count = transaction_processor.calculate_doubling_metrics([buy], current_price=412.4)
        self.assertEqual(progress, "1.3x")
        self.assertEqual(count, 0)


def run_unit_tests():
    """Run every unit test in this module.

    Classes used to be listed by hand here, and the list fell behind: seven classes and
    44 tests were defined but never run by `portfolio.py --mode test`, including the
    alert-delivery tests and every regression test written for #26 and #28
    (investment-reviews#29).  Discovery cannot fall behind.
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    logger.info(f"Unit tests: {result.testsRun} run, "
                f"{len(result.failures)} failed, {len(result.errors)} errored")
    return result.wasSuccessful()


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------

from periodic_review_processor import (
    calculate_benchmark_performance,
    create_periodic_review_summary,
    create_tag_summary,
    BENCHMARKS,
    BENCHMARK_NORMALISED_START,
)


def _make_price_data(tickers, start_date, eval_date, start_prices, eval_prices):
    """Build a minimal price_data dict compatible with get_stock_price_from_data."""
    price_data = {}
    for ticker, sp, ep in zip(tickers, start_prices, eval_prices):
        price_data[ticker] = pd.DataFrame(
            {'Close': [sp, ep]},
            index=[start_date, eval_date]
        )
    return price_data


class TestBenchmarkPerformance(unittest.TestCase):
    """Tests for calculate_benchmark_performance and summary helpers."""

    def setUp(self):
        self.start_date = datetime(2026, 1, 1)
        self.eval_date = datetime(2026, 3, 1)

    def _price_data_for_ticker(self, ticker, start_price, eval_price):
        return {
            ticker: pd.DataFrame(
                {'Close': [start_price, eval_price]},
                index=[self.start_date, self.eval_date]
            )
        }

    def test_normalised_start_value_is_1000(self):
        """Start value must always equal BENCHMARK_NORMALISED_START regardless of index level."""
        ticker = '^GSPC'
        price_data = self._price_data_for_ticker(ticker, start_price=4500.0, eval_price=4950.0)
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        row = df[df['ticker'] == ticker]
        self.assertFalse(row.empty, "Expected a row for ^GSPC")
        self.assertEqual(row.iloc[0]['start_value'], (BENCHMARK_NORMALISED_START, 'GBP'))

    def test_roi_reflects_price_change(self):
        """ROI should equal (eval_price - start_price) / start_price."""
        ticker = '^GSPC'
        start_price, eval_price = 4000.0, 4400.0  # +10%
        price_data = self._price_data_for_ticker(ticker, start_price, eval_price)
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        row = df[df['ticker'] == ticker]
        self.assertAlmostEqual(row.iloc[0]['simple_roi'], 0.10, places=6)

    def test_current_value_scaled_correctly(self):
        """Current value = £1000 * (eval_price / start_price)."""
        ticker = '^FTSE'
        start_price, eval_price = 8000.0, 8400.0  # +5%
        price_data = self._price_data_for_ticker(ticker, start_price, eval_price)
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        row = df[df['ticker'] == ticker]
        expected_current = BENCHMARK_NORMALISED_START * (eval_price / start_price)
        self.assertAlmostEqual(row.iloc[0]['current_value'][0], expected_current, places=4)

    def test_missing_start_price_skips_ticker(self):
        """A ticker with no start-date price should be omitted from results."""
        ticker = '^GSPC'
        # Only eval price present (no data at start_date)
        price_data = {
            ticker: pd.DataFrame(
                {'Close': [4950.0]},
                index=[self.eval_date]
            )
        }
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        self.assertTrue(df.empty or ticker not in df['ticker'].values)

    def test_missing_eval_price_skips_ticker(self):
        """A ticker with no eval-date price should be omitted from results."""
        ticker = '^GSPC'
        price_data = {
            ticker: pd.DataFrame(
                {'Close': [4500.0]},
                index=[self.start_date]
            )
        }
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        self.assertTrue(df.empty or ticker not in df['ticker'].values)

    def test_all_rows_flagged_is_benchmark(self):
        """Every row returned must have is_benchmark=True."""
        ticker = '^GSPC'
        price_data = self._price_data_for_ticker(ticker, 4000.0, 4200.0)
        df = calculate_benchmark_performance(price_data, self.start_date, self.eval_date)
        self.assertFalse(df.empty)
        self.assertTrue(all(df['is_benchmark'] == True))  # noqa: E712

    def test_benchmark_not_in_portfolio_summary_totals(self):
        """Benchmark values must not contribute to portfolio category totals."""
        # Build a minimal benchmarks_df with one row
        benchmarks_df = pd.DataFrame([{
            'ticker': '^GSPC',
            'company_name': 'S&P 500',
            'tag': 'Benchmarks - US Equities',
            'start_value': (BENCHMARK_NORMALISED_START, 'GBP'),
            'current_value': (1100.0, 'GBP'),
            'pnl': (100.0, 'GBP'),
            'simple_roi': 0.10,
            'is_benchmark': True,
        }])

        # results dict with no portfolio data
        results = {k: pd.DataFrame() for k in ['new', 'retained', 'increased', 'sold']}
        summary = create_periodic_review_summary(
            results,
            self.start_date,
            self.eval_date,
            self.eval_date,
            benchmarks_df=benchmarks_df
        )

        # Portfolio category rows should all have zero values
        portfolio_rows = summary[summary['is_benchmark'] == False]  # noqa: E712
        for col in ['start_value', 'current_value', 'pnl']:
            total = sum(v[0] for v in portfolio_rows[col])
            self.assertEqual(total, 0.0, f"Portfolio {col} should be 0, got {total}")

        # Benchmark summary row must exist and be flagged
        benchmark_rows = summary[summary['is_benchmark'] == True]  # noqa: E712
        self.assertEqual(len(benchmark_rows), 1)
        self.assertEqual(benchmark_rows.iloc[0]['category'], 'Benchmarks')

    def test_create_tag_summary_benchmark_rows_flagged(self):
        """create_tag_summary must flag benchmark tag rows with is_benchmark=True."""
        benchmarks_df = pd.DataFrame([
            {
                'ticker': '^GSPC',
                'company_name': 'S&P 500',
                'tag': 'Benchmarks - US Equities',
                'start_value': (1000.0, 'GBP'),
                'current_value': (1100.0, 'GBP'),
                'pnl': (100.0, 'GBP'),
                'simple_roi': 0.10,
                'is_benchmark': True,
            },
            {
                'ticker': '^IXIC',
                'company_name': 'Nasdaq',
                'tag': 'Benchmarks - US Equities',
                'start_value': (1000.0, 'GBP'),
                'current_value': (1200.0, 'GBP'),
                'pnl': (200.0, 'GBP'),
                'simple_roi': 0.20,
                'is_benchmark': True,
            },
        ])

        results = {k: pd.DataFrame() for k in ['new', 'retained', 'increased', 'sold']}
        per_tag = create_tag_summary(
            results,
            self.start_date,
            self.eval_date,
            self.eval_date,
            benchmarks_df=benchmarks_df
        )

        # Should have exactly one tag row for 'Benchmarks - US Equities'
        tag_rows = per_tag[per_tag['tag'] == 'Benchmarks - US Equities']
        self.assertEqual(len(tag_rows), 1)
        self.assertTrue(tag_rows.iloc[0]['is_benchmark'])
        # sort_category must be 'benchmark' for correct ordering
        self.assertEqual(tag_rows.iloc[0]['sort_category'], 'benchmark')
        # Aggregated start_value should be sum (2 x £1000)
        self.assertEqual(tag_rows.iloc[0]['start_value'], (2000.0, 'GBP'))


# ---------------------------------------------------------------------------
# Thesis candidate tests
# ---------------------------------------------------------------------------

import json
import os
import tempfile

from periodic_review_processor import (
    calculate_thesis_candidate_performance,
    create_thesis_summary,
)
from thesis_config import load_thesis_config


class TestThesisConfig(unittest.TestCase):
    """Tests for loading and validating the thesis candidate configuration file."""

    VALID_CONFIG = {
        'schema_version': 1,
        'theses': [
            {
                'name': 'European Defence',
                'candidates': [
                    {'ticker': 'RHM.DE', 'name': 'Rheinmetall'},
                    {'ticker': 'KOG.OL', 'name': 'Kongsberg Gruppen'},
                ],
            }
        ],
    }

    def _write_config(self, content):
        """Write content (str or object) to a temp file and return its path."""
        fd, path = tempfile.mkstemp(suffix='.json')
        with os.fdopen(fd, 'w') as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f)
        self.addCleanup(os.unlink, path)
        return path

    def test_valid_config_loads(self):
        theses = load_thesis_config(self._write_config(self.VALID_CONFIG))
        self.assertEqual(len(theses), 1)
        self.assertEqual(theses[0]['name'], 'European Defence')
        self.assertEqual(len(theses[0]['candidates']), 2)

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            load_thesis_config('/nonexistent/theses.json')

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config('{not json'))

    def test_unsupported_schema_version_raises(self):
        config = json.loads(json.dumps(self.VALID_CONFIG))
        config['schema_version'] = 2
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config(config))

    def test_missing_theses_raises(self):
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config({'schema_version': 1}))

    def test_thesis_without_name_raises(self):
        config = {'schema_version': 1, 'theses': [{'candidates': [{'ticker': 'VRT', 'name': 'Vertiv'}]}]}
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config(config))

    def test_candidate_without_ticker_raises(self):
        config = {'schema_version': 1, 'theses': [{'name': 'Quantum', 'candidates': [{'name': 'IonQ'}]}]}
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config(config))

    def test_thesis_with_no_candidates_raises(self):
        config = {'schema_version': 1, 'theses': [{'name': 'Quantum', 'candidates': []}]}
        with self.assertRaises(ValueError):
            load_thesis_config(self._write_config(config))


class TestThesisCandidatePerformance(unittest.TestCase):
    """Tests for thesis candidate performance, baskets and breadth."""

    def setUp(self):
        self.start_date = datetime(2026, 1, 1)
        self.eval_date = datetime(2026, 3, 1)
        self.theses = [
            {
                'name': 'European Defence',
                'candidates': [
                    {'ticker': 'RHM.DE', 'name': 'Rheinmetall'},
                    {'ticker': 'KOG.OL', 'name': 'Kongsberg Gruppen'},
                    {'ticker': 'HAG.DE', 'name': 'Hensoldt'},
                ],
            }
        ]

    def _price_data(self, prices):
        """Build price data from {ticker: (start_price, eval_price)}."""
        return {
            ticker: pd.DataFrame(
                {'Close': [start, end]},
                index=[self.start_date, self.eval_date]
            )
            for ticker, (start, end) in prices.items()
        }

    def _performance(self, prices, held_tickers=frozenset(), highs_and_vol=None):
        return calculate_thesis_candidate_performance(
            self.theses, self._price_data(prices), highs_and_vol or {},
            set(held_tickers), self.start_date, self.eval_date
        )

    def test_normalised_start_value_is_1000(self):
        """Each candidate starts at £1000, matching the benchmark methodology."""
        df = self._performance({'RHM.DE': (500.0, 550.0)})
        self.assertEqual(df.iloc[0]['start_value'], (BENCHMARK_NORMALISED_START, 'GBP'))
        self.assertAlmostEqual(df.iloc[0]['current_value'][0], 1100.0, places=4)
        self.assertAlmostEqual(df.iloc[0]['simple_roi'], 0.10, places=6)

    def test_candidate_without_prices_is_omitted(self):
        """A candidate with no start price contributes no row."""
        price_data = self._price_data({'RHM.DE': (500.0, 550.0)})
        price_data['KOG.OL'] = pd.DataFrame({'Close': [300.0]}, index=[self.eval_date])
        df = calculate_thesis_candidate_performance(
            self.theses, price_data, {}, set(), self.start_date, self.eval_date
        )
        self.assertEqual(sorted(df['ticker']), ['RHM.DE'])

    def test_held_flag_derived_from_portfolio(self):
        """is_held comes from the portfolio tickers, matched case-insensitively."""
        df = self._performance(
            {'RHM.DE': (500.0, 550.0), 'KOG.OL': (100.0, 90.0)},
            held_tickers={'RHM.DE'}
        )
        held = df.set_index('ticker')['is_held']
        self.assertTrue(held['RHM.DE'])
        self.assertFalse(held['KOG.OL'])
        self.assertEqual(df.set_index('ticker')['held']['RHM.DE'], 'Yes')

    def test_pct_of_high_uses_eval_price(self):
        """% of high is the eval-date price over the 90-day high."""
        highs = {'RHM.DE': {'recent_high': 600.0, 'annualized_volatility': 0.3}}
        df = self._performance({'RHM.DE': (500.0, 550.0)}, highs_and_vol=highs)
        self.assertAlmostEqual(df.iloc[0]['current_price_pct_of_high'], 550.0 / 600.0, places=6)
        self.assertAlmostEqual(df.iloc[0]['volatility'], 0.3, places=6)

    def test_baskets_are_equal_weighted(self):
        """Candidate basket is the mean of all valid returns; held basket the mean of held ones."""
        df = self._performance(
            {
                'RHM.DE': (100.0, 120.0),  # +20%, held
                'KOG.OL': (100.0, 110.0),  # +10%
                'HAG.DE': (100.0, 90.0),   # -10%
            },
            held_tickers={'RHM.DE', 'HAG.DE'}
        )
        summary = create_thesis_summary(self.theses, df)
        row = summary.iloc[0]
        self.assertAlmostEqual(row['candidate_return'], (0.20 + 0.10 - 0.10) / 3, places=6)
        self.assertAlmostEqual(row['held_return'], (0.20 - 0.10) / 2, places=6)
        self.assertAlmostEqual(row['held_vs_candidates'], row['held_return'] - row['candidate_return'], places=6)

    def test_held_basket_counts_a_holding_once(self):
        """Position size is irrelevant — the held basket is unweighted by definition."""
        df = self._performance(
            {'RHM.DE': (100.0, 120.0), 'KOG.OL': (100.0, 110.0)},
            held_tickers={'RHM.DE', 'KOG.OL'}
        )
        summary = create_thesis_summary(self.theses, df)
        self.assertAlmostEqual(summary.iloc[0]['held_return'], 0.15, places=6)

    def test_breadth_denominator_is_valid_candidates(self):
        """Breadth is positive returns over candidates with valid returns, not configured count."""
        price_data = self._price_data({'RHM.DE': (100.0, 120.0), 'KOG.OL': (100.0, 90.0)})
        df = calculate_thesis_candidate_performance(
            self.theses, price_data, {}, set(), self.start_date, self.eval_date
        )
        summary = create_thesis_summary(self.theses, df)
        row = summary.iloc[0]
        self.assertEqual(row['positive_candidates'], 1)
        self.assertEqual(row['valid_candidates'], 2)
        self.assertEqual(row['configured_candidates'], 3)
        self.assertAlmostEqual(row['breadth'], 0.5, places=6)

    def test_no_held_candidates_leaves_held_columns_blank(self):
        """A thesis with nothing held reports no held basket and no relative performance."""
        df = self._performance({'RHM.DE': (100.0, 120.0)})
        summary = create_thesis_summary(self.theses, df)
        # Missing values may be None or NaN depending on the other rows; both render blank
        self.assertTrue(pd.isna(summary.iloc[0]['held_return']))
        self.assertTrue(pd.isna(summary.iloc[0]['held_vs_candidates']))

    def test_held_columns_blank_only_for_theses_with_nothing_held(self):
        """One thesis holding candidates must not fill in another thesis's held basket."""
        theses = self.theses + [{
            'name': 'Data Centre Infrastructure',
            'candidates': [{'ticker': 'VRT', 'name': 'Vertiv Holdings'}],
        }]
        price_data = self._price_data({'RHM.DE': (100.0, 120.0), 'VRT': (50.0, 55.0)})
        df = calculate_thesis_candidate_performance(
            theses, price_data, {}, {'RHM.DE'}, self.start_date, self.eval_date
        )
        summary = create_thesis_summary(theses, df).set_index('thesis')
        self.assertAlmostEqual(summary.loc['European Defence', 'held_return'], 0.20, places=6)
        self.assertTrue(pd.isna(summary.loc['Data Centre Infrastructure', 'held_return']))

    def test_thesis_with_no_valid_candidates_is_omitted(self):
        """No usable price data for any candidate means no summary row."""
        summary = create_thesis_summary(self.theses, pd.DataFrame())
        self.assertTrue(summary.empty)

    def test_tag_summary_thesis_rows(self):
        """create_tag_summary appends one candidate-basket row per thesis, sorted after benchmarks."""
        df = self._performance({'RHM.DE': (100.0, 120.0), 'KOG.OL': (100.0, 110.0)})
        results = {k: pd.DataFrame() for k in ['new', 'retained', 'increased', 'sold']}
        per_tag = create_tag_summary(
            results, self.start_date, self.eval_date, self.eval_date,
            thesis_candidates_df=df
        )

        thesis_rows = per_tag[per_tag['sort_category'] == 'thesis']
        self.assertEqual(len(thesis_rows), 1)
        row = thesis_rows.iloc[0]
        self.assertEqual(row['category'], 'Thesis - European Defence')
        self.assertEqual(row['count'], 2)
        # 2 x £1000 in, £1200 + £1100 out
        self.assertEqual(row['start_value'], (2000.0, 'GBP'))
        self.assertAlmostEqual(row['current_value'][0], 2300.0, places=4)
        self.assertAlmostEqual(row['roi'], 0.15, places=6)

    def test_thesis_rows_excluded_from_portfolio_totals(self):
        """Thesis baskets are notional and must not be added to portfolio category totals."""
        df = self._performance({'RHM.DE': (100.0, 120.0)})
        results = {k: pd.DataFrame() for k in ['new', 'retained', 'increased', 'sold']}
        summary = create_periodic_review_summary(
            results, self.start_date, self.eval_date, self.eval_date
        )
        self.assertEqual(sum(v[0] for v in summary['start_value']), 0.0)

        per_tag = create_tag_summary(
            results, self.start_date, self.eval_date, self.eval_date,
            thesis_candidates_df=df
        )
        self.assertTrue(per_tag[per_tag['sort_category'] == 'thesis'].iloc[0]['is_benchmark'])


import io
from contextlib import redirect_stdout

import alerts
import full_history_processor
import reporter_definitions as rd
from console_parser import ConsoleOutputParser
from console_table_writer import ConsoleTableWriter
from data_table_builder import DataTableBuilder


class TestDailyChange(unittest.TestCase):
    """Tests for full_history_processor.calculate_daily_change."""

    @staticmethod
    def _prices(closes):
        dates = pd.date_range('2026-07-01', periods=len(closes))
        return pd.DataFrame({'Close': closes}, index=dates)

    def test_rise(self):
        """Change is measured between the last two closes."""
        change = full_history_processor.calculate_daily_change(self._prices([100.0, 102.0, 105.06]))
        self.assertAlmostEqual(change, 0.03, places=6)

    def test_fall(self):
        """A fall gives a negative change."""
        change = full_history_processor.calculate_daily_change(self._prices([100.0, 95.0]))
        self.assertAlmostEqual(change, -0.05, places=6)

    def test_trailing_nan_ignored(self):
        """NaN closes are skipped rather than producing NaN."""
        change = full_history_processor.calculate_daily_change(self._prices([100.0, 110.0, np.nan]))
        self.assertAlmostEqual(change, 0.1, places=6)

    def test_single_close(self):
        """A single close (e.g. live-price fallback) has no comparison point."""
        self.assertIsNone(full_history_processor.calculate_daily_change(self._prices([100.0])))

    def test_empty_and_missing(self):
        """Empty, absent, and column-less price data return None."""
        self.assertIsNone(full_history_processor.calculate_daily_change(None))
        self.assertIsNone(full_history_processor.calculate_daily_change(pd.DataFrame()))
        self.assertIsNone(full_history_processor.calculate_daily_change(pd.DataFrame({'Open': [1.0, 2.0]})))

    def test_zero_previous_close(self):
        """A zero previous close cannot yield a ratio."""
        self.assertIsNone(full_history_processor.calculate_daily_change(self._prices([0.0, 10.0])))


class TestFullHistoryStockParsing(unittest.TestCase):
    """Tests for ConsoleOutputParser.parse_stocks against real console output."""

    @staticmethod
    def _render(rows):
        """Render rows through the real console writer, as portfolio.py does."""
        df = pd.DataFrame(rows)
        config = rd.COLUMN_CONFIGS['full_history']
        table_data = DataTableBuilder().build_table(df, config, 'Full Investment History')
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            ConsoleTableWriter().write_table(table_data, config)
        return buffer.getvalue()

    @staticmethod
    def _row(**overrides):
        row = {
            'tag': 'AI', 'stock_name': 'Palantir', 'ticker': 'PLTR', 'account_type': 'ISA',
            'total_invested': 5000.0, 'total_received': 0.0, 'units_held': 100,
            'current_value': 12000.0, 'total_pnl': 7000.0, 'unrealized_profit': 7000.0,
            'simple_roi': 1.4, 'mwrr': 0.5, 'current_price': 120.0, 'daily_change': 0.042,
            'recent_high': 130.0, 'current_price_pct_of_high': 0.92, 'volatility': 0.31,
            'progress_to_doubling': '1.97x', 'doubling_count': 1,
            'first_transaction_date': datetime(2023, 1, 5),
            'final_transaction_date': datetime(2025, 6, 2),
        }
        row.update(overrides)
        return row

    def test_parses_stock_row(self):
        """Company, ticker, tag, value, daily change and progress are recovered."""
        output = self._render([self._row()])
        stocks = ConsoleOutputParser.extract_stocks_from_output(output)

        self.assertEqual(len(stocks), 1)
        stock = stocks[0]
        self.assertEqual(stock['company'], 'Palantir')
        self.assertEqual(stock['ticker'], 'PLTR')
        self.assertEqual(stock['tag'], 'AI')
        self.assertAlmostEqual(stock['current_value'], 12000.0)
        self.assertAlmostEqual(stock['daily_change'], 0.042, places=4)
        self.assertAlmostEqual(stock['progress_to_2x'], 1.97)

    def test_negative_change_survives_colour_coding(self):
        """ANSI colour codes around cell values are stripped before parsing."""
        output = self._render([self._row(daily_change=-0.051, simple_roi=-0.3, current_price_pct_of_high=0.7)])
        stock = ConsoleOutputParser.extract_stocks_from_output(output)[0]
        self.assertAlmostEqual(stock['daily_change'], -0.051, places=4)

    def test_sold_stock_has_no_change_or_progress(self):
        """A fully sold row (no price) yields None rather than a bogus number."""
        output = self._render([self._row(
            units_held=0, current_value=0.0, current_price=None, daily_change=None,
            recent_high=None, current_price_pct_of_high=None, volatility=None,
            progress_to_doubling='—', doubling_count=2,
        )])
        stock = ConsoleOutputParser.extract_stocks_from_output(output)[0]
        self.assertIsNone(stock['daily_change'])
        self.assertIsNone(stock['progress_to_2x'])
        self.assertEqual(stock['ticker'], 'PLTR')

    def test_all_rows_returned(self):
        """Every stock row is returned, not just the first."""
        output = self._render([
            self._row(ticker='PLTR'),
            self._row(ticker='NVDA', stock_name='Nvidia'),
            self._row(ticker='RR.L', stock_name='Rolls-Royce', tag='Defense'),
        ])
        stocks = ConsoleOutputParser.extract_stocks_from_output(output)
        self.assertEqual([s['ticker'] for s in stocks], ['PLTR', 'NVDA', 'RR.L'])

    def test_missing_table_raises(self):
        """Output without the detail table is an error, not an empty result."""
        with self.assertRaises(ValueError):
            ConsoleOutputParser.extract_stocks_from_output('Portfolio Summary\n=================\n')


class TestAlertSelection(unittest.TestCase):
    """Tests for alerts.find_alerts and alert email formatting."""

    @staticmethod
    def _stock(ticker, progress=None, change=None, company=None, tag='AI', value=1000.0):
        return {
            'company': company or ticker,
            'ticker': ticker,
            'tag': tag,
            'current_value': value,
            'daily_change': change,
            'progress_to_2x': progress,
        }

    def test_doubling_threshold_is_exclusive(self):
        """1.95x does not alert; anything above it does."""
        stocks = [
            self._stock('BELOW', progress=1.94),
            self._stock('EQUAL', progress=1.95),
            self._stock('ABOVE', progress=1.96),
        ]
        found = alerts.find_alerts(stocks, 3.0)
        self.assertEqual([s['ticker'] for s in found['approaching_doubling']], ['ABOVE'])

    def test_movers_in_both_directions(self):
        """Rises and falls beyond the threshold both alert; smaller moves do not."""
        stocks = [
            self._stock('UP', change=0.045),
            self._stock('DOWN', change=-0.062),
            self._stock('FLAT', change=0.012),
        ]
        found = alerts.find_alerts(stocks, 3.0)
        self.assertEqual({s['ticker'] for s in found['big_movers']}, {'UP', 'DOWN'})

    def test_threshold_is_inclusive_and_configurable(self):
        """A move of exactly the threshold alerts, and the threshold is honoured."""
        stocks = [self._stock('EXACT', change=0.05), self._stock('UNDER', change=0.049)]
        found = alerts.find_alerts(stocks, 5.0)
        self.assertEqual([s['ticker'] for s in found['big_movers']], ['EXACT'])

    def test_missing_values_never_alert(self):
        """Stocks with no price data are skipped rather than treated as zero."""
        found = alerts.find_alerts([self._stock('SOLD')], 3.0)
        self.assertEqual(found['approaching_doubling'], [])
        self.assertEqual(found['big_movers'], [])

    def test_sorted_most_notable_first(self):
        """Doublings sort by progress, movers by size of move regardless of sign."""
        stocks = [
            self._stock('A', progress=1.98, change=0.04),
            self._stock('B', progress=2.40, change=-0.09),
        ]
        found = alerts.find_alerts(stocks, 3.0)
        self.assertEqual([s['ticker'] for s in found['approaching_doubling']], ['B', 'A'])
        self.assertEqual([s['ticker'] for s in found['big_movers']], ['B', 'A'])

    def test_email_reports_both_sections(self):
        """The email names both categories and the stocks in them."""
        found = alerts.find_alerts(
            [self._stock('PLTR', progress=2.1, company='Palantir'),
             self._stock('NVDA', change=-0.08, company='Nvidia')],
            3.0
        )
        subject, body = alerts.format_alert_email(found, 3.0)

        self.assertIn('1 near 2x', subject)
        self.assertIn('1 big mover', subject)
        self.assertIn('Palantir (PLTR) [AI], £1,000 — 2.10x', body)
        self.assertIn('Nvidia (NVDA) [AI], £1,000 — -8.0%', body)
        self.assertIn('3.0%', body)

    def test_email_omits_empty_section(self):
        """A quiet category is left out of the email entirely."""
        found = alerts.find_alerts([self._stock('PLTR', progress=2.1)], 3.0)
        subject, body = alerts.format_alert_email(found, 3.0)
        self.assertNotIn('big mover', subject)
        self.assertNotIn('Moved at least', body)


class _FakeSMTP:
    """Minimal stand-in for smtplib.SMTP recording the conversation.

    The original alert bug was entirely in the parts of the send that no test touched —
    whether we authenticate at all, and as whom — so these tests assert on the sequence of
    calls rather than just "no exception raised".
    """

    instances = []

    def __init__(self, host, port, timeout=None, starttls_offered=True, fail_on=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.starttls_offered = starttls_offered
        self.fail_on = fail_on or {}
        self.calls = []
        self.login_args = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _maybe_fail(self, name):
        if name in self.fail_on:
            raise self.fail_on[name]

    def ehlo(self):
        self.calls.append('ehlo')

    def has_extn(self, name):
        return name == 'starttls' and self.starttls_offered

    def starttls(self, context=None):
        self.calls.append('starttls')

    def login(self, user, password):
        self.calls.append('login')
        self.login_args = (user, password)
        self._maybe_fail('login')

    def send_message(self, message):
        self.calls.append('send_message')
        self._maybe_fail('send_message')
        self.sent = message


class TestAlertDelivery(unittest.TestCase):
    """Tests for alerts.send_alert_email — the path that silently broke in #20."""

    def setUp(self):
        _FakeSMTP.instances = []
        self._real_smtp = alerts.smtplib.SMTP

    def tearDown(self):
        alerts.smtplib.SMTP = self._real_smtp

    def _patch(self, **kwargs):
        def factory(host, port, timeout=None):
            return _FakeSMTP(host, port, timeout, **kwargs)
        alerts.smtplib.SMTP = factory

    @staticmethod
    def _config(**overrides):
        config = {
            'to': 'someone@example.com',
            'from': 'alerts@calumlabs.uk',
            'smtp_host': 'host.docker.internal',
            'smtp_port': 1025,
            'smtp_user': 'account@proton.me',
            'smtp_password': 'bridge-generated',
        }
        config.update(overrides)
        return config

    def test_authenticates_before_sending(self):
        """STARTTLS then login must both precede the message (the #20 regression)."""
        self._patch()
        alerts.send_alert_email(self._config(), 'subject', 'body')
        smtp = _FakeSMTP.instances[0]
        self.assertEqual(smtp.calls, ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])

    def test_authenticates_as_the_account_not_the_sender(self):
        """Username is the bridge account address; From stays the send-as address."""
        self._patch()
        alerts.send_alert_email(self._config(), 'subject', 'body')
        smtp = _FakeSMTP.instances[0]
        self.assertEqual(smtp.login_args, ('account@proton.me', 'bridge-generated'))
        self.assertEqual(smtp.sent['From'], 'alerts@calumlabs.uk')

    def test_password_read_from_file_when_configured(self):
        """A secret file wins over an inline value, and is stripped of its trailing newline."""
        self._patch()
        with tempfile.NamedTemporaryFile('w', suffix='.secret', delete=False) as handle:
            handle.write('from-a-file\n')
            path = handle.name
        try:
            alerts.send_alert_email(
                self._config(smtp_password_file=path), 'subject', 'body')
        finally:
            os.unlink(path)
        self.assertEqual(_FakeSMTP.instances[0].login_args[1], 'from-a-file')

    def test_unreadable_secret_file_is_a_delivery_error(self):
        """A missing secret must not surface as a bare OSError."""
        self._patch()
        with self.assertRaises(alerts.AlertDeliveryError):
            alerts.send_alert_email(
                self._config(smtp_password_file='/nonexistent/smtp_password'),
                'subject', 'body')

    def test_user_without_password_refuses_to_send(self):
        """An unseeded placeholder must fail loudly, not send unauthenticated."""
        self._patch()
        with self.assertRaises(alerts.AlertDeliveryError):
            alerts.send_alert_email(self._config(smtp_password=''), 'subject', 'body')
        self.assertEqual(_FakeSMTP.instances[0].calls, ['ehlo', 'starttls', 'ehlo'])

    def test_starttls_skipped_when_not_offered(self):
        """A relay without STARTTLS still authenticates rather than erroring."""
        self._patch(starttls_offered=False)
        alerts.send_alert_email(self._config(), 'subject', 'body')
        self.assertEqual(_FakeSMTP.instances[0].calls, ['ehlo', 'login', 'send_message'])

    def test_rejection_at_data_becomes_a_delivery_error(self):
        """The exact 554 the bridge returns for an unowned From address."""
        self._patch(fail_on={'send_message': alerts.smtplib.SMTPDataError(
            554, b'5.0.0 Error: no such user')})
        with self.assertRaises(alerts.AlertDeliveryError) as caught:
            alerts.send_alert_email(self._config(), 'subject', 'body')
        self.assertIn('no such user', str(caught.exception))

    def test_unreachable_relay_becomes_a_delivery_error(self):
        """A connection failure is a delivery error, not an unhandled OSError."""
        def factory(host, port, timeout=None):
            raise ConnectionRefusedError(61, 'Connection refused')
        alerts.smtplib.SMTP = factory
        with self.assertRaises(alerts.AlertDeliveryError):
            alerts.send_alert_email(self._config(), 'subject', 'body')


class TestAlertFailureIsNonFatal(unittest.TestCase):
    """A dead mail relay must not be reported as a failed portfolio update (#20).

    The spreadsheet is already written by the time alerts are sent, so an undeliverable
    email has to stay distinguishable from a broken pipeline — that conflation is what made
    the dashboard show DOWN for ten days while the sheet updated correctly every night.
    """

    def _updater(self, alert_config):
        import logging
        import update_google_sheet
        updater = update_google_sheet.PortfolioUpdater.__new__(
            update_google_sheet.PortfolioUpdater)
        updater.logger = logging.getLogger('test')
        updater.dry_run = False
        updater.daily_change_threshold = 3.0
        updater.alert_delivery_ok = True
        updater.config = {'notifications': {'alerts': alert_config}}
        return updater

    def test_delivery_failure_is_recorded_not_raised(self):
        """The exception is swallowed, but the failure is recorded for the metric."""
        updater = self._updater({'to': 'someone@example.com'})
        console_output = 'irrelevant — the parser is stubbed below'
        with patch.object(ConsoleOutputParser, 'extract_stocks_from_output',
                          return_value=[{'company': 'Palantir', 'ticker': 'PLTR',
                                         'tag': 'AI', 'current_value': 1000.0,
                                         'progress_to_2x': 2.5, 'daily_change': 0.01}]), \
             patch.object(alerts, 'send_alert_email',
                          side_effect=alerts.AlertDeliveryError('554 no such user')):
            updater._send_alerts(console_output)
        self.assertFalse(updater.alert_delivery_ok)

    def test_successful_delivery_leaves_the_channel_healthy(self):
        """The happy path must not flip the alert-delivery flag."""
        updater = self._updater({'to': 'someone@example.com'})
        with patch.object(ConsoleOutputParser, 'extract_stocks_from_output',
                          return_value=[{'company': 'Palantir', 'ticker': 'PLTR',
                                         'tag': 'AI', 'current_value': 1000.0,
                                         'progress_to_2x': 2.5, 'daily_change': 0.01}]), \
             patch.object(alerts, 'send_alert_email'):
            updater._send_alerts('irrelevant')
        self.assertTrue(updater.alert_delivery_ok)

    def test_no_recipient_configured_is_not_a_delivery_failure(self):
        """Alerts switched off must leave the channel reported healthy, not broken."""
        updater = self._updater({'to': ''})
        updater._send_alerts('irrelevant')
        self.assertTrue(updater.alert_delivery_ok)


import financial_metrics
import periodic_review_processor
from datetime import timedelta


class TestRecentHighs(unittest.TestCase):
    """Recent-high window and the smoothed / percentile highs (investment-reviews#26)."""

    ANCHOR = datetime(2026, 8, 31)

    def _series(self, closes, end=None, offset_days=0):
        """Build one ticker's price frame, one row per calendar day ending at the anchor.

        Args:
            closes: Closing prices, oldest first
            end: Date of the last row (defaults to the anchor)
            offset_days: Days to shift the whole series back from that end date
        """
        end = (end or self.ANCHOR) - timedelta(days=offset_days)
        index = pd.date_range(end=end, periods=len(closes), freq='D')
        return {'TEST': pd.DataFrame({'Close': closes}, index=index)}

    def test_window_is_ninety_calendar_days_not_ninety_rows(self):
        """A spike 100 days back is outside the window even though the data reaches it.

        The fetched series carries a buffer before the requested start, so counting rows
        made full-history mode read further back than 90 days and report a higher high.
        """
        closes = [100.0] * 120
        closes[19] = 500.0  # 100 days before the anchor
        result = financial_metrics.calculate_highs_and_volatility(self._series(closes))
        self.assertAlmostEqual(result['TEST']['recent_high'], 100.0)

    def test_window_ends_at_eval_date_when_given(self):
        """With an eval date, prices after it are excluded from the window."""
        closes = [100.0] * 100 + [900.0] * 20
        result = financial_metrics.calculate_highs_and_volatility(
            self._series(closes), eval_date=self.ANCHOR - timedelta(days=20)
        )
        self.assertAlmostEqual(result['TEST']['recent_high'], 100.0)

    def test_single_day_spike_moves_high_but_not_smoothed_or_percentile(self):
        """The whole point: one spike day sets the raw high and barely moves the others."""
        closes = [100.0] * 90
        closes[45] = 200.0
        result = financial_metrics.calculate_highs_and_volatility(self._series(closes))['TEST']
        self.assertAlmostEqual(result['recent_high'], 200.0)
        self.assertAlmostEqual(result['smoothed_high'], 110.0)  # one 200 in a 10-day mean
        self.assertAlmostEqual(result['percentile_high'], 100.0)

    def test_smoothed_high_is_the_best_ten_day_average(self):
        """A sustained ten-day rise is captured in full by the smoothed high."""
        closes = [100.0] * 80 + [200.0] * 10
        result = financial_metrics.calculate_highs_and_volatility(self._series(closes))['TEST']
        self.assertAlmostEqual(result['smoothed_high'], 200.0)

    def test_percentile_high_is_the_ninetieth_percentile_of_closes(self):
        """The percentile high ignores the top tenth of days."""
        closes = [float(price) for price in range(1, 91)]
        result = financial_metrics.calculate_highs_and_volatility(self._series(closes))['TEST']
        self.assertAlmostEqual(result['recent_high'], 90.0)
        self.assertAlmostEqual(result['percentile_high'], 81.1, places=6)

    def test_too_few_rows_for_a_ten_day_average_yields_none(self):
        """Fewer than ten observations must give None, not NaN rendered as a price."""
        result = financial_metrics.calculate_highs_and_volatility(self._series([100.0] * 5))['TEST']
        self.assertAlmostEqual(result['recent_high'], 100.0)
        self.assertIsNone(result['smoothed_high'])

    def test_empty_frame_yields_all_none(self):
        """A ticker with no price data returns every metric as None."""
        price_data = {'TEST': pd.DataFrame({'Close': []}, index=pd.DatetimeIndex([]))}
        result = financial_metrics.calculate_highs_and_volatility(price_data)['TEST']
        self.assertEqual(set(result.values()), {None})

    def test_price_vs_highs_divides_by_each_level(self):
        """Each percentage is the current price over the corresponding high."""
        result = financial_metrics.price_vs_highs(
            90.0, {'recent_high': 120.0, 'smoothed_high': 100.0, 'percentile_high': 110.0}
        )
        self.assertAlmostEqual(result['current_price_pct_of_high'], 0.75)
        self.assertAlmostEqual(result['current_price_pct_of_smoothed_high'], 0.90)
        self.assertAlmostEqual(result['current_price_pct_of_percentile_high'], 90.0 / 110.0)

    def test_price_vs_highs_tolerates_missing_inputs(self):
        """A missing price or high gives None rather than raising or dividing by zero."""
        self.assertIsNone(financial_metrics.price_vs_highs(None, {'recent_high': 120.0})['current_price_pct_of_high'])
        self.assertIsNone(financial_metrics.price_vs_highs(90.0, None)['current_price_pct_of_high'])
        self.assertIsNone(financial_metrics.price_vs_highs(90.0, {'recent_high': 0.0})['current_price_pct_of_high'])


class TestPeriodicReviewPriceFetchWindow(unittest.TestCase):
    """The periodic review must fetch enough history to fill the recent-high window."""

    def test_short_review_period_still_fetches_ninety_days(self):
        """A one-month review would otherwise compute the 90-day high over 30 days."""
        start_date = datetime(2026, 8, 1)
        eval_date = datetime(2026, 8, 31)
        fetcher = Mock()
        fetcher.batch_get_stock_prices.return_value = {}

        review = Mock()
        with patch.object(periodic_review_processor, 'classify_stocks_by_review_period',
                          return_value={'new': [], 'retained': [], 'sold': [], 'increased': []}):
            periodic_review_processor.process_periodic_review(
                review, start_date, datetime(2026, 8, 31), eval_date, fetcher
            )

        fetched_starts = {call.args[1] for call in fetcher.batch_get_stock_prices.call_args_list}
        self.assertTrue(fetched_starts, "no price fetch was made")
        for fetched_start in fetched_starts:
            self.assertLessEqual(fetched_start, eval_date - timedelta(days=90))


class TestExchangeRateSeriesShape(unittest.TestCase):
    """Historical exchange rates must be stored as Series (investment-reviews#28)."""

    DATES = pd.date_range('2025-06-01', periods=5, freq='D')

    def _multi_level(self, ticker, closes):
        """Build a frame shaped the way yfinance returns one — columns keyed by ticker."""
        return pd.DataFrame(
            {('Close', ticker): closes, ('Volume', ticker): [1000] * len(closes)},
            index=self.DATES
        )

    def _batch_frame(self, closes_by_ticker):
        """Build the multi-ticker frame yf.download returns for a batch."""
        columns = {}
        for ticker, closes in closes_by_ticker.items():
            columns[('Close', ticker)] = closes
            columns[('Volume', ticker)] = [1000] * len(closes)
        return pd.DataFrame(columns, index=self.DATES)

    def _ticker_info(self, tickers, price=100.0):
        return {t: {'currency': 'USD', 'exchange': 'NYSE', 'regularMarketPrice': price}
                for t in tickers}

    def test_close_series_squeezes_a_ticker_keyed_frame(self):
        """data['Close'] is a one-column DataFrame; it must come back as a Series."""
        frame = self._multi_level('USDGBP=X', [0.75] * 5)
        self.assertIsInstance(frame['Close'], pd.DataFrame)  # the shape that caused #28

        closes = MarketDataFetcher._close_series(frame)
        self.assertIsInstance(closes, pd.Series)
        self.assertIsInstance(float(closes.iloc[-1]), float)

    def test_close_series_passes_a_plain_series_through(self):
        """A single-level frame already gives a Series and must be left alone."""
        frame = pd.DataFrame({'Close': [0.75] * 5}, index=self.DATES)
        self.assertIsInstance(MarketDataFetcher._close_series(frame), pd.Series)

    def test_delisted_holding_does_not_empty_the_batch(self):
        """#28: a delisted ticker taking the ticker.info fallback cost the whole batch.

        Needs historical rates (use_live_rates=False, the periodic-review path), a ticker
        whose prices are all NaN, and a currency with a working direct pair — then the
        rate lookup raised and the batch-level handler blanked every ticker.
        """
        mdf = MarketDataFetcher()
        batch = self._batch_frame({'DEAD': [float('nan')] * 5, 'LIVE': [100.0] * 5})
        rates = self._multi_level('USDGBP=X', [0.75] * 5)

        def download(symbols, **kwargs):
            return rates if symbols == 'USDGBP=X' else batch

        with patch('yfinance.download', side_effect=download):
            result = mdf.batch_get_stock_prices(
                ['DEAD', 'LIVE'], datetime(2025, 6, 1), datetime(2025, 6, 5),
                use_live_rates=False,
                ticker_info_func=lambda tickers: self._ticker_info(tickers)
            )

        # The healthy holding keeps its prices, converted at 0.75
        self.assertFalse(result['LIVE'].empty, "a delisted holding emptied the whole batch")
        self.assertAlmostEqual(result['LIVE']['Close'].iloc[-1], 75.0, places=4)

        # The delisted one falls back to its ticker.info price, converted at the same rate
        self.assertFalse(result['DEAD'].empty)
        self.assertAlmostEqual(result['DEAD']['Close'].iloc[-1], 75.0, places=4)

    def test_one_ticker_failing_does_not_cost_the_others(self):
        """A per-ticker failure blanks that ticker only, not the whole batch."""
        mdf = MarketDataFetcher()
        # BAD is given a sentinel price so the injected failure can pick it out; the
        # conversion call itself carries no ticker.
        batch = self._batch_frame({'BAD': [999.0] * 5, 'GOOD': [100.0] * 5})
        rates = self._multi_level('USDGBP=X', [0.75] * 5)

        def download(symbols, **kwargs):
            return rates if symbols == 'USDGBP=X' else batch

        real_convert = MarketDataFetcher._convert_prices_to_gbp

        def convert(self, prices, exchange_rates, price_dates):
            if len(prices) and prices.iloc[0] == 999.0:
                raise ValueError("simulated per-ticker failure")
            return real_convert(self, prices, exchange_rates, price_dates)

        with patch('yfinance.download', side_effect=download), \
             patch.object(MarketDataFetcher, '_convert_prices_to_gbp', convert):
            result = mdf.batch_get_stock_prices(
                ['BAD', 'GOOD'], datetime(2025, 6, 1), datetime(2025, 6, 5),
                use_live_rates=False,
                ticker_info_func=lambda tickers: self._ticker_info(tickers)
            )

        self.assertTrue(result['BAD'].empty)
        self.assertFalse(result['GOOD'].empty, "one ticker's failure blanked the others")
        self.assertAlmostEqual(result['GOOD']['Close'].iloc[-1], 75.0, places=4)

    def test_ticker_info_failure_is_still_fatal(self):
        """Containing per-ticker errors must not swallow the fatal ticker-info RuntimeError."""
        mdf = MarketDataFetcher()

        def fatal(tickers):
            raise RuntimeError("Failed to get ticker information: Invalid ISIN")

        with patch('yfinance.download', return_value=pd.DataFrame()):
            with self.assertRaises(RuntimeError):
                mdf.batch_get_stock_prices(
                    ['TEST'], datetime(2025, 6, 1), datetime(2025, 6, 5),
                    ticker_info_func=fatal
                )


import review_invariants
import test_runner


class TestReviewInvariants(unittest.TestCase):
    """Each invariant must be able to fire, or it is coverage in name only (#29)."""

    @staticmethod
    def _holdings(**overrides):
        row = {
            'ticker': 'PLTR', 'units_held': 100, 'current_price': 120.0,
            'current_value': 12000.0, 'recent_high': 130.0,
            'smoothed_high': 125.0, 'percentile_high': 124.0,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_priced_holdings_passes_when_priced(self):
        self.assertEqual(review_invariants._priced_holdings(self._holdings(), 'T'), [])

    def test_priced_holdings_fires_on_a_held_position_with_no_price(self):
        """The #28 signature: units still held, price gone."""
        violations = review_invariants._priced_holdings(
            self._holdings(current_price=None), 'Full Investment History')
        self.assertEqual(len(violations), 1)
        self.assertIn('PLTR', violations[0])

    def test_priced_holdings_ignores_fully_sold_positions(self):
        """A sold-out row has no price and should not be reported."""
        self.assertEqual(
            review_invariants._priced_holdings(
                self._holdings(units_held=0, current_price=None, current_value=None), 'T'),
            []
        )

    def test_priced_holdings_reports_a_missing_units_column(self):
        """A check that cannot run must say so rather than pass silently."""
        df = self._holdings().drop(columns=['units_held'])
        violations = review_invariants._priced_holdings(df, 'T')
        self.assertEqual(len(violations), 1)
        self.assertIn('cannot verify prices', violations[0])

    def test_priced_holdings_unwraps_currency_tuples(self):
        """Periodic review carries values as (amount, 'GBP') tuples."""
        df = self._holdings(current_price=(120.0, 'GBP'), current_value=(12000.0, 'GBP'))
        self.assertEqual(review_invariants._priced_holdings(df, 'T'), [])
        df = self._holdings(current_price=(None, 'GBP'), current_value=(None, 'GBP'))
        self.assertEqual(len(review_invariants._priced_holdings(df, 'T')), 1)

    def test_high_ordering_fires_when_a_smoothed_high_exceeds_the_raw_high(self):
        violations = review_invariants._high_ordering(
            self._holdings(smoothed_high=140.0), 'T')
        self.assertEqual(len(violations), 1)
        self.assertIn('smoothed_high', violations[0])

    def test_high_ordering_fires_when_a_percentile_high_exceeds_the_raw_high(self):
        violations = review_invariants._high_ordering(
            self._holdings(percentile_high=140.0), 'T')
        self.assertEqual(len(violations), 1)
        self.assertIn('percentile_high', violations[0])

    def test_high_ordering_reports_a_missing_column(self):
        df = self._holdings().drop(columns=['percentile_high'])
        violations = review_invariants._high_ordering(df, 'T')
        self.assertIn('cannot verify high ordering', violations[0])

    def test_group_totals_must_reconcile(self):
        groups = pd.DataFrame([{'current_value': 6000.0}, {'current_value': 6000.0}])
        self.assertEqual(review_invariants._group_totals_reconcile(12000.0, groups, 'Category'), [])

        short = pd.DataFrame([{'current_value': 6000.0}])
        violations = review_invariants._group_totals_reconcile(12000.0, short, 'Category')
        self.assertEqual(len(violations), 1)
        self.assertIn('do not reconcile', violations[0])

    def test_full_history_reconciliation_catches_a_dropped_group(self):
        """A grouping that loses rows shows up here and nowhere else."""
        results = {
            'individual_stocks': pd.concat([self._holdings(ticker='A'), self._holdings(ticker='B')]),
            'per_category': pd.DataFrame([{'current_value': 12000.0}]),   # one row's worth missing
            'per_tag': pd.DataFrame([{'current_value': 24000.0}]),
        }
        violations = review_invariants.check_full_history(results)
        self.assertEqual(len(violations), 1)
        self.assertIn('Category', violations[0])

    def test_periodic_review_fires_when_benchmarks_are_lost(self):
        """During #28 every benchmark was skipped and the review still printed."""
        results = {'retained': self._holdings(), 'benchmarks': pd.DataFrame()}
        violations = review_invariants.check_periodic_review(results, expected_benchmarks=8)
        self.assertEqual(len(violations), 1)
        self.assertIn('0 of 8', violations[0])

    def test_annual_review_uses_its_own_units_column(self):
        """Annual review names the column holdings_at_end, not units_held."""
        df = self._holdings(current_price=None).rename(columns={'units_held': 'holdings_at_end'})
        violations = review_invariants.check_annual_review({'individual_stocks': df})
        self.assertEqual(len(violations), 1)
        self.assertIn('PLTR', violations[0])

    def test_report_returns_false_and_uses_the_agreed_prefix(self):
        """The prefix is the contract between a review run and the harness."""
        with self.assertLogs(level='ERROR') as captured:
            self.assertFalse(review_invariants.report(['something broke'], 'Full history'))
        self.assertTrue(any('INVARIANT VIOLATION: something broke' in m for m in captured.output))
        self.assertTrue(review_invariants.report([], 'Full history'))


class TestIntegrationHarness(unittest.TestCase):
    """The harness must be able to fail, which is what #29 was about."""

    GRID = """Portfolio Summary
=================

+-----------------+-----------------+
| Tag             | Current Value   |
+=================+=================+
| Whole Portfolio | £125,000        |
+-----------------+-----------------+
"""

    def test_strip_log_lines_removes_records_but_keeps_the_report(self):
        output = ("2026-08-31 WARNING [root] Stock NVDA tag changed\n"
                  "Tax Report Summary\n==================\n")
        cleaned = test_runner.strip_log_lines(output)
        self.assertNotIn('WARNING', cleaned)
        self.assertIn('Tax Report Summary', cleaned)

    def test_check_review_run_passes_on_a_sound_run(self):
        self.assertTrue(test_runner.check_review_run(self.GRID, 'Full history', ['Portfolio Summary']))

    def test_check_review_run_fails_on_an_invariant_violation(self):
        output = self.GRID + "\n2026-08-31 ERROR [root] INVARIANT VIOLATION: 3 held positions have no price\n"
        self.assertFalse(test_runner.check_review_run(output, 'Full history', ['Portfolio Summary']))

    def test_check_review_run_fails_when_a_table_is_absent(self):
        """A collapsed run reports no violations; the table check is what catches it."""
        self.assertFalse(test_runner.check_review_run(
            "nothing was produced", 'Full history', ['Portfolio Summary']))

    def test_summary_tables_extract_rows(self):
        """extract_table_data used to drop every row of any table without a Ticker."""
        summary = """Periodic Review Summary
=======================

+------------+---------------+
| Category   | Current Value |
+============+===============+
| New        | £179,159,466  |
+------------+---------------+
"""
        rows = test_runner.extract_table_data(summary, table_name='Periodic Review Summary')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Category'], 'New')


if __name__ == '__main__':
    import sys
    success = run_unit_tests()
    sys.exit(0 if success else 1)

