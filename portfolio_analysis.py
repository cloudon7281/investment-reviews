"""Portfolio Analysis - portfolio analysis interface.

This module provides a simple interface for portfolio analysis by delegating
to specialized modules for different aspects of calculation.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from portfolio_review import PortfolioReview

# Specialized calculation modules
from market_data_fetcher import MarketDataFetcher
import tax_report_processor
import full_history_processor
import periodic_review_processor

class PortfolioAnalysis:
    def __init__(self):
        """Initialize the portfolio analysis."""
        self.market_data_fetcher = MarketDataFetcher()
        # Keep references to caches for backward compatibility
        self.price_cache = self.market_data_fetcher.price_cache
        self.exchange_rate_cache = self.market_data_fetcher.exchange_rate_cache
        self.stock_currencies: Dict[str, str] = {}

    def process_full_history(self, portfolio_review: PortfolioReview, value_over_time_days: int = None) -> Dict[str, pd.DataFrame]:
        """Process full history mode - three-phase implementation."""
        return full_history_processor.process_full_history(
            portfolio_review, value_over_time_days, self.market_data_fetcher
        )

    def process_periodic_review(self, portfolio_review: PortfolioReview, start_date: datetime, end_date: datetime, eval_date: Optional[datetime] = None) -> Dict[str, pd.DataFrame]:
        """Process a periodic review analysis."""
        return periodic_review_processor.process_periodic_review(
            portfolio_review, start_date, end_date, eval_date, self.market_data_fetcher
        )

    def process_tax_report(self, portfolio_review: PortfolioReview, tax_year_start: datetime, tax_year_end: datetime) -> pd.DataFrame:
        """Process tax report for a specific tax year."""
        return tax_report_processor.process_tax_report(portfolio_review, tax_year_start, tax_year_end)

