"""
Console table writer for portfolio reports.
"""

from typing import List, Dict, Any, Optional
from tabulate import tabulate
import pandas as pd
import locale
from logger import logger


class ConsoleTableWriter:
    """Writes formatted tables to console output."""
    
    def __init__(self):
        """Initialize the console table writer."""
        pass
    
    def write_table(self, table_data: List[List[Dict[str, Any]]], config: Dict[str, Any]) -> None:
        """Write a table to console output.
        
        Args:
            table_data: List of rows, each row is a list of cell data dictionaries, or dict with 'title' and 'data' keys
            config: Column configuration from reporter_definitions
        """
        # Handle new data structure with title
        if isinstance(table_data, dict) and 'title' in table_data and 'data' in table_data:
            title = table_data['title']
            actual_data = table_data['data']
        else:
            title = None
            actual_data = table_data
        
        if not actual_data:
            print("No data to display")
            return
        
        # Display title if provided
        if title:
            print(f"\n{title}")
            print("=" * len(title))
            print("")
        
        # Extract headers and formatted data
        headers = config['headers']
        formatted_data = []
        prev_row_type = None
        
        for row in actual_data:
            # Handle new structure with row type metadata
            if isinstance(row, dict) and 'cells' in row:
                row_cells = row['cells']
                row_type = row.get('row_type', None)
            else:
                # Backward compatibility: treat as list of cells
                row_cells = row
                row_type = None
            
            # Add separator line when transitioning between row types (for visual distinction)
            if row_type and prev_row_type and row_type != prev_row_type:
                # Add a thin separator row
                formatted_data.append(['-' * len(h) for h in headers])
            prev_row_type = row_type
            
            formatted_row = []
            for cell in row_cells:
                # Format the raw value using the format configuration
                formatted_value = self._format_for_console(cell['raw_value'], cell['format_config'], cell.get('style'))
                formatted_row.append(formatted_value)
            formatted_data.append(formatted_row)
        
        # Display table using tabulate
        if formatted_data:
            print(tabulate(formatted_data, headers=headers, tablefmt='grid'))
    
    
    def write_section_header(self, header: str) -> None:
        """Write a section header to console output.
        
        Args:
            header: The header text to display
        """
        print(f"\n{header}")
        print("-" * len(header))
    
    def write_text(self, text: str) -> None:
        """Write plain text to console output.
        
        Args:
            text: The text to display
        """
        print(text)
    
    def _format_for_console(self, value: Any, format_config: Dict[str, Any], style: Optional[str] = None) -> str:
        """Format a value for console output based on format configuration and style.
        
        Args:
            value: The value to format
            format_config: Format configuration dictionary from reporter_definitions
            style: Style name ('red', 'amber', 'green') for color coding
            
        Returns:
            Formatted string for console output with optional color coding
        """
        # Handle None/NaN values
        if pd.isna(value) or value is None or value == '':
            return ''
        
        # Handle missing format configuration
        if not format_config or 'type' not in format_config:
            return str(value)
        
        format_type = format_config['type']
        
        # Format the value based on type
        if format_type == 'currency':
            currency = format_config.get('currency', 'GBP')
            decimal_places = format_config.get('decimal_places', 2)
            formatted_value = self._format_currency(value, currency, decimal_places)
        elif format_type == 'percentage':
            formatted_value = f"{value*100:.1f}%"
        elif format_type == 'integer':
            formatted_value = f"{value:,.0f}"
        elif format_type == 'date':
            # Format dates as DD/MM/YY
            if hasattr(value, 'strftime'):
                formatted_value = value.strftime('%d/%m/%y')
            else:
                # If it's already a string, try to parse and reformat
                try:
                    from datetime import datetime
                    if isinstance(value, str):
                        # Try different date formats and convert to DD/MM/YY
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                            try:
                                dt = datetime.strptime(value, fmt)
                                formatted_value = dt.strftime('%d/%m/%y')
                                break
                            except ValueError:
                                continue
                        else:
                            formatted_value = str(value)  # Fallback to original string
                    else:
                        formatted_value = str(value)
                except:
                    formatted_value = str(value)
        elif format_type == 'text':
            formatted_value = str(value)
        else:
            formatted_value = str(value)
        
        # Apply color coding if style is specified
        if style:
            return self._apply_console_style(formatted_value, style)
        else:
            return formatted_value
    
    def _apply_console_style(self, text: str, style: str) -> str:
        """Apply console color coding based on style.
        
        Args:
            text: The text to color
            style: Style name ('red', 'amber', 'green')
            
        Returns:
            Text with ANSI color codes
        """
        if style == 'red':
            return f"\033[91m{text}\033[0m"  # Red text
        elif style == 'amber':
            return f"\033[93m{text}\033[0m"  # Yellow text
        elif style == 'green':
            return f"\033[92m{text}\033[0m"  # Green text
        else:
            return text
    
    def _format_currency(self, value: float, currency: str = 'GBP', decimal_places: int = 2) -> str:
        """Format a number as currency.
        
        Args:
            value: The value to format
            currency: The currency code (default: GBP)
            decimal_places: Number of decimal places (default: 2)
            
        Returns:
            Formatted currency string
        """
        try:
            if currency == 'GBP':
                # Use locale.currency but control decimal places
                if decimal_places == 0:
                    # Format as integer with currency symbol and grouping
                    formatted = f"£{value:,.0f}"
                else:
                    formatted = locale.currency(value, grouping=True)
                return formatted
            else:
                # For non-GBP currencies
                if decimal_places == 0:
                    return f"{currency} {value:,.0f}"
                else:
                    return f"{currency} {value:,.{decimal_places}f}"
        except:
            if decimal_places == 0:
                return f"{currency} {value:,.0f}"
            else:
                return f"{currency} {value:,.{decimal_places}f}"
