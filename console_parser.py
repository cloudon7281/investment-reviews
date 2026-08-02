#!/usr/bin/env python3
"""
Parse console output from full-history mode to extract portfolio values.

Extracts the Portfolio Summary table which contains:
- Whole Portfolio total
- Category totals (ISA, Taxable, Pension)
- Tag totals

and the per-stock rows of the Full Investment History table, used for the
nightly alerts.

Used by update_google_sheet.py for daily updates.
"""

import re
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ConsoleOutputParser:
    """Parser for full-history console output."""
    
    def __init__(self):
        """Initialize the parser."""
        self.portfolio_value = None
        self.category_values = {}
        self.tag_values = {}
    
    def parse(self, console_output: str) -> Dict[str, float]:
        """Parse console output and extract all values.
        
        Args:
            console_output: Full console output from portfolio.py
            
        Returns:
            Dictionary with keys:
                'Whole Portfolio': float
                'ISA': float
                'Taxable': float
                'Pension': float
                '<tag name>': float for each tag
                
        Raises:
            ValueError: If cannot parse required fields
        """
        # Debug: Show basic info about console output
        output_lines = console_output.split('\n')
        logger.debug(f"Console output has {len(output_lines)} lines")
        logger.debug(f"First 5 lines: {output_lines[:min(5, len(output_lines))]}")
        
        # Find the Portfolio Summary section
        summary_section = self._extract_portfolio_summary(console_output)
        if not summary_section:
            # Debug: Show what sections we can find
            logger.error("Could not find 'Portfolio Summary' section in console output")
            logger.debug("Searching for lines with 'Summary' or 'Portfolio':")
            for i, line in enumerate(output_lines):
                if 'Summary' in line or 'Portfolio' in line:
                    logger.debug(f"  Line {i}: {line[:100]}")
            raise ValueError("Could not find Portfolio Summary section in console output")
        
        logger.debug(f"Found Portfolio Summary section with {len(summary_section.split(chr(10)))} lines")
        
        # Parse the table
        values = {}
        
        # Extract each row from the summary table
        # Format: | Tag | £X,XXX | £X,XXX | £X,XXX | ...
        lines = summary_section.split('\n')
        
        # Debug: Show first few lines of the extracted section
        logger.debug(f"First 5 lines of extracted section:")
        for i, line in enumerate(lines[:5]):
            logger.debug(f"  [{i}] {repr(line[:80])}")
        
        lines_with_pipe = 0
        for line in lines:
            # Skip separator lines and headers
            if line.startswith('+') or line.startswith('=') or 'Total Invested' in line:
                continue
            
            # Parse data lines (those that start with | and contain multiple |)
            if line.strip().startswith('|') and line.count('|') >= 4:
                lines_with_pipe += 1
                logger.debug(f"  Line {lines_with_pipe} with pipes: {line[:80]}")
                parsed = self._parse_summary_line(line)
                if parsed:
                    tag_name, current_value = parsed
                    values[tag_name] = current_value
                    logger.debug(f"    ✓ Parsed: '{tag_name}' = £{current_value:,.2f}")
                else:
                    logger.debug(f"    ✗ _parse_summary_line returned None")
        
        logger.info(f"Found {lines_with_pipe} data lines, successfully parsed {len(values)} values")
        
        # Validate we got the essential fields
        required_fields = ['Whole Portfolio', 'ISA', 'Taxable', 'Pension']
        missing = [f for f in required_fields if f not in values]
        if missing:
            logger.error(f"Parsed fields: {list(values.keys())}")
            raise ValueError(f"Missing required fields in output: {missing}")
        
        return values
    
    def _extract_portfolio_summary(self, console_output: str) -> Optional[str]:
        """Extract the Portfolio Summary table section from console output.
        
        Args:
            console_output: Full console output
            
        Returns:
            String containing just the Portfolio Summary table, or None if not found
        """
        # Look for "Portfolio Summary" header followed by table
        pattern = r'Portfolio Summary\s*\n=+\s*\n(.*?)(?=\n\nFull Investment History|$)'
        match = re.search(pattern, console_output, re.DOTALL)
        
        if match:
            return match.group(1)
        return None
    
    def _parse_summary_line(self, line: str) -> Optional[tuple]:
        """Parse a single line from the summary table.
        
        Args:
            line: Table row containing ||
            
        Returns:
            Tuple of (tag_name, current_value) or None if can't parse
        """
        # Remove ANSI color codes (e.g., [92m, [0m)
        line = re.sub(r'\[\d+m', '', line)
        
        # Split by | to get columns (not ||)
        parts = [p.strip() for p in line.split('|') if p.strip()]
        
        logger.debug(f"      Split into {len(parts)} parts: {parts[:5] if len(parts) > 5 else parts}")
        
        # Format: || Tag | Total Invested | Total Received | Current Value | ...
        # After split and filter: [Tag, Total Invested, Total Received, Current Value, ...]
        # We want: parts[0] = Tag name, parts[3] = Current Value
        if len(parts) < 4:
            logger.debug(f"      Not enough parts ({len(parts)} < 4)")
            return None
        
        tag_name = parts[0].strip()
        current_value_str = parts[3].strip()
        
        logger.debug(f"      tag_name='{tag_name}', current_value_str='{current_value_str}'")
        
        # Skip header rows
        if tag_name == 'Tag' or not current_value_str:
            logger.debug(f"      Skipping: tag is 'Tag' or value is empty")
            return None
        
        # Parse currency value (£X,XXX.XX)
        try:
            # Remove £ and commas
            value_clean = current_value_str.replace('£', '').replace(',', '')
            current_value = float(value_clean)
            return (tag_name, current_value)
        except (ValueError, AttributeError) as e:
            logger.debug(f"      Failed to parse value '{current_value_str}': {e}")
            return None
    
    def parse_stocks(self, console_output: str) -> List[Dict]:
        """Parse the per-stock rows of the Full Investment History table.

        Args:
            console_output: Full console output from portfolio.py

        Returns:
            List of dictionaries, one per stock, with keys:
                'company': str
                'ticker': str
                'tag': str
                'current_value': float or None
                'daily_change': float or None (fraction, e.g. 0.032 for +3.2%)
                'progress_to_2x': float or None (e.g. 1.97)

        Raises:
            ValueError: If the Full Investment History table cannot be found
        """
        rows = self._extract_grid_rows(console_output, 'Full Investment History')
        if not rows:
            raise ValueError("Could not find Full Investment History table in console output")

        stocks = []
        for row in rows:
            stocks.append({
                'company': row.get('Company', ''),
                'ticker': row.get('Ticker', ''),
                'tag': row.get('Tag', ''),
                'current_value': self._parse_currency(row.get('Current Value')),
                'daily_change': self._parse_percentage(row.get('1d Change')),
                'progress_to_2x': self._parse_multiple(row.get('Progress to 2x')),
            })

        logger.info(f"Parsed {len(stocks)} stock rows from Full Investment History")
        return stocks

    def _extract_grid_rows(self, console_output: str, table_name: str) -> List[Dict[str, str]]:
        """Extract rows of a tabulate 'grid' table as header -> cell dictionaries.

        Args:
            console_output: Full console output
            table_name: Title printed immediately above the table

        Returns:
            List of dictionaries keyed by column header (empty if table not found)
        """
        lines = console_output.split('\n')

        # Locate the table title, then read the grid that follows it
        start_index = None
        for i, line in enumerate(lines):
            if line.strip() == table_name:
                start_index = i + 1
                break

        if start_index is None:
            logger.error(f"Could not find '{table_name}' title in console output")
            return []

        headers = None
        rows = []
        for line in lines[start_index:]:
            stripped = self._strip_ansi(line).strip()

            if stripped.startswith('+'):
                continue  # grid rule
            if not stripped.startswith('|'):
                if headers is not None:
                    break  # end of the table
                continue  # title underline / blank lines before the table

            cells = [cell.strip() for cell in stripped.strip('|').split('|')]

            if headers is None:
                headers = cells
                continue

            # Skip the separator rows written between row types
            if all(set(cell) <= {'-'} for cell in cells):
                continue

            rows.append(dict(zip(headers, cells)))

        return rows

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI colour codes from a line of console output."""
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    @staticmethod
    def _parse_currency(value: Optional[str]) -> Optional[float]:
        """Parse a formatted currency cell (e.g. '£1,234.56') into a float."""
        if not value:
            return None
        try:
            return float(value.replace('£', '').replace(',', ''))
        except ValueError:
            logger.debug(f"Could not parse currency value '{value}'")
            return None

    @staticmethod
    def _parse_percentage(value: Optional[str]) -> Optional[float]:
        """Parse a formatted percentage cell (e.g. '3.2%') into a fraction."""
        if not value:
            return None
        try:
            return float(value.replace('%', '').replace(',', '')) / 100
        except ValueError:
            logger.debug(f"Could not parse percentage value '{value}'")
            return None

    @staticmethod
    def _parse_multiple(value: Optional[str]) -> Optional[float]:
        """Parse a formatted multiple cell (e.g. '1.9x'); '—' returns None."""
        if not value or not value.endswith('x'):
            return None
        try:
            return float(value[:-1])
        except ValueError:
            logger.debug(f"Could not parse multiple value '{value}'")
            return None

    @staticmethod
    def extract_values_from_output(console_output: str) -> Dict[str, float]:
        """Convenience method to parse output in one call.
        
        Args:
            console_output: Full console output from portfolio.py
            
        Returns:
            Dictionary mapping tag names to current values
        """
        parser = ConsoleOutputParser()
        return parser.parse(console_output)

    @staticmethod
    def extract_stocks_from_output(console_output: str) -> List[Dict]:
        """Convenience method to parse the per-stock rows in one call.

        Args:
            console_output: Full console output from portfolio.py

        Returns:
            List of per-stock dictionaries (see parse_stocks)
        """
        parser = ConsoleOutputParser()
        return parser.parse_stocks(console_output)


if __name__ == '__main__':
    # Test with sample output (EXAMPLE DATA ONLY - NOT REAL)
    sample_output = """
Portfolio Summary
=================

+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Tag             | Total Invested   | Total Received   | Current Value   | Total P&L   | ROI     | First Transaction   | Last Transaction   | Annualized ROI   |
+=================+==================+==================+=================+=============+=========+=====================+====================+==================+
|| Whole Portfolio | £100,000         | £20,000          | £125,000        | [92m£45,000[0m     | 45.0%   |                     |                    |                  |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| ISA             | £50,000          | £10,000          | £60,000         | [92m£20,000[0m     | [92m40.0%[0m   | 01/01/20            | 31/12/24           | 8.5%             |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Taxable         | £40,000          | £8,000           | £55,000         | [92m£23,000[0m     | 57.5%   | 01/01/20            | 31/12/24           | 11.5%            |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Pension         | £10,000          | £0               | £10,500         | [92m£500[0m        | 5.0%    | 01/01/24            | 31/12/24           | 5.0%             |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Technology      | £25,000          | £0               | £30,000         | [92m£5,000[0m      | 20.0%   | 01/06/23            | 31/12/24           | 13.3%            |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+

Full Investment History
"""
    
    try:
        parser = ConsoleOutputParser()
        summary = parser._extract_portfolio_summary(sample_output)
        print("Extracted summary section:")
        print(summary)
        print("\n" + "="*80 + "\n")
        
        values = parser.parse(sample_output)
        print("Parsed values:")
        for tag, value in values.items():
            print(f"  {tag}: £{value:,.2f}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

