"""
CSV writer for portfolio reports.
"""

import csv
from pathlib import Path
from typing import Any
import pandas as pd
from logger import logger


class CSVWriter:
    """Writes formatted CSV files for portfolio data."""
    
    def __init__(self, output_filepath: str):
        """Initialize the CSV writer.
        
        Args:
            output_filepath: Path where CSV file should be written
        """
        self.output_filepath = Path(output_filepath)
        logger.info(f"Initialized CSVWriter for: {self.output_filepath}")
    
    def write_value_over_time(self, df: pd.DataFrame) -> None:
        """Write value-over-time DataFrame to CSV file.
        
        Args:
            df: DataFrame with columns: date, whole_portfolio, isa, taxable, pension, and tag columns
                All monetary values should be floats in GBP
        """
        if df.empty:
            logger.warning("No data to write to CSV")
            return
        
        logger.info(f"Writing value-over-time CSV with {len(df)} rows and {len(df.columns)} columns")
        
        try:
            # Prepare header row
            headers = []
            for col in df.columns:
                if col == 'date':
                    headers.append('Date')
                elif col == 'whole_portfolio':
                    headers.append('Whole Portfolio')
                elif col == 'isa':
                    headers.append('ISA')
                elif col == 'taxable':
                    headers.append('Taxable')
                elif col == 'pension':
                    headers.append('Pension')
                else:
                    # Tag columns - capitalize first letter
                    headers.append(col.title() if col else col)
            
            # Open CSV file for writing
            with open(self.output_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(headers)
                
                # Write data rows
                for _, row in df.iterrows():
                    formatted_row = []
                    for col in df.columns:
                        value = row[col]
                        if col == 'date':
                            # Format date as YYYY-MM-DD
                            formatted_value = self._format_date(value)
                        else:
                            # Format monetary values as currency
                            formatted_value = self._format_currency(value)
                        formatted_row.append(formatted_value)
                    
                    writer.writerow(formatted_row)
            
            logger.info(f"Successfully wrote CSV to: {self.output_filepath}")
            
        except Exception as e:
            logger.error(f"Error writing CSV file: {str(e)}")
            raise
    
    def _format_date(self, value: Any) -> str:
        """Format a date value as YYYY-MM-DD.
        
        Args:
            value: Date value (datetime or string)
            
        Returns:
            Formatted date string
        """
        if pd.isna(value):
            return ''
        
        if hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d')
        else:
            # Already a string
            return str(value)
    
    def _format_currency(self, value: Any) -> str:
        """Format a monetary value as £X,XXX.XX.

        Args:
            value: Numeric value in GBP

        Returns:
            Formatted currency string
        """
        if pd.isna(value) or value is None:
            return '£0.00'

        try:
            # Format with 2 decimal places and comma separators
            return f"£{value:,.2f}"
        except (ValueError, TypeError):
            logger.warning(f"Could not format value as currency: {value}")
            return '£0.00'

    def write_price_over_time(self, df: pd.DataFrame) -> None:
        """Write price-over-time DataFrame to CSV file.

        Unlike value-over-time, this outputs raw GBP prices without currency formatting,
        making it easier to import into spreadsheets for analysis.

        Args:
            df: DataFrame with columns: date, ticker1, ticker2, ...
                Values are GBP closing prices (floats)
        """
        if df.empty:
            logger.warning("No data to write to CSV")
            return

        logger.info(f"Writing price-over-time CSV with {len(df)} rows and {len(df.columns)} columns")

        try:
            # Prepare header row (use column names as-is, just capitalize Date)
            headers = []
            for col in df.columns:
                if col == 'date':
                    headers.append('Date')
                else:
                    headers.append(col)  # Keep ticker symbols as-is

            # Open CSV file for writing
            with open(self.output_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(headers)

                # Write data rows
                for _, row in df.iterrows():
                    formatted_row = []
                    for col in df.columns:
                        value = row[col]
                        if col == 'date':
                            # Format date as YYYY-MM-DD
                            formatted_value = self._format_date(value)
                        else:
                            # Format prices as plain numbers (2 decimal places)
                            formatted_value = self._format_price(value)
                        formatted_row.append(formatted_value)

                    writer.writerow(formatted_row)

            logger.info(f"Successfully wrote CSV to: {self.output_filepath}")

        except Exception as e:
            logger.error(f"Error writing CSV file: {str(e)}")
            raise

    def _format_price(self, value: Any) -> str:
        """Format a price value as a plain number with 2 decimal places.

        Args:
            value: Numeric price value in GBP

        Returns:
            Formatted price string (plain number, no currency symbol)
        """
        if pd.isna(value) or value is None:
            return ''

        try:
            # Format with 2 decimal places, no currency symbol
            return f"{value:.2f}"
        except (ValueError, TypeError):
            logger.warning(f"Could not format value as price: {value}")
            return ''

