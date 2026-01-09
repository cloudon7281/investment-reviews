#!/usr/bin/env python3
"""
Parse console output from full-history mode to extract portfolio values.

Extracts the Portfolio Summary table which contains:
- Whole Portfolio total
- Category totals (ISA, Taxable, Pension)
- Tag totals

Used by update_google_sheet.py for daily updates.
"""

import re
import logging
from typing import Dict, Optional
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


if __name__ == '__main__':
    # Test with sample output
    sample_output = """
Portfolio Summary
=================

+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Tag             | Total Invested   | Total Received   | Current Value   | Total P&L   | ROI     | First Transaction   | Last Transaction   | Annualized ROI   |
+=================+==================+==================+=================+=============+=========+=====================+====================+==================+
|| Whole Portfolio | £1,143,678       | £338,582         | £1,190,515      | [92m£385,418[0m    | 33.7%   |                     |                    |                  |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| ISA             | £105,240         | £231,688         | £106,446        | [92m£232,894[0m    | [92m221.3%[0m  | 30/10/20            | 22/09/25           | 26.6%            |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Taxable         | £308,472         | £106,893         | £322,816        | [92m£121,237[0m    | 39.3%   | 12/10/20            | 20/08/25           | 6.9%             |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| Pension         | £729,966         | £0               | £761,253        | [92m£31,286[0m     | 4.3%    | 04/08/25            | 05/08/25           | 26.1%            |
+-----------------+------------------+------------------+-----------------+-------------+---------+---------------------+--------------------+------------------+
|| AI              | £50,000          | £0               | £55,123         | [92m£5,123[0m      | 10.2%   | 15/03/25            | 15/03/25           | 45.3%            |
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

