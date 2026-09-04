#!/usr/bin/env python3
"""
Unit tests for critical functionality in the investment review system.

Tests cover:
1. Currency conversion logic
2. Ticker conversion handling
3. YF API error handling
"""

import os
import sys
import logging
import shutil
import subprocess
import tempfile
import unittest
from logger import logger
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime
from portfolio_analysis import PortfolioAnalysis
from portfolio_review import StockTransaction
import transaction_processor
import update_google_sheet
from google_sheets_client import GoogleSheetsClient
import check_notes
import ticker_mapping
import yaml
import pdf_parser
import portfolio_review
import reconcile_tags
from portfolio_review import PortfolioReview
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

    def test_batched_download_padding_rows_are_dropped(self):
        """A ticker's frame must carry only the days that ticker traded.

        yf.download() indexes the batch by the union of every ticker's trading calendar,
        so a US holding gains a NaN row for each day the LSE was open and the NYSE was
        not.  Those rows are not observations, and leaving them in the cached frame makes
        every row-counting consumer read a market holiday as a trading day
        (investment-reviews#34).
        """
        mdf = MarketDataFetcher()

        with patch('yfinance.download') as mock_download, \
             patch('yfinance.Tickers') as mock_tickers:

            # US.L trades every day; US does not trade on the 2nd - the UK holiday shape.
            dates = pd.date_range('2025-10-01', periods=5)
            mock_data = pd.DataFrame({
                ('Close', 'UK.L'): [10.0, 10.5, 11.0, 10.8, 11.2],
                ('Close', 'US'): [20.0, np.nan, 21.0, 20.8, 21.2],
                ('Volume', 'UK.L'): [1000, 1100, 1200, 1150, 1250],
                ('Volume', 'US'): [1000, 0, 1200, 1150, 1250],
            }, index=dates)
            mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
            mock_download.return_value = mock_data

            uk_ticker, us_ticker = Mock(), Mock()
            uk_ticker.info = {'currency': 'GBP', 'exchange': 'LSE'}
            us_ticker.info = {'currency': 'GBP', 'exchange': 'NYQ'}
            mock_tickers_obj = Mock()
            mock_tickers_obj.tickers = {'UK.L': uk_ticker, 'US': us_ticker}
            mock_tickers.return_value = mock_tickers_obj

            result = mdf.batch_get_stock_prices(
                ['UK.L', 'US'], datetime(2025, 10, 1), datetime(2025, 10, 16)
            )

        self.assertEqual(len(result['UK.L']), 5)
        self.assertEqual(len(result['US']), 4, "the non-trading day is still in the frame")
        self.assertFalse(result['US']['Close'].isna().any())
        self.assertNotIn(pd.Timestamp('2025-10-02'), result['US'].index)


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

    def _series_with_gap(self, closes, missing_offsets):
        """Build a frame where the given offsets from the end carry no close.

        This is the shape a batched download produces for a US holding: the index is the
        union of every ticker's calendar, so days the LSE traded and the NYSE did not
        appear as rows with a NaN close (investment-reviews#34).
        """
        price_data = self._series(closes)
        frame = price_data['TEST']
        for offset in missing_offsets:
            frame.iloc[len(frame) - 1 - offset, frame.columns.get_loc('Close')] = float('nan')
        return price_data

    def test_a_non_trading_day_does_not_void_the_windows_around_it(self):
        """A NaN row must drop out, not blank every window that spans it.

        Left in place it makes `rolling` return NaN for the ten windows following it, so a
        peak fortnight straddling a market holiday is discarded and the smoothed high
        falls back to some lower window elsewhere in the period.
        """
        # Eleven days at the peak, one of them a market holiday: ten real observations.
        closes = [100.0] * 79 + [200.0] * 11
        with_gap = self._series_with_gap(list(closes), missing_offsets=[5])
        result = financial_metrics.calculate_highs_and_volatility(with_gap)['TEST']
        self.assertAlmostEqual(result['smoothed_high'], 200.0)

    def test_a_gap_shortens_the_series_rather_than_the_window(self):
        """Ten observations are averaged, never nine treated as ten.

        With the gap removed the ten most recent observations reach one day further back,
        so the mean is over ten real closes and the 100.0 before the run is included.
        """
        closes = [100.0] * 80 + [200.0] * 10
        with_gap = self._series_with_gap(list(closes), missing_offsets=[3])
        result = financial_metrics.calculate_highs_and_volatility(with_gap)['TEST']
        # Nine 200s and one 100 is the best available ten-observation mean.
        self.assertAlmostEqual(result['smoothed_high'], 190.0)

    def test_all_closes_missing_yields_all_none(self):
        """A frame of nothing but padding rows has no observations to report."""
        closes = [100.0] * 30
        with_gap = self._series_with_gap(list(closes), missing_offsets=range(30))
        result = financial_metrics.calculate_highs_and_volatility(with_gap)['TEST']
        self.assertIsNone(result['recent_high'])
        self.assertIsNone(result['smoothed_high'])

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


class TestContractNoteLayout(unittest.TestCase):
    """The layout of a contract note is read from the note (investment-reviews#36)."""

    # The HL pence layout, verbatim in shape: header, ISIN/code, name, then the row.
    PENCE_LINES = [
        'Quantity Security Price Consideration',
        '{isin} STOCK CODE: {code}',
        '{name}',
        '1,442.00 1385.9867 19,985.93',
        'Ptg NPV',
    ]

    def _pence_note(self, isin, code='FEML', name='Fidelity Emerging Markets Limited'):
        return [l.format(isin=isin, code=code, name=name) for l in self.PENCE_LINES]

    def test_pence_row_is_read_whatever_the_domicile(self):
        """Guernsey, Jersey and Great Britain are the same document.

        A London-listed, sterling, pence-priced investment trust is read the same way
        wherever it happens to be domiciled.  Dispatching on the ISIN country code sent
        GG to the foreign-currency reader and lost the price entirely.
        """
        for isin in ('GG00B4L0PD47', 'JE00B1VS3770', 'GB00B10RZP78', 'IM00B1Z40972'):
            with self.subTest(isin=isin):
                result = {}
                pdf_parser.parse_pence_row_details(self._pence_note(isin), 2, result)
                self.assertAlmostEqual(result['price'], 13.859867)
                self.assertAlmostEqual(result['total_amount'], 19985.93)
                self.assertAlmostEqual(result['num_shares'], 1442.0)
                self.assertEqual(result['currency'], 'GBP')

    def test_a_row_that_does_not_multiply_out_is_not_a_pence_row(self):
        """The arithmetic is what identifies the layout, so three numbers are not enough.

        Without the check, any three numbers near a stock name would be read as quantity,
        pence and consideration, inventing a price for a note in some other layout.
        """
        lines = list(self._pence_note('GG00B4L0PD47'))
        lines[3] = '1,442.00 1385.9867 4,004.00'  # consideration does not match
        result = {}
        pdf_parser.parse_pence_row_details(lines, 2, result)
        self.assertIsNone(result.get('price'))

    def test_a_two_number_row_is_not_a_pence_row(self):
        """A row with no consideration cannot prove itself, so it is not claimed."""
        lines = list(self._pence_note('GG00B4L0PD47'))
        lines[3] = '1,442.00 1385.9867'
        result = {}
        pdf_parser.parse_pence_row_details(lines, 2, result)
        self.assertIsNone(result.get('price'))

    def test_foreign_currency_layout_still_reads_its_own_price(self):
        """The other layout is unchanged: price in the stock's currency, plus an FX rate."""
        lines = [
            'Quantity Security Price Consideration',
            'US0378331005 STOCK CODE: AAPL',
            'Apple Inc',
            '100.00',
            'Price (USD) 210.50',
            'Exchange rate 1.2750',
            'GBP 16,509.80',
        ]
        result = {}
        pdf_parser.parse_foreign_currency_details(lines, 2, result)
        self.assertAlmostEqual(result['price'], 210.50)
        self.assertEqual(result['currency'], 'USD')
        self.assertAlmostEqual(result['exchange_rate'], 1.2750)


class TestLondonListedExchangeSuffix(unittest.TestCase):
    """London listings are reached as .L whatever the ISIN's domicile (#39)."""

    # (ticker, ISIN) for the holdings that reached Yahoo as bare tickers and could not be
    # priced: Irish and Guernsey domiciles absent from EXCHANGE_SUFFIX_MAP.
    LONDON_LISTED = [
        ('BTEK', 'IE00BYXG2H39'),
        ('DFND', 'IE00BYXG2H39'),
        ('FEML', 'GG00B4L0PD47'),
        ('IWFV', 'IE00BYXG2H39'),
        ('LTAM', 'IE00BYXG2H39'),
        ('ARMR', 'IE00BYXG2H39'),
        ('WDEF', 'IE0007N9SZH3'),
        ('ARMG', 'IE000JCW3DZ3'),
    ]

    def test_a_bare_ticker_can_resolve_to_an_entirely_different_fund(self):
        '''ARMG on the LSE is the Global X Defence Tech UCITS ETF (GBP line).

        Bare ARMG is the Leverage Shares 2X Long ARM Daily ETF on Nasdaq — a different
        fund tracking a different underlying, and geared. Unlike WDEF (#46), where the
        wrong pick was another currency line of the same fund, here the price bears no
        relation to the holding at all: it reported a 49% loss on a flat position, with
        180% annualised volatility (investment-reviews#50).
        '''
        self.assertEqual(pdf_parser.get_exchange_suffix('IE000JCW3DZ3', 'ARMG'), '.L')

    def test_a_multi_currency_listing_resolves_to_the_line_actually_held(self):
        '''WDEF is a EUR line on the LSE; bare WDEF is a USD line on NYSE Arca.

        Both are real instruments and both return a plausible price, so picking the wrong
        one is not an error anywhere — it is an 18% understatement reported as a loss
        (investment-reviews#46).
        '''
        self.assertEqual(pdf_parser.get_exchange_suffix('IE0007N9SZH3', 'WDEF'), '.L')

    def test_london_listings_resolve_to_the_london_suffix(self):
        for ticker, isin in self.LONDON_LISTED:
            with self.subTest(ticker=ticker):
                self.assertEqual(pdf_parser.get_exchange_suffix(isin, ticker), '.L')

    def test_the_country_map_still_applies_to_everything_else(self):
        """The per-ticker entries are an override, not a replacement."""
        self.assertEqual(pdf_parser.get_exchange_suffix('US0378331005', 'AAPL'), '')
        self.assertEqual(pdf_parser.get_exchange_suffix('GB00B10RZP78', 'HSBA'), '.L')
        self.assertEqual(pdf_parser.get_exchange_suffix('DE0007164600', 'SAP'), '.DE')

    def test_an_unmapped_domicile_still_yields_no_suffix(self):
        """Nothing here fixes the general case; that is investment-reviews#40."""
        self.assertEqual(pdf_parser.get_exchange_suffix('GG00B4L0PD47', 'NEWTRUST'), '')


class TestUnreadableContractNote(unittest.TestCase):
    """An unvaluable note is named, not turned into a transaction (investment-reviews#36)."""

    def _scan(self, filenames, raiser):
        """Scan a throwaway history tree whose notes all fail to parse."""
        with tempfile.TemporaryDirectory() as base:
            year_dir = os.path.join(base, 'Taxable', '2026', 'Some tag')
            os.makedirs(year_dir)
            for name in filenames:
                open(os.path.join(year_dir, name), 'w').close()
            with patch('portfolio_review.parse_stock_transaction_pdf', side_effect=raiser):
                return PortfolioReview(base, 'full-history')

    def test_scan_fails_naming_every_unreadable_note(self):
        """One pass names them all, rather than sending the operator round again per note."""
        names = ['B1_BOUGHT_One.pdf', 'B2_BOUGHT_Two.pdf']

        def raiser(path):
            raise pdf_parser.ContractNoteParseError(f"Could not read price from {path}")

        # NoteParseError, not ContractNoteParseError: since #54 the aggregate covers
        # corporate-action notes too, so the summary is raised as the shared base type.
        with self.assertRaises(pdf_parser.NoteParseError) as caught:
            self._scan(names, raiser)
        message = str(caught.exception)
        self.assertIn('2 note(s)', message)
        for name in names:
            self.assertIn(name, message)

    def test_an_unreadable_note_is_not_swallowed_as_a_generic_error(self):
        """The pre-existing catch-all logged and carried on, yielding a short portfolio."""
        def raiser(path):
            raise pdf_parser.ContractNoteParseError(f"Could not read price from {path}")

        with self.assertRaises(pdf_parser.NoteParseError):
            self._scan(['B1_BOUGHT_One.pdf'], raiser)

    def test_other_parse_errors_still_only_skip_that_file(self):
        """Only an unvaluable note is fatal; an unreadable file keeps its old behaviour."""
        def raiser(path):
            raise ValueError('not a PDF at all')

        review = self._scan(['B1_BOUGHT_One.pdf'], raiser)
        self.assertIsNotNone(review)


class TestReconcileTagPaths(unittest.TestCase):
    """Where the directory structure files a note (investment-reviews#42)."""

    ROOT = '/notes'

    def test_parses_category_year_and_tag(self):
        self.assertEqual(
            reconcile_tags.parse_note_path(self.ROOT, '/notes/Taxable/2026/Defence/B1_BOUGHT_X.pdf'),
            ('taxable', '2026', 'Defence'))

    def test_a_note_directly_under_the_year_has_no_tag(self):
        self.assertEqual(
            reconcile_tags.parse_note_path(self.ROOT, '/notes/ISA/2026/B1_BOUGHT_X.pdf'),
            ('isa', '2026', None))

    def test_a_four_digit_directory_is_a_year_not_a_tag(self):
        """'2026' below the year would otherwise be read as a tag called 2026."""
        self.assertEqual(
            reconcile_tags.parse_note_path(self.ROOT, '/notes/ISA/2026/2026/B1_BOUGHT_X.pdf'),
            ('isa', '2026', None))

    def test_agrees_with_the_scanner(self):
        """The tool and PortfolioReview must not disagree about where a note is filed."""
        review = PortfolioReview.__new__(PortfolioReview)
        for path in ('/notes/Taxable/2026/H&L fund recommendations/B448671254_BOUGHT_F.pdf',
                     '/notes/ISA/2010/2010 generic/B181267631_BOUGHT_I.pdf',
                     '/notes/Pension/2024/B1_BOUGHT_X.pdf'):
            with self.subTest(path=path):
                self.assertEqual(reconcile_tags.parse_note_path(self.ROOT, path),
                                 review._extract_account_type_and_year(path))

    def test_only_note_files_are_matched(self):
        self.assertTrue(reconcile_tags.is_note('B1_BOUGHT_X.pdf'))
        self.assertTrue(reconcile_tags.is_note('trades.CSV'))
        self.assertTrue(reconcile_tags.is_note('export.mhtml'))
        self.assertFalse(reconcile_tags.is_note('.DS_Store'))
        self.assertFalse(reconcile_tags.is_note('notes.txt'))


class TestReconcileTagMoves(unittest.TestCase):
    """Moving a stock's notes across three copies (investment-reviews#42)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.locations = []
        for name in ('icloud', 'staging', 'jarvis'):
            root = os.path.join(self._tmp.name, name)
            os.makedirs(root)
            self.locations.append(reconcile_tags.LocalLocation(name, root))

    def _place(self, location, category, year, tag, filename):
        directory = os.path.join(location.root, category, year, tag) if tag else \
            os.path.join(location.root, category, year)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, filename)
        open(path, 'w').close()
        return path

    def _find(self, fragment):
        notes = []
        for location in self.locations:
            notes.extend(location.find(fragment))
        return notes

    def test_retag_keeps_the_directory_casing_on_disk(self):
        """'ISA' parses to 'isa'; a destination spelled from the parsed form forks the tree."""
        location = self.locations[0]
        self._place(location, 'ISA', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        note = location.find('BOUGHT_X')[0]
        destination = location.retag(note, 'Defence')
        self.assertEqual(destination,
                         os.path.join(location.root, 'ISA', '2026', 'Defence', 'B1_BOUGHT_X.pdf'))

    def test_a_note_with_no_tag_gains_one(self):
        location = self.locations[0]
        self._place(location, 'ISA', '2026', None, 'B1_BOUGHT_X.pdf')
        note = location.find('BOUGHT_X')[0]
        self.assertIsNone(note.tag)
        self.assertEqual(location.retag(note, 'Defence'),
                         os.path.join(location.root, 'ISA', '2026', 'Defence', 'B1_BOUGHT_X.pdf'))

    def test_moves_are_ordered_upstream_first(self):
        """iCloud, then staging, then jarvis.

        The first hop never deletes and the second mirrors, so a note left upstream is
        copied back over the move within the hour.  The order is the safety property.
        """
        for location in self.locations:
            self._place(location, 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'Defence')
        self.assertEqual([location.name for location, _, _ in moves],
                         ['icloud', 'staging', 'jarvis'])

    def test_notes_already_under_the_target_tag_are_not_moved(self):
        self._place(self.locations[0], 'Taxable', '2026', 'Defence', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[1], 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'Defence')
        self.assertEqual([location.name for location, _, _ in moves], ['staging'])

    def test_a_split_within_one_location_is_reported(self):
        self._place(self.locations[0], 'Taxable', '2025', 'Old', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[0], 'Taxable', '2026', 'New', 'B2_BOUGHT_X.pdf')
        problems = reconcile_tags.disagreements(self._find('BOUGHT_X'), ['icloud', 'staging', 'jarvis'])
        self.assertTrue(any('split across 2 tags' in p for p in problems), problems)

    def test_a_move_applied_to_only_some_locations_is_reported(self):
        """The state a half-finished move leaves, which the syncs then spread."""
        self._place(self.locations[0], 'Taxable', '2026', 'Defence', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[1], 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[2], 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        problems = reconcile_tags.disagreements(self._find('BOUGHT_X'), ['icloud', 'staging', 'jarvis'])
        self.assertTrue(any('filed differently in different locations' in p for p in problems), problems)

    def test_consistent_filing_reports_nothing(self):
        for location in self.locations:
            self._place(location, 'Taxable', '2026', 'Defence', 'B1_BOUGHT_X.pdf')
        self.assertEqual(reconcile_tags.disagreements(self._find('BOUGHT_X'),
                                                      ['icloud', 'staging', 'jarvis']), [])

    def test_the_same_stock_may_hold_different_tags_in_different_categories(self):
        """The scanner keys the tag on (ticker, category), so this is not a fault."""
        for location in self.locations:
            self._place(location, 'ISA', '2026', 'Defence', 'B1_BOUGHT_X.pdf')
            self._place(location, 'Taxable', '2026', 'Nuclear', 'B2_BOUGHT_X.pdf')
        self.assertEqual(reconcile_tags.disagreements(self._find('BOUGHT_X'),
                                                      ['icloud', 'staging', 'jarvis']), [])

    def test_moving_leaves_nothing_behind_in_any_location(self):
        for location in self.locations:
            self._place(location, 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'Defence')
        for location, note, destination in moves:
            location.move(note.path, destination)

        after = self._find('BOUGHT_X')
        self.assertEqual(len(after), 3)
        self.assertEqual({note.tag for note in after}, {'Defence'})
        self.assertEqual(reconcile_tags.disagreements(after, ['icloud', 'staging', 'jarvis']), [])
        for location in self.locations:
            self.assertFalse(os.path.exists(
                os.path.join(location.root, 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')))

    def test_a_move_onto_an_existing_file_refuses_rather_than_overwrites(self):
        location = self.locations[0]
        self._place(location, 'Taxable', '2026', 'Old', 'B1_BOUGHT_X.pdf')
        self._place(location, 'Taxable', '2026', 'Defence', 'B1_BOUGHT_X.pdf')
        note = [n for n in location.find('BOUGHT_X') if n.tag == 'Old'][0]
        with self.assertRaises(RuntimeError):
            location.move(note.path, location.retag(note, 'Defence'))


class TestReconcileTagPresence(unittest.TestCase):
    """A note in some copies and not others (investment-reviews#61)."""

    LOCATIONS = ['icloud', 'staging', 'jarvis']

    def _notes(self, placements):
        """placements: {location: [filenames]}"""
        return [reconcile_tags.Note(location, f'/{location}/ISA/2026/Nuclear/{name}',
                                    'isa', '2026', 'Nuclear', name)
                for location, names in placements.items() for name in names]

    def test_a_note_only_upstream_is_waiting_for_a_sync(self):
        """The case that reported 'Consistent' while the counts read 3, 2, 2.

        Tags agreed, so the tag check had nothing to say — but a note filed minutes ago
        and not yet mirrored is exactly what someone runs this to find out.
        """
        notes = self._notes({'icloud': ['a.pdf', 'b.pdf'],
                             'staging': ['a.pdf'], 'jarvis': ['a.pdf']})
        stale, pending = reconcile_tags.presence_differences(notes, self.LOCATIONS)
        self.assertEqual(stale, [], 'waiting for a sync is not a fault')
        self.assertEqual(len(pending), 2)
        self.assertTrue(all('b.pdf' in line for line in pending))

    def test_a_note_in_staging_but_not_icloud_is_a_fault(self):
        """ditto never deletes, so staging keeps pushing it to jarvis indefinitely."""
        notes = self._notes({'icloud': [], 'staging': ['ghost.pdf'], 'jarvis': ['ghost.pdf']})
        stale, _ = reconcile_tags.presence_differences(notes, self.LOCATIONS)
        self.assertEqual(len(stale), 1)
        self.assertIn('ghost.pdf', stale[0])
        self.assertIn('keep pushing', stale[0])

    def test_a_note_only_on_jarvis_removes_itself(self):
        """The second hop mirrors, so anything not in staging is deleted on the next run."""
        notes = self._notes({'icloud': [], 'staging': [], 'jarvis': ['leftover.pdf']})
        stale, pending = reconcile_tags.presence_differences(notes, self.LOCATIONS)
        self.assertEqual(stale, [])
        self.assertEqual(len(pending), 2)

    def test_notes_present_everywhere_report_nothing(self):
        notes = self._notes({name: ['a.pdf'] for name in self.LOCATIONS})
        self.assertEqual(reconcile_tags.presence_differences(notes, self.LOCATIONS),
                         ([], []))

    def test_a_pending_sync_does_not_fail_the_check(self):
        """--check gates a script; a note mid-sync is no reason to stop it."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        locations = []
        for name in self.LOCATIONS:
            root = os.path.join(base, name)
            directory = os.path.join(root, 'ISA', '2026', 'Nuclear')
            os.makedirs(directory)
            open(os.path.join(directory, 'a_BOUGHT_X.pdf'), 'w').close()
            locations.append(reconcile_tags.LocalLocation(name, root))
        open(os.path.join(base, 'icloud', 'ISA', '2026', 'Nuclear', 'b_BOUGHT_X.pdf'), 'w').close()

        with patch.object(reconcile_tags, 'build_locations', return_value=locations):
            self.assertEqual(reconcile_tags.main(['BOUGHT_X', '--check']), 0)


class TestReconcileTagCaseInsensitivity(unittest.TestCase):
    """Tag directories are case-insensitively unique on macOS (investment-reviews#44)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.locations = []
        for name in ('icloud', 'staging', 'jarvis'):
            root = os.path.join(self._tmp.name, name)
            os.makedirs(root)
            self.locations.append(reconcile_tags.LocalLocation(name, root))

    def _place(self, location, category, year, tag, filename):
        directory = os.path.join(location.root, category, year, tag)
        os.makedirs(directory, exist_ok=True)
        open(os.path.join(directory, filename), 'w').close()

    def _find(self, fragment):
        notes = []
        for location in self.locations:
            notes.extend(location.find(fragment))
        return notes

    def test_tags_differing_only_in_case_are_the_same_tag(self):
        self.assertTrue(reconcile_tags.same_tag('AI application layer', 'AI Application Layer'))
        self.assertTrue(reconcile_tags.same_tag('Tech', 'tech'))
        self.assertFalse(reconcile_tags.same_tag('Tech', 'Biotech'))
        self.assertFalse(reconcile_tags.same_tag(None, 'Tech'))
        self.assertTrue(reconcile_tags.same_tag(None, None))

    def test_a_note_already_under_a_case_variant_is_not_moved(self):
        """The move that aborted: the destination resolved onto the file itself."""
        self._place(self.locations[0], 'ISA', '2026', 'AI application layer', 'B1_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'AI Application Layer')
        self.assertEqual(moves, [])

    def test_the_spelling_difference_is_reported_not_applied(self):
        """Respelling renames a directory other stocks sit in, so it is not done silently."""
        self._place(self.locations[0], 'ISA', '2026', 'AI application layer', 'B1_BOUGHT_X.pdf')
        notes = self._find('BOUGHT_X')
        self.assertEqual(reconcile_tags.spelling_differences(notes, 'AI Application Layer'),
                         ['AI application layer'])
        self.assertEqual(reconcile_tags.spelling_differences(notes, 'AI application layer'), [])
        # and the directory is untouched
        self.assertTrue(os.path.isdir(
            os.path.join(self.locations[0].root, 'ISA', '2026', 'AI application layer')))

    def test_a_case_variant_does_not_count_as_a_split(self):
        """One tag spelled two ways across years is a spelling question, not two tags."""
        self._place(self.locations[0], 'ISA', '2024', 'AI Application Layer', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[0], 'ISA', '2026', 'AI application layer', 'B2_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'AI application layer')
        self.assertEqual(moves, [])


class TestReconcileTagPreflight(unittest.TestCase):
    """Nothing moves unless everything can (investment-reviews#44)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.locations = []
        for name in ('icloud', 'staging', 'jarvis'):
            root = os.path.join(self._tmp.name, name)
            os.makedirs(root)
            self.locations.append(reconcile_tags.LocalLocation(name, root))

    def _place(self, location, category, year, tag, filename):
        directory = os.path.join(location.root, category, year, tag)
        os.makedirs(directory, exist_ok=True)
        open(os.path.join(directory, filename), 'w').close()

    def _find(self, fragment):
        notes = []
        for location in self.locations:
            notes.extend(location.find(fragment))
        return notes

    def test_preflight_passes_when_every_destination_is_free(self):
        for location in self.locations:
            self._place(location, 'ISA', '2026', 'Tech', 'B1_BOUGHT_X.pdf')
        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'Defence')
        self.assertEqual(reconcile_tags.preflight(moves), [])

    def test_preflight_catches_a_taken_destination_before_anything_moves(self):
        for location in self.locations:
            self._place(location, 'ISA', '2026', 'Tech', 'B1_BOUGHT_X.pdf')
        # a different stock's note already occupies the destination name in the last location
        self._place(self.locations[2], 'ISA', '2026', 'Defence', 'B1_BOUGHT_X.pdf')

        moves = reconcile_tags.plan(self._find('BOUGHT_X'), self.locations, 'Defence')
        problems = reconcile_tags.preflight(moves)
        self.assertEqual(len(problems), 1)
        self.assertIn('jarvis', problems[0])

        # the caller aborts on a non-empty result, so the upstream files are still in place
        for location in self.locations[:2]:
            self.assertTrue(os.path.exists(
                os.path.join(location.root, 'ISA', '2026', 'Tech', 'B1_BOUGHT_X.pdf')))

    def test_preflight_compares_case_insensitively(self):
        """A destination only has to collide case-insensitively to fail on macOS."""
        self._place(self.locations[0], 'ISA', '2026', 'Tech', 'B1_BOUGHT_X.pdf')
        self._place(self.locations[0], 'ISA', '2026', 'defence', 'B1_BOUGHT_X.pdf')
        moves = [(self.locations[0], note, self.locations[0].retag(note, 'Defence'))
                 for note in self.locations[0].find('BOUGHT_X') if note.tag == 'Tech']
        self.assertEqual(len(reconcile_tags.preflight(moves)), 1)


class TestManualTransferNotes(unittest.TestCase):
    """A TRANSFER declared in a manual YAML note (investment-reviews#52)."""

    def _review(self, entries):
        """Scan a throwaway history tree containing one YAML note."""
        import yaml as _yaml
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        directory = os.path.join(base, 'ISA', '2026', 'Defense')
        os.makedirs(directory)
        with open(os.path.join(directory, 'action.yaml'), 'w') as handle:
            _yaml.safe_dump(entries, handle)
        return PortfolioReview(base, 'full-history')

    def _transactions(self, review, ticker):
        for notes in review.stock_notes.values():
            for note in (notes if isinstance(notes, list) else [notes]):
                if getattr(note, 'ticker', None) == ticker:
                    return note.transactions
        return None

    TRANSFER_IN = {
        'transaction_type': 'TRANSFER', 'ticker': 'KMAR.OL',
        'stock_name': 'Kongsberg Maritime ASA', 'date': '2026-04-23',
        'quantity': 1192, 'total_amount': 5847.00,
    }
    TRANSFER_OUT = {
        'transaction_type': 'TRANSFER', 'ticker': 'KOG.OL',
        'stock_name': 'Kongsberg Gruppen ASA', 'date': '2026-04-23',
        'quantity': 0, 'total_amount': -5847.00,
    }

    def test_a_yaml_transfer_is_recorded_as_a_transfer_not_a_sale(self):
        """Everything that was not a purchase fell through to SELL.

        The manual-transaction template documents TRANSFER, and transaction_processor
        has always understood it, but nothing could reach that branch from a note: the
        holding was recorded as a disposal and then dropped, because a stock whose first
        transaction is a SELL is excluded entirely.
        """
        transactions = self._transactions(self._review([dict(self.TRANSFER_IN)]), 'KMAR.OL')
        self.assertIsNotNone(transactions, "the transferred-in holding was dropped")
        self.assertEqual(transactions[0].transaction_type, 'TRANSFER')

    def test_a_transfer_out_is_not_recorded_as_a_disposal(self):
        """The giving leg carries a negative cost base, not sale proceeds."""
        transactions = self._transactions(self._review([dict(self.TRANSFER_OUT)]), 'KOG.OL')
        self.assertEqual(transactions[0].transaction_type, 'TRANSFER')
        self.assertAlmostEqual(transactions[0].total_amount, -5847.00)

    def test_a_demerger_pair_conserves_the_total_cost_base(self):
        """The point of modelling a demerger as paired transfers.

        A demerger does not create value, it splits an existing cost base across two
        holdings.  Booking the new shares as a zero-cost purchase would leave the old
        holding's cost base overstated by exactly the amount the new one is understated.
        """
        review = self._review([dict(self.TRANSFER_IN), dict(self.TRANSFER_OUT)])
        received = transaction_processor.calculate_transactions_through_date(
            self._transactions(review, 'KMAR.OL'), datetime(2026, 9, 1))
        given = transaction_processor.calculate_transactions_through_date(
            self._transactions(review, 'KOG.OL'), datetime(2026, 9, 1))

        self.assertAlmostEqual(received['total_invested'], 5847.00)
        self.assertAlmostEqual(given['total_invested'], -5847.00)
        self.assertAlmostEqual(received['total_invested'] + given['total_invested'], 0.0)
        self.assertAlmostEqual(received['units_held'], 1192)
        self.assertAlmostEqual(given['units_held'], 0)

    def test_neither_leg_is_counted_as_money_received(self):
        """A demerger is not a disposal, so nothing has been realised."""
        review = self._review([dict(self.TRANSFER_IN), dict(self.TRANSFER_OUT)])
        for ticker in ('KMAR.OL', 'KOG.OL'):
            with self.subTest(ticker=ticker):
                result = transaction_processor.calculate_transactions_through_date(
                    self._transactions(review, ticker), datetime(2026, 9, 1))
                self.assertAlmostEqual(result['total_received'], 0.0)


class TestCorporateActionRecognition(unittest.TestCase):
    """Which corporate action a note's filename names (investment-reviews#53)."""

    def test_demerger_is_not_a_merger(self):
        """'merger' is a substring of 'demerger', and they are opposite actions.

        The HL letter was handed to the merger parser, which models shares being
        exchanged away rather than received.
        """
        self.assertEqual(
            portfolio_review.corporate_action_in('kongsberg+gruppen+asa+-+demerger.pdf'),
            'demerger')

    def test_the_notes_already_in_the_tree_are_unchanged(self):
        """Every corporate-action note currently filed must resolve as it did before."""
        for filename, expected in (
            ('everbridge+inc+-+merger.pdf', 'merger'),
            ('jpmorgan+-+unit+class+conversion+.pdf', 'conversion'),
            ('rathbone+-+unit+class+conversion+.pdf', 'conversion'),
            ('sezzle+inc+-+subdivision.pdf', 'subdivision'),
        ):
            with self.subTest(filename=filename):
                self.assertEqual(portfolio_review.corporate_action_in(filename), expected)

    def test_separators_are_word_boundaries(self):
        """HL uses '+' and '-'; manual notes use '_'. All are boundaries."""
        for filename in ('acme+inc+-+merger.pdf', 'acme_merger_2026.pdf',
                         'acme merger.pdf', 'ACME-MERGER.PDF'):
            with self.subTest(filename=filename):
                self.assertEqual(portfolio_review.corporate_action_in(filename), 'merger')

    def test_an_action_word_inside_a_longer_word_does_not_match(self):
        """The defect in general form, not just the one instance of it."""
        self.assertIsNone(portfolio_review.corporate_action_in('acme+reconversion.pdf'))
        self.assertIsNone(portfolio_review.corporate_action_in('submerger_notes.pdf'))

    def test_an_ordinary_contract_note_names_no_action(self):
        self.assertIsNone(
            portfolio_review.corporate_action_in('B117667224_BOUGHT_Kongsberg_Gruppen_ASA.pdf'))

    def test_a_demerger_note_is_recognised_as_manually_entered(self):
        """There is no demerger parser, and the letter has no cost apportionment.

        The note is documentation; its effect is entered by hand as paired transfers
        (#52). Being unable to parse it is expected, not a fault.
        """
        self.assertIn('demerger', portfolio_review.MANUALLY_ENTERED_ACTIONS)
        for action in ('merger', 'conversion', 'subdivision'):
            with self.subTest(action=action):
                self.assertNotIn(action, portfolio_review.MANUALLY_ENTERED_ACTIONS)

    def test_a_demerger_note_is_not_sent_to_any_parser(self):
        """The whole point: it must reach none of the three corporate-action parsers."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        directory = os.path.join(base, 'ISA', '2026', 'Defense')
        os.makedirs(directory)
        open(os.path.join(directory, 'acme+plc+-+demerger.pdf'), 'w').close()

        with patch('portfolio_review.parse_merger_pdf') as merger, \
             patch('portfolio_review.parse_conversion_pdf') as conversion, \
             patch('portfolio_review.parse_subdivision_pdf') as subdivision, \
             patch('portfolio_review.parse_stock_transaction_pdf') as contract_note:
            PortfolioReview(base, 'full-history')

        merger.assert_not_called()
        conversion.assert_not_called()
        subdivision.assert_not_called()
        contract_note.assert_not_called()


class TestUnreadableCorporateAction(unittest.TestCase):
    """A corporate action the scan recognised must not vanish (investment-reviews#54)."""

    def _scan_with(self, filename, raiser):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        directory = os.path.join(base, 'ISA', '2026', 'Defense')
        os.makedirs(directory)
        open(os.path.join(directory, filename), 'w').close()
        target = {'merger': 'portfolio_review.parse_merger_pdf',
                  'subdivision': 'portfolio_review.parse_subdivision_pdf',
                  'conversion': 'portfolio_review.parse_conversion_pdf'}[
            portfolio_review.corporate_action_in(filename)]
        with patch(target, side_effect=raiser):
            return PortfolioReview(base, 'full-history')

    def test_an_unreadable_corporate_action_fails_the_scan(self):
        """It used to be one WARNING in a run that then reported success.

        An unreadable contract note omits a transaction, which shows against a broker
        statement as a wrong unit count.  An unreadable corporate action can omit an
        entire holding, and nothing reconciles the set of holdings against anything.
        """
        def raiser(path):
            raise pdf_parser.CorporateActionParseError(f"No stock name found in {path}")

        with self.assertRaises(pdf_parser.NoteParseError) as caught:
            self._scan_with('acme+inc+-+merger.pdf', raiser)
        self.assertIn('acme+inc+-+merger.pdf', str(caught.exception))

    def test_it_is_collected_alongside_unreadable_contract_notes(self):
        """One pass names everything that needs attention, of either kind."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        directory = os.path.join(base, 'ISA', '2026', 'Defense')
        os.makedirs(directory)
        for name in ('B1_BOUGHT_One.pdf', 'acme+inc+-+merger.pdf'):
            open(os.path.join(directory, name), 'w').close()

        with patch('portfolio_review.parse_stock_transaction_pdf',
                   side_effect=lambda p: (_ for _ in ()).throw(
                       pdf_parser.ContractNoteParseError(f"No price in {p}"))), \
             patch('portfolio_review.parse_merger_pdf',
                   side_effect=lambda p: (_ for _ in ()).throw(
                       pdf_parser.CorporateActionParseError(f"No stock name in {p}"))):
            with self.assertRaises(pdf_parser.NoteParseError) as caught:
                PortfolioReview(base, 'full-history')

        message = str(caught.exception)
        self.assertIn('2 note(s)', message)
        self.assertIn('B1_BOUGHT_One.pdf', message)
        self.assertIn('acme+inc+-+merger.pdf', message)

    def test_a_manually_entered_action_is_not_treated_as_a_failure(self):
        """A demerger has no parser by design, so it cannot be a parse failure.

        Failing on one would block every run permanently once the letter is filed
        alongside the manual YAML that records its effect (#53).
        """
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        directory = os.path.join(base, 'ISA', '2026', 'Defense')
        os.makedirs(directory)
        open(os.path.join(directory, 'acme+plc+-+demerger.pdf'), 'w').close()
        self.assertIsNotNone(PortfolioReview(base, 'full-history'))

    def test_the_error_names_the_corporate_action_kind(self):
        """The message has to be actionable: which note, and what was not readable."""
        for filename, kind in (('acme+inc+-+merger.pdf', 'merger'),
                               ('acme+inc+-+subdivision.pdf', 'subdivision'),
                               ('acme+inc+-+conversion.pdf', 'conversion')):
            with self.subTest(kind=kind):
                def raiser(path):
                    raise pdf_parser.CorporateActionParseError(
                        f"Could not read the {kind} note {path}")
                with self.assertRaises(pdf_parser.NoteParseError) as caught:
                    self._scan_with(filename, raiser)
                self.assertIn(kind, str(caught.exception))


class TestUnparseableNotesStopTheUpdate(unittest.TestCase):
    """Notes that could not be read must not produce a spreadsheet row (#38)."""

    MESSAGE = ("2 note(s) could not be used, so the portfolio would be understated:\n"
               "  Could not read price from /notes/ISA/2026/A.pdf\n"
               "  Could not read the merger note /notes/ISA/2026/B.pdf")

    def _updater(self, recipient='calum@example.com'):
        updater = update_google_sheet.PortfolioUpdater.__new__(
            update_google_sheet.PortfolioUpdater)
        updater.logger = logging.getLogger('test-updater')
        updater.dry_run = False
        updater.alert_delivery_ok = True
        updater.unparseable_notes = None
        updater.config = {'notifications': {'alerts': {'to': recipient} if recipient else {}}}
        return updater

    def _fenced(self, message):
        return (f"some library warning\n"
                f"{update_google_sheet.UNPARSEABLE_NOTES_BEGIN}\n{message}\n"
                f"{update_google_sheet.UNPARSEABLE_NOTES_END}\n")

    def test_the_report_is_lifted_out_of_the_surrounding_noise(self):
        """stderr also carries library warnings; only the fenced part is the report."""
        extracted = update_google_sheet._unparseable_notes_message(self._fenced(self.MESSAGE))
        self.assertEqual(extracted, self.MESSAGE)
        self.assertNotIn('library warning', extracted)

    def test_a_missing_fence_yields_everything_rather_than_nothing(self):
        """An email holding too much is recoverable; one holding nothing is not."""
        self.assertEqual(
            update_google_sheet._unparseable_notes_message("something went wrong"),
            "something went wrong")

    def test_only_the_unparseable_exit_code_is_treated_as_unparseable_notes(self):
        """Exit 3 is the specific condition; any other failure stays a general one."""
        updater = self._updater()
        updater.config['portfolio'] = {'base_dir': '/notes', 'temp_output': '/tmp/x.numbers'}

        for code, expected in ((3, update_google_sheet.UnparseableNotesError),
                               (1, RuntimeError),
                               (2, RuntimeError)):
            with self.subTest(exit_code=code):
                error = subprocess.CalledProcessError(code, ['portfolio'])
                error.stdout, error.stderr = '', self._fenced(self.MESSAGE)
                with patch('subprocess.run', side_effect=error):
                    with self.assertRaises(expected):
                        updater._run_portfolio_analysis()

    def test_the_spreadsheet_is_left_alone_and_the_report_is_emailed(self):
        """The requirement: no row, and the email is the error and nothing else."""
        updater = self._updater()
        sheets = Mock()
        updater.sheets_client = sheets

        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=update_google_sheet.UnparseableNotesError(self.MESSAGE)), \
             patch('update_google_sheet.alerts.send_alert_email') as send:
            result = updater.run()

        self.assertFalse(result)
        self.assertEqual(updater.unparseable_notes, self.MESSAGE)
        sheets.append_row.assert_not_called()
        sheets.insert_column.assert_not_called()

        send.assert_called_once()
        _, subject, body = send.call_args[0]
        self.assertEqual(body, self.MESSAGE, "the email body must be the report itself")
        self.assertIn('FAILED', subject)

    def test_any_failed_update_is_emailed_not_just_unreadable_notes(self):
        """A night with no row and no explanation is not a report.

        The Google Sheets rejection of 2026-09-01 and 2026-09-03 failed this way twice in
        three days and sent nothing either time; it was noticed by looking at the
        spreadsheet (investment-reviews#64).
        """
        updater = self._updater()
        sheets_error = RuntimeError(
            'Invalid requests[0].insertDimension: range.startIndex must be less than '
            'the grid size (60) if inheritFromBefore is false.')

        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=sheets_error), \
             patch('update_google_sheet.alerts.send_alert_email') as send:
            result = updater.run()

        self.assertFalse(result)
        send.assert_called_once()
        _, subject, body = send.call_args[0]
        self.assertIn('FAILED', subject)
        self.assertIn('the update failed', subject)
        self.assertIn('insertDimension', body, 'the body must carry the actual reason')
        self.assertIn('grid size (60)', body, 'and enough of it to act on')

    def test_the_two_failures_are_distinguishable_in_the_subject(self):
        """They need different responses: fix a note, or fix the spreadsheet."""
        updater = self._updater()
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=update_google_sheet.UnparseableNotesError(self.MESSAGE)), \
             patch('update_google_sheet.alerts.send_alert_email') as send:
            updater.run()
        self.assertIn('notes could not be read', send.call_args[0][1])

        updater = self._updater()
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=RuntimeError('boom')), \
             patch('update_google_sheet.alerts.send_alert_email') as send:
            updater.run()
        self.assertIn('the update failed', send.call_args[0][1])

    def test_a_general_failure_keeps_its_own_exit_code(self):
        """Emailing both does not merge them: exit 3 and exit 1 need different responses."""
        updater = self._updater()
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=RuntimeError('boom')), \
             patch('update_google_sheet.alerts.send_alert_email'):
            updater.run()
        self.assertIsNone(updater.unparseable_notes,
                          'a general failure must not be reported as unreadable notes')

    def test_an_undeliverable_failure_email_does_not_mask_the_failure(self):
        updater = self._updater()
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=RuntimeError('boom')), \
             patch('update_google_sheet.alerts.send_alert_email',
                   side_effect=update_google_sheet.alerts.AlertDeliveryError('relay down')):
            self.assertFalse(updater.run())
        self.assertFalse(updater.alert_delivery_ok)

    def test_a_missing_recipient_is_reported_rather_than_raising(self):
        """Nobody to tell is itself worth logging; it must not mask the real fault."""
        updater = self._updater(recipient=None)
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=update_google_sheet.UnparseableNotesError(self.MESSAGE)), \
             patch('update_google_sheet.alerts.send_alert_email') as send:
            result = updater.run()
        self.assertFalse(result)
        self.assertEqual(updater.unparseable_notes, self.MESSAGE)
        send.assert_not_called()

    def test_an_undeliverable_report_does_not_hide_the_note_failure(self):
        """Both channels down: the run still fails for the notes, not for the email."""
        updater = self._updater()
        with patch.object(update_google_sheet.PortfolioUpdater, '_run_portfolio_analysis',
                          side_effect=update_google_sheet.UnparseableNotesError(self.MESSAGE)), \
             patch('update_google_sheet.alerts.send_alert_email',
                   side_effect=update_google_sheet.alerts.AlertDeliveryError('relay down')):
            result = updater.run()
        self.assertFalse(result)
        self.assertEqual(updater.unparseable_notes, self.MESSAGE)
        self.assertFalse(updater.alert_delivery_ok)


class TestCheckNotes(unittest.TestCase):
    """Checking a note against the market before it goes live (investment-reviews#59)."""

    def _bar(self, low, high, currency='GBP'):
        return {'low': low, 'high': high, 'currency': currency, 'bar_date': '2026-08-03'}

    def _note(self, **kw):
        base = {'ticker': 'ARMG.L', 'isin': 'IE000JCW3DZ3', 'stock_name': 'Global X ETFs',
                'currency': 'GBP', 'price': 21.5484, 'transaction_date': datetime(2026, 8, 3),
                'transaction_type': 'purchase'}
        base.update(kw)
        return base

    def _check(self, note, bar, rates=None):
        rates = rates or {}
        with patch.object(check_notes, 'market_bar', return_value=bar), \
             patch.object(check_notes, 'fx_to_gbp',
                          side_effect=lambda ccy, *a, **k: rates.get(ccy, 1.0)):
            return check_notes.check_transaction('note.pdf', note, {})

    def test_a_price_inside_the_day_range_passes(self):
        """A trade executes intraday, so the note's price belongs inside the day's range."""
        result = self._check(self._note(), self._bar(21.20, 21.80))
        self.assertEqual(result.status, check_notes.OK)

    def test_a_price_matching_the_close_but_outside_the_range_is_not_required(self):
        """Judged against closes rather than ranges, correct notes look wrong.

        Measured over the live notes, comparing against a close rejected five holdings
        whose price sat inside the trade day's own high/low.
        """
        outside = self._check(self._note(price=90.0, currency='USD'),
                              self._bar(105.46, 109.47, 'USD'))
        self.assertEqual(outside.status, check_notes.FAIL)
        inside = self._check(self._note(price=107.0, currency='USD'),
                             self._bar(105.46, 109.47, 'USD'))
        self.assertEqual(inside.status, check_notes.OK)

    def test_a_currency_label_disagreement_is_not_by_itself_wrong(self):
        """AGGG.L is listed on the LSE and quoted in USD, and that is normal.

        The Interactive Investor CSV states every price in GBP because it derives them
        from a GBP consideration, so a note currency that differs from the quote currency
        is routine.  Failing on the labels rejected correct notes whose prices agreed.
        """
        note = self._note(ticker='AGGG.L', currency='GBP', price=3.3501)
        result = self._check(note, self._bar(4.3915, 4.4195, 'USD'), rates={'USD': 0.7524})
        self.assertEqual(result.status, check_notes.OK)

    def test_the_wrong_currency_line_is_caught_on_price_after_conversion(self):
        """What the label check used to catch, now caught by comparing like with like.

        Bare WDEF is the USD line on NYSE Arca against a EUR note for the LSE line (#46).
        """
        note = self._note(ticker='WDEF', currency='EUR', price=29.9756, exchange_rate=0.8527)
        result = self._check(note, self._bar(27.59, 28.14, 'USD'), rates={'USD': 0.7395})
        self.assertEqual(result.status, check_notes.FAIL)

    def test_a_note_in_the_quote_currency_needs_no_rate(self):
        """Yahoo has no CZKGBP=X, and a CZK note against a CZK quote never needed one."""
        note = self._note(ticker='PRIUA.PR', currency='CZK', price=855.0)
        with patch.object(check_notes, 'market_bar',
                          return_value=self._bar(850.0, 860.0, 'CZK')), \
             patch.object(check_notes, 'fx_to_gbp', return_value=None) as fx:
            result = check_notes.check_transaction('note.mhtml', note, {})
        self.assertEqual(result.status, check_notes.OK)
        fx.assert_not_called()

    def test_a_rate_stated_on_the_note_is_preferred(self):
        """It is the rate the broker applied; a mid-market rate is only close to it."""
        cache = {}
        self.assertEqual(
            check_notes.fx_to_gbp('EUR', datetime(2026, 7, 13), cache, stated=0.8527), 0.8527)
        self.assertEqual(check_notes.fx_to_gbp('GBP', datetime(2026, 7, 13), cache), 1.0)
        self.assertEqual(cache, {}, 'no lookup should have been needed')

    def test_a_cost_base_entry_has_no_traded_price_to_check(self):
        """A demerger transfer apportions a GBP cost base; the market says nothing about it.

        Comparing it against the instrument's own currency reports a correct note as
        wrong, which is how this first ran against the Kongsberg entry.
        """
        note = self._note(ticker='KMAR.OL', currency='GBP', price=4.9052,
                          transaction_type='transfer')
        result = self._check(note, self._bar(55.0, 57.0, 'NOK'))
        self.assertEqual(result.status, check_notes.OK)
        self.assertIn('cost-base entry', result.detail)

    def test_a_cost_base_entry_still_has_to_name_a_real_security(self):
        """Not price-checked is not unchecked: the identifier must still resolve."""
        note = self._note(ticker='NOSUCH.L', transaction_type='transfer')
        result = self._check(note, None)
        self.assertEqual(result.status, check_notes.FAIL)

    def test_the_ratio_says_what_kind_of_wrong_it_is(self):
        for ratio, expected in ((100.0, 'pence against pounds, or a 100:1 split'),
                                (0.01, 'pence against pounds, or a 100:1 split'),
                                (10.0, '10x'), (1.35, 'FX rate'),
                                (39.6, '40x'),   # NVIDIA's 4:1 and 10:1, compounded
                                (7.3, 'different instrument')):
            with self.subTest(ratio=ratio):
                self.assertIn(expected, check_notes.explain_ratio(ratio))

    def test_provenance_names_where_the_identifier_came_from(self):
        """A wrong identifier has to be traceable to the thing that produced it."""
        self.assertEqual(
            check_notes.identity_provenance({'ticker': 'ARMG.L', 'isin': 'IE000JCW3DZ3'}),
            'ticker map')
        self.assertEqual(
            check_notes.identity_provenance(
                {'ticker': None, 'stock_name': 'Jupiter India', 'isin': 'GB00BD08NQ14'}),
            'name mapping')
        self.assertEqual(
            check_notes.identity_provenance({'ticker': 'CRM', 'isin': 'US79466L3024'}),
            'ISIN country US')

    def test_a_note_that_cannot_be_parsed_is_reported_not_skipped(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, 'B1_BOUGHT_Broken.pdf')
        open(path, 'w').write('not a pdf')
        checks = check_notes.check_note(path, {})
        self.assertEqual(checks[0].status, check_notes.FAIL)

    def test_a_corporate_action_is_skipped_not_failed(self):
        """Skipping is not the same as failing, and must not become it.

        A corporate action has no traded price to check; #53 and #54 already report one
        that cannot be read.  Collapsing the two made a broken contract note silent.
        """
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, 'acme+inc+-+merger.pdf')
        open(path, 'w').write('not a pdf either')
        self.assertEqual(check_notes.check_note(path, {}), [])

    def test_only_note_files_are_collected(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        for name in ('B1_BOUGHT_X.pdf', 'trades.csv', 'export.mhtml', 'action.yaml',
                     'notes.txt', '.DS_Store'):
            open(os.path.join(base, name), 'w').close()
        found = [os.path.basename(p) for p in check_notes.collect_notes([base])]
        self.assertNotIn('notes.txt', found)
        self.assertNotIn('.DS_Store', found)
        self.assertEqual(len(found), 4)


class TestTickerMappingsFile(unittest.TestCase):
    """The mappings are data now, loaded from YAML (investment-reviews#59)."""

    def test_every_mapping_survived_the_move_out_of_python(self):
        """Counts pinned at what the Python dicts held, verified entry by entry then.

        Reference data whose errors are silent and financial: a dropped entry would send
        a holding to Yahoo as a bare ticker, which is how #50 priced a defence ETF off a
        leveraged ARM fund.
        """
        self.assertEqual(len(ticker_mapping.TICKER_MAPPING), 45)
        self.assertEqual(len(ticker_mapping.EXCHANGE_SUFFIX_MAP), 6)
        self.assertEqual(len(ticker_mapping.SPECIAL_EXCHANGE_SUFFIX_MAP), 32)

    def test_the_entries_that_earlier_issues_turned_on_are_still_there(self):
        for ticker, suffix in (('ARMG', '.L'), ('ARMR', '.L'), ('WDEF', '.L'),
                               ('FEML', '.L'), ('BTEK', '.L'), ('TECK', '')):
            with self.subTest(ticker=ticker):
                self.assertEqual(ticker_mapping.SPECIAL_EXCHANGE_SUFFIX_MAP[ticker], suffix)
        self.assertEqual(ticker_mapping.TICKER_MAPPING['Jupiter India'], '0P00018LFD.L')

    def test_an_entry_may_carry_a_note_or_not(self):
        """Most mappings need no explanation; the ones that do need it badly."""
        data = {'names': {'Plain': 'AAA.L',
                          'Explained': {'yahoo': 'BBB.L', 'note': 'class R became class Z'}}}
        path = os.path.join(tempfile.mkdtemp(), 'm.yaml')
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        with open(path, 'w') as handle:
            yaml.safe_dump(data, handle)
        loaded = ticker_mapping.load_mappings(path)
        self.assertEqual(loaded['names'], {'Plain': 'AAA.L', 'Explained': 'BBB.L'})

    def test_an_entry_missing_its_value_is_rejected(self):
        path = os.path.join(tempfile.mkdtemp(), 'm.yaml')
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        with open(path, 'w') as handle:
            yaml.safe_dump({'names': {'Broken': {'note': 'no identifier here'}}}, handle)
        with self.assertRaises(ValueError):
            ticker_mapping.load_mappings(path)

    def test_an_unreadable_mappings_file_raises_rather_than_loading_empty(self):
        """Empty maps would silently send every holding to Yahoo as a bare ticker."""
        with self.assertRaises(RuntimeError):
            ticker_mapping.load_mappings('/nonexistent/ticker_mappings.yaml')

    def test_a_suffix_is_empty_or_starts_with_a_dot(self):
        for source in (ticker_mapping.EXCHANGE_SUFFIX_MAP,
                       ticker_mapping.SPECIAL_EXCHANGE_SUFFIX_MAP):
            for key, suffix in source.items():
                with self.subTest(key=key):
                    self.assertTrue(suffix == '' or suffix.startswith('.'),
                                    f'{key!r} maps to {suffix!r}')

    def test_no_mapping_points_at_nothing(self):
        for name, identifier in ticker_mapping.TICKER_MAPPING.items():
            with self.subTest(name=name):
                self.assertTrue(identifier and identifier.strip(), f'{name!r} maps to nothing')


class TestInsertColumnAtTheEnd(unittest.TestCase):
    """Appending a column to a full grid (investment-reviews#65)."""

    def _client(self, grid_columns, row_count=937):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        client.logger = logging.getLogger('test-sheets')
        client.spreadsheet_id = 'sheet-id'
        client.worksheet_name = 'Sheet1'
        client.sheets = Mock()
        client.sheets.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1', 'sheetId': 7,
                                       'gridProperties': {'columnCount': grid_columns}}}]
        }
        client.get_row_count = Mock(return_value=row_count)
        return client

    def _insert_request(self, client):
        body = client.sheets.batchUpdate.call_args.kwargs['body']
        return body['requests'][0]['insertDimension']

    def test_appending_past_the_last_column_inherits_from_the_left(self):
        """The failure itself: 60 named columns in a 60-wide grid.

        With inheritFromBefore false the API is asked to inherit from the column after
        the last one, which does not exist, and rejects the request.
        """
        client = self._client(grid_columns=60)
        client.insert_column(60, 'Orbital compute')
        request = self._insert_request(client)
        self.assertEqual(request['range']['startIndex'], 60)
        self.assertTrue(request.get('inheritFromBefore'),
                        'appending must inherit from the column to its left')

    def test_inserting_inside_the_grid_is_unchanged(self):
        """A spare trailing column already worked; that behaviour is not disturbed."""
        client = self._client(grid_columns=61)
        client.insert_column(60, 'Orbital compute')
        self.assertFalse(self._insert_request(client).get('inheritFromBefore', False))

    def test_the_very_first_column_cannot_inherit_from_its_left(self):
        """The API requires startIndex > 0 when inheritFromBefore is true."""
        client = self._client(grid_columns=0)
        client.insert_column(0, 'First')
        self.assertFalse(self._insert_request(client).get('inheritFromBefore', False))

    def test_the_grid_size_and_sheet_id_come_from_one_fetch(self):
        """Both live in the same metadata; asking twice is a wasted round trip."""
        client = self._client(grid_columns=60)
        client.insert_column(60, 'Orbital compute')
        self.assertEqual(client.sheets.get.call_count, 1)
        self.assertEqual(self._insert_request(client)['range']['sheetId'], 7)


class TestCheckNotesCandidates(unittest.TestCase):
    """Proposing an identifier and recording the choice (investment-reviews#59)."""

    def _note(self, **kw):
        base = {'ticker': 'ARMG', 'isin': 'IE000JCW3DZ3', 'stock_name': 'Global X ETFs',
                'currency': 'GBP', 'price': 21.5484,
                'transaction_date': datetime(2026, 8, 3), 'transaction_type': 'purchase'}
        base.update(kw)
        return base

    def test_a_ticker_note_is_offered_suffixes_it_can_actually_record(self):
        """Only what the resolver can use: a match that cannot be written is a trap."""
        candidates = check_notes.candidates_for(self._note())
        self.assertEqual(candidates[0].identifier, 'ARMG.L', 'the likeliest first')
        for candidate in candidates:
            with self.subTest(identifier=candidate.identifier):
                self.assertEqual(candidate.section, 'ticker_suffixes')
                self.assertEqual(candidate.key, 'ARMG')

    def test_the_isin_is_only_offered_where_the_resolver_would_look_at_names(self):
        """Names are consulted only for a note with no ticker, so offering the ISIN for a
        ticker-bearing note would propose something that could never take effect."""
        with_ticker = check_notes.candidates_for(self._note())
        self.assertNotIn('IE000JCW3DZ3', [c.identifier for c in with_ticker])

        without = check_notes.candidates_for(self._note(ticker=None))
        isin = [c for c in without if c.identifier == 'IE000JCW3DZ3']
        self.assertEqual(len(isin), 1)
        self.assertEqual(isin[0].section, 'names')
        self.assertEqual(isin[0].key, 'Global X ETFs')

    def test_a_candidate_is_judged_the_same_way_the_note_was(self):
        """Scoring a suggestion more leniently than the thing it replaces is worse than
        making no suggestion."""
        calls = []
        def fake(ticker, currency, price, trade_date, rate, cache):
            calls.append(ticker)
            return (check_notes.OK, 'inside', {}) if ticker == 'ARMG.L' else (check_notes.FAIL, 'no', {})
        with patch.object(check_notes, 'compare_to_market', side_effect=fake):
            scored = check_notes.search_candidates(self._note(), {})
        self.assertIn('ARMG.L', calls)
        matched = [c.identifier for c in scored if c.status == check_notes.OK]
        self.assertEqual(matched, ['ARMG.L'])

    def test_choosing_nothing_records_nothing(self):
        """A first-class answer: the tool cannot tell a wrong identifier from a security
        Yahoo does not carry, and guessing is how a plausible wrong number gets in."""
        check = check_notes.Check('n.pdf', check_notes.FAIL, 'ARMG', 'note ticker',
                                  'GBP', 21.5484, '2026-08-03', None, None, None, None, 'outside')
        with patch.object(check_notes, 'search_candidates', return_value=[
                check_notes.Candidate('ARMG.L', 'ticker_suffixes', 'ARMG', '.L',
                                      check_notes.OK, 'inside')]), \
             patch.object(check_notes, 'write_mapping') as write:
            written = check_notes.offer_candidates(check, self._note(), {},
                                                   prompt=lambda _: '', out=lambda *a: None)
        self.assertFalse(written)
        write.assert_not_called()

    def test_an_answer_outside_the_choices_records_nothing(self):
        check = check_notes.Check('n.pdf', check_notes.FAIL, 'ARMG', 'note ticker',
                                  'GBP', 21.5484, '2026-08-03', None, None, None, None, 'outside')
        with patch.object(check_notes, 'search_candidates', return_value=[
                check_notes.Candidate('ARMG.L', 'ticker_suffixes', 'ARMG', '.L',
                                      check_notes.OK, 'inside')]), \
             patch.object(check_notes, 'write_mapping') as write:
            for answer in ('2', 'x', '0', '-1'):
                with self.subTest(answer=answer):
                    self.assertFalse(check_notes.offer_candidates(
                        check, self._note(), {}, prompt=lambda _: answer, out=lambda *a: None))
            write.assert_not_called()

    def test_the_chosen_mapping_is_written_with_its_reason(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, 'ticker_mappings.yaml')
        header = '# a header explaining the file\n# second line\n\n'
        with open(path, 'w') as handle:
            handle.write(header)
            yaml.safe_dump({'ticker_suffixes': {'ARMR': '.L'}}, handle)

        check_notes.write_mapping('ticker_suffixes', 'ARMG', '.L',
                                  note='chosen against the 2026-08-03 price', path=path)
        written = open(path).read()
        self.assertTrue(written.startswith(header), 'the header must survive a write')

        data = yaml.safe_load(written)
        self.assertEqual(data['ticker_suffixes']['ARMR'], '.L', 'existing entries kept')
        self.assertEqual(data['ticker_suffixes']['ARMG'],
                         {'suffix': '.L', 'note': 'chosen against the 2026-08-03 price'})

    def test_the_written_file_still_loads(self):
        """A writer that produced something the loader rejects would break every run."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, 'ticker_mappings.yaml')
        with open(path, 'w') as handle:
            handle.write('# header\n\n')
            yaml.safe_dump({'names': {}, 'exchange_suffixes': {}, 'renames': {},
                            'ticker_suffixes': {'ARMR': '.L'}}, handle)
        check_notes.write_mapping('ticker_suffixes', 'ARMG', '.L', note='why', path=path)
        loaded = ticker_mapping.load_mappings(path)
        self.assertEqual(loaded['ticker_suffixes'], {'ARMR': '.L', 'ARMG': '.L'})


class TestReviewInvariants(unittest.TestCase):
    """Each invariant must be able to fire, or it is coverage in name only (#29)."""

    @staticmethod
    def _holdings(**overrides):
        row = {
            'ticker': 'PLTR', 'units_held': 100, 'current_price': 120.0,
            'current_value': 12000.0, 'recent_high': 130.0,
            'smoothed_high': 125.0, 'percentile_high': 124.0,
            'progress_to_doubling': '1.5x', 'simple_roi': 0.5, 'doubling_count': 0,
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
        self.assertEqual([v for v in violations if 'do not reconcile' in v and 'Category' in v],
                         violations, f"expected only the Category reconciliation violation: {violations}")

    def test_doubling_progress_must_match_the_return(self):
        """#31: a holding down 3% was reported at 97x progress towards a doubling."""
        results = {'individual_stocks': self._holdings(
            ticker='XGSG.L', progress_to_doubling='97.2x', simple_roi=-0.03)}
        violations = review_invariants.check_full_history(results)
        matching = [v for v in violations if 'progress to a' in v]
        self.assertEqual(len(matching), 1, violations)
        self.assertIn('XGSG.L', matching[0])

    def test_a_genuine_multi_bagger_does_not_fire(self):
        """Real multiples must survive: 12x progress on a 320% return is consistent."""
        results = {'individual_stocks': self._holdings(
            ticker='CLS.TO', progress_to_doubling='12.0x', simple_roi=3.207)}
        self.assertEqual(
            [v for v in review_invariants.check_full_history(results) if 'progress to a' in v], [])

    def test_doubling_check_is_skipped_after_a_profit_taking(self):
        """Progress resets to the sale price after a doubling, so the two diverge."""
        results = {'individual_stocks': self._holdings(
            progress_to_doubling='1.1x', simple_roi=8.0, doubling_count=2)}
        self.assertEqual(
            [v for v in review_invariants.check_full_history(results) if 'progress to a' in v], [])

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


import csv_parser


class TestCsvPricePerShare(unittest.TestCase):
    """The broker CSV states its own units; the price comes from the consideration (#31)."""

    HEADER = ("Date,Settlement Date,Symbol,Name,Sedol,Quantity,Price,Description,"
              "Reference,Debit,Credit,Running Balance\n")

    def _parse(self, *rows):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as handle:
            handle.write(self.HEADER)
            for row in rows:
                handle.write(row + '\n')
            path = handle.name
        try:
            return csv_parser.parse_stock_transaction_csv(path)
        finally:
            os.unlink(path)

    def test_london_etf_price_is_not_divided_by_a_hundred(self):
        """#31: every '.L' symbol missing from a Yahoo-quirk list had its price cut 100x.

        This is the row from the issue.  £24.12 x 2487 units is the £59,995.28 paid, so
        the stated price is already in pounds and dividing it was simply wrong.
        """
        row = ('04/08/2025,06/08/2025,XGSG.L,Xtrackers II Global Government Bond,B5KR5B1,'
               '2487,£24.12,2487 XTRS II Del 24.12,27725US4BFN,"£59,995.28",n/a,"£306,867.61"')
        transaction = self._parse(row)[0]
        self.assertAlmostEqual(transaction['price'], 59995.28 / 2487, places=4)
        self.assertGreater(transaction['price'], 24.0)

    def test_price_stated_in_dollars_still_yields_the_gbp_price(self):
        """Some London ETFs are USD-denominated and II writes the dollar price under a £.

        Deriving from the consideration sidesteps the units question entirely.
        """
        row = ('04/08/2025,06/08/2025,ICOM.L,iShares Diversified Commodity,BDFL4P1,'
               '4560,£7.19,4560 ISHS VI Del 7.19,27725US29ZN,"£25,063.57",n/a,"£656,691.82"')
        transaction = self._parse(row)[0]
        self.assertAlmostEqual(transaction['price'], 25063.57 / 4560, places=4)

    def test_price_includes_dealing_costs(self):
        """The consideration includes costs, so the derived price is a true cost per unit.

        £145,000 bought 42849.54 units at a stated £3.38, which is £144,831 of stock plus
        £169 of costs.  Deriving from the consideration gives £3.3839, consistent with the
        cost basis the rest of the tool already uses for unrealized profit.
        """
        row = ('05/08/2025,07/08/2025,0P00013P6I.L,HSBC FTSE All-World Index C Acc,BMJJJF9,'
               '42849.54,£3.38,42849.54 HSBC GLOB Del 3.38,27725US4CB6,"£145,000.00",n/a,"£1,881.09"')
        transaction = self._parse(row)[0]
        self.assertAlmostEqual(transaction['price'], 145000.00 / 42849.54, places=4)

    def test_us_symbol_price_comes_from_the_consideration_too(self):
        """Non-London symbols were never divided, and must be unaffected."""
        row = ('05/08/2025,07/08/2025,PLTR,Palantir Technologies Inc,BN0000,'
               '100,£21.09,100 PLTR Del 21.09,27725US4CB7,"£2,109.00",n/a,"£1,881.09"')
        transaction = self._parse(row)[0]
        self.assertAlmostEqual(transaction['price'], 21.09, places=4)

    def test_sale_price_comes_from_the_credit_column(self):
        """Disposals take their consideration from Credit rather than Debit."""
        row = ('05/08/2025,07/08/2025,SSAC.L,iShares MSCI ACWI,B6R51T5,'
               '100,£74.31,100 ISHS V Del 74.31,27725US4B8W,n/a,"£7,431.00","£1,881.09"')
        transaction = self._parse(row)[0]
        self.assertEqual(transaction['transaction_type'], 'disposal')
        self.assertAlmostEqual(transaction['price'], 74.31, places=4)


class TestDoublingMetricsAgainstCsvPrices(unittest.TestCase):
    """The user-visible symptom of #31: a nightly alert claiming a 97x return."""

    def _buy(self, price, quantity=2487):
        return StockTransaction(
            date=datetime(2025, 8, 4), transaction_type='BUY', quantity=quantity,
            price_per_share=price, total_amount=price * quantity
        )

    def test_a_flat_holding_is_not_reported_as_a_hundred_baggers(self):
        """XGSG.L: bought at £24.12, now £23.45. It reported 97.2x."""
        progress, _ = transaction_processor.calculate_doubling_metrics(
            [self._buy(24.1236)], current_price=23.45)
        self.assertEqual(progress, '1.0x')

        # The value the broken parser produced, for contrast
        progress_when_priced_in_error, _ = transaction_processor.calculate_doubling_metrics(
            [self._buy(0.241236)], current_price=23.45)
        self.assertEqual(progress_when_priced_in_error, '97.2x')

    def test_a_genuine_multiple_still_reports(self):
        """The fix must not mute real doubling candidates."""
        progress, _ = transaction_processor.calculate_doubling_metrics(
            [self._buy(21.09, quantity=100)], current_price=137.57)
        self.assertEqual(progress, '6.5x')


if __name__ == '__main__':
    import sys
    success = run_unit_tests()
    sys.exit(0 if success else 1)

