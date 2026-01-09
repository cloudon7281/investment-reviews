"""
Numbers table writer for portfolio reports.
"""

from typing import List, Dict, Any, Optional
import math
import warnings
import pandas as pd
from numbers_parser import Style, RGB
from logger import logger


class NumbersTableWriter:
    """Writes formatted tables to Numbers documents."""
    
    def __init__(self, numbers_doc, numbers_filename: str = None):
        """Initialize the Numbers table writer.
        
        Args:
            numbers_doc: The Numbers document object
            numbers_filename: Optional filename for the Numbers document
        """
        self.numbers_doc = numbers_doc
        self.numbers_filename = numbers_filename
        
        # Create styles for color coding (Numbers-specific implementation detail)
        self.red_style = self.numbers_doc.add_style(
            name="Red Background",
            bg_color=RGB(255, 0, 0)
        )
        self.amber_style = self.numbers_doc.add_style(
            name="Amber Background",
            bg_color=RGB(255, 165, 0)
        )
        self.green_style = self.numbers_doc.add_style(
            name="Green Background",
            bg_color=RGB(0, 255, 0)
        )
        
        logger.debug("Created styles:")
        logger.debug(f"Red style: {self.red_style}")
        logger.debug(f"Amber style: {self.amber_style}")
        logger.debug(f"Green style: {self.green_style}")
    
    def write_table(self, table_data: List[List[Dict[str, Any]]], config: Dict[str, Any], sheet_name: str, table_name: str = None) -> None:
        """Write a table to Numbers document.
        
        Args:
            table_data: List of rows, each row is a list of cell data dictionaries, or dict with 'title' and 'data' keys
            config: Column configuration from reporter_definitions
            sheet_name: Name of the sheet to create/use
            table_name: Optional name for the table (defaults to sheet_name or title from table_data)
        """
        # Handle new data structure with title
        if isinstance(table_data, dict) and 'title' in table_data and 'data' in table_data:
            title = table_data['title']
            actual_data = table_data['data']
            # Use title as table_name if not provided
            if table_name is None:
                table_name = title
        else:
            title = None
            actual_data = table_data
        if not self.numbers_filename:
            return
            
        try:
            logger.debug(f"Creating/accessing sheet: {sheet_name}")
            
            # Handle sheet creation/reuse logic
            if sheet_name not in self.numbers_doc.sheets:
                # Check if we can reuse the default "Sheet 1"
                if len(self.numbers_doc.sheets) == 1 and self.numbers_doc.sheets[0].name == "Sheet 1":
                    # Reuse and rename the default sheet
                    default_sheet = self.numbers_doc.sheets[0]
                    default_sheet.name = sheet_name
                    logger.debug(f"Reused and renamed default sheet to: {sheet_name}")
                else:
                    # Create new sheet
                    logger.debug(f"Adding new sheet: {sheet_name}")
                    self.numbers_doc.add_sheet(sheet_name)
            
            # Get the sheet
            sheet = self.numbers_doc.sheets[sheet_name]
            logger.debug(f"Got sheet: {sheet_name}")
            
            # Handle table creation/reuse logic
            if len(sheet.tables) == 0:
                # No tables exist, add a new one
                table = sheet.add_table(table_name or sheet_name)
                logger.debug(f"Added new table: {table.name}")
            elif len(sheet.tables) == 1 and sheet.tables[0].name == "Table 1":
                # Reuse and rename the default table
                default_table = sheet.tables[0]
                default_table.name = table_name or sheet_name
                table = default_table
                logger.debug(f"Reused and renamed default table to: {table.name}")
            else:
                # Tables exist and are not the default, add another one
                table = sheet.add_table(table_name or f"{sheet_name} - Table {len(sheet.tables) + 1}")
                logger.debug(f"Added new table: {table.name}")
            
            # Add headers
            logger.debug("Adding headers")
            for col, header in enumerate(config['headers']):
                logger.debug(f"Setting header {col}: {header}")
                self._write_to_numbers(table, 0, col, header, {'bold': True})
            
            # Add data rows (with separator rows between groups for visual distinction)
            logger.debug("Adding data rows")
            numbers_row_idx = 1  # Track actual row index in Numbers table
            prev_row_type = None
            
            for data_idx, row_data in enumerate(actual_data):
                logger.debug(f"Processing data row {data_idx}")
                
                # Handle new structure with row type metadata
                if isinstance(row_data, dict) and 'cells' in row_data:
                    row_cells = row_data['cells']
                    row_type = row_data.get('row_type', None)
                else:
                    # Backward compatibility: treat as list of cells
                    row_cells = row_data
                    row_type = None
                
                # Add separator row when transitioning between row types (same as console)
                if row_type and prev_row_type and row_type != prev_row_type:
                    logger.debug(f"Adding separator row at Numbers row {numbers_row_idx}")
                    # Write separator row (dashes in each column)
                    for col_idx in range(len(config['headers'])):
                        self._write_to_numbers(table, numbers_row_idx, col_idx, '---', None, None)
                    numbers_row_idx += 1
                prev_row_type = row_type
                
                for col_idx, cell_data in enumerate(row_cells):
                    try:
                        # Use simplified cell data structure
                        raw_value = cell_data['raw_value']
                        format_config = cell_data['format_config']
                        style = cell_data.get('style')
                        
                        logger.debug(f"Setting cell ({numbers_row_idx}, {col_idx}) to {raw_value}")
                        logger.debug(f"Format config: {format_config}, type: {type(format_config)}")
                        
                        # Format the value for Numbers output
                        formatted_value = self._format_for_numbers(raw_value, format_config)
                        
                        logger.debug(f"Formatted value: {formatted_value}, type: {type(formatted_value)}")
                        
                        # Write to Numbers with style
                        self._write_to_numbers(table, numbers_row_idx, col_idx, formatted_value, format_config, style)
                    except Exception as e:
                        logger.error(f"Error setting cell ({numbers_row_idx}, {col_idx}): {str(e)}")
                        raise
                
                # Move to next row after processing all cells
                numbers_row_idx += 1
                        
            # Adjust column widths for text columns
            logger.debug("Adjusting column widths")
            for col_idx, (header, format_config) in enumerate(zip(config['headers'], config['column_formats'])):
                if format_config is None or format_config == 'text':  # Text column
                    # Get all values in this column (including header)
                    column_values = [header]  # Start with header
                    for row_data in actual_data:
                        # Handle new structure with row type metadata
                        if isinstance(row_data, dict) and 'cells' in row_data:
                            row_cells = row_data['cells']
                        else:
                            # Backward compatibility: treat as list of cells
                            row_cells = row_data
                        
                        if col_idx < len(row_cells):
                            cell_data = row_cells[col_idx]
                            raw_value = cell_data['raw_value']
                            if raw_value is not None and raw_value != '':
                                column_values.append(str(raw_value))
                    
                    # Calculate max width using old algorithm: 7 points per character + 10 padding
                    max_length = max(len(str(val)) for val in column_values) if column_values else 10
                    max_width = 5 * max_length + 24
                    
                    logger.debug(f"Setting column {col_idx} width to {max_width}")
                    table.col_width(col_idx, max_width)
            
            # Delete any extra rows after our data
            last_row = len(actual_data)  # +1 for header row is already included in the loop above
            logger.debug(f"Deleting rows after row {last_row}")
            if last_row + 1 < table.num_rows:
                # Delete rows from the end of the table
                rows_to_delete = table.num_rows - (last_row + 1)
                logger.debug(f"Deleting {rows_to_delete} rows from the end of the table")
                table.delete_row(num_rows=rows_to_delete)
                logger.debug(f"Successfully deleted {rows_to_delete} rows, new table size: {table.num_rows}")
            
            # Delete any extra columns after our data
            last_col = len(config['headers'])
            logger.debug(f"Deleting columns after column {last_col}")
            if last_col < table.num_cols:
                # Delete columns from the end of the table
                cols_to_delete = table.num_cols - last_col
                logger.debug(f"Deleting {cols_to_delete} columns from the end of the table")
                table.delete_column(num_cols=cols_to_delete)
                logger.debug(f"Successfully deleted {cols_to_delete} columns, new table size: {table.num_cols}")
            
            logger.debug(f"Successfully created table: {table.name}")
            
        except Exception as e:
            logger.error(f"Error creating Numbers table: {str(e)}")
            raise
    
    
    def _write_to_numbers(self, table, row: int, col: int, value: Any, format_config: Optional[Dict] = None, style: Optional[str] = None) -> None:
        """Write a value to a Numbers table cell with optional formatting."""
        try:
            # Handle None values
            if value is None:
                value = ''
            # Handle NaN values
            elif isinstance(value, float) and math.isnan(value):
                value = 'NaN'
            # Handle currency tuples
            elif isinstance(value, tuple):
                value, currency = value
                if isinstance(value, float) and math.isnan(value):
                    value = 'NaN'
                elif currency is None:
                    logger.warning(f"Skipping currency formatting for value {value} as currency is None")
                else:
                    # Handle case where format_config might be a string instead of dict
                    if isinstance(format_config, dict):
                        decimal_places = format_config.get('decimal_places', 2)
                    else:
                        decimal_places = 2  # Default to 2 decimal places
                    format_config = {'currency': currency, 'decimal_places': decimal_places}
            
            # Round floating-point values to prevent precision warnings
            if isinstance(value, float) and not math.isnan(value) and value != 'NaN':
                # Round to 2 decimal places to prevent numbers_parser precision warnings
                value = round(value, 2)

            logger.debug(f"Writing to Numbers table - Row: {row}, Col: {col}, Value: {value}, Type: {type(value)}, Format: {format_config}, Style: {style}")
            
            # Write the value with warning suppression
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                table.write(row, col, value)
            logger.debug("Successfully wrote value to cell")
            
            # Skip formatting for NaN values
            if value == 'NaN':
                logger.debug("Skipping formatting for NaN value")
                return
                
            # Apply formatting if specified
            if format_config and isinstance(format_config, dict):
                logger.debug(f"Applying formatting with options: {format_config}")
                
                # Apply date formatting if specified
                if format_config.get('type') == 'date':
                    # Format dates as DD/MM/YY for Numbers
                    if hasattr(value, 'strftime'):
                        value = value.strftime('%d/%m/%y')
                    else:
                        # If it's already a string, try to parse and reformat
                        try:
                            from datetime import datetime
                            if isinstance(value, str):
                                # Try different date formats and convert to DD/MM/YY
                                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                    try:
                                        dt = datetime.strptime(value, fmt)
                                        value = dt.strftime('%d/%m/%y')
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    value = str(value)  # Fallback to original string
                            else:
                                value = str(value)
                        except:
                            value = str(value)
                    
                    # Write the formatted date value
                    table.write(row, col, value)
                    logger.debug("Successfully wrote formatted date value")
                    return
                
                # Apply currency formatting if specified
                if 'currency' in format_config:
                    logger.debug(f"Applying currency formatting with currency: {format_config['currency']}")
                    if format_config['currency'] is None:
                        logger.warning(f"Skipping currency formatting for value {value} as currency is None")
                        return
                    table.set_cell_formatting(
                        row, col,
                        "currency",
                        currency_code=format_config['currency'],
                        decimal_places=format_config.get('decimal_places', 2) if isinstance(format_config, dict) else 2,
                        show_thousands_separator=True,
                        use_accounting_style=False
                    )
                    logger.debug("Successfully applied formatting")
                    return
                
                # Apply number formatting
                logger.debug("Applying number formatting")
                if isinstance(format_config, dict) and format_config.get('type') == 'percentage':
                    table.set_cell_formatting(
                        row, col,
                        "percentage",
                        decimal_places=format_config.get('decimal_places', 2) if isinstance(format_config, dict) else 2,
                        show_thousands_separator=False
                    )
                elif isinstance(format_config, dict) and format_config.get('type') == 'currency' and format_config.get('currency') is not None:
                    table.set_cell_formatting(
                        row, col,
                        "currency",
                        decimal_places=format_config.get('decimal_places', 2) if isinstance(format_config, dict) else 2,
                        show_thousands_separator=True
                    )
                logger.debug("Successfully applied formatting")
                
            # Apply styling if provided
            if style:
                style_obj = self._get_style_object(style)
                if style_obj:
                    logger.debug(f"Applying style: {style}")
                    table.set_cell_style(row, col, style_obj)
                    logger.debug("Successfully applied style")
                    
        except Exception as e:
            logger.error(f"Error writing to Numbers table: {str(e)}")
            raise
    
    
    def _get_style_object(self, style_name: str) -> Optional[Style]:
        """Get a style object based on style name.
        
        Args:
            style_name: Style name ('red', 'amber', 'green')
            
        Returns:
            Style object if found, None otherwise
        """
        if style_name == 'red':
            return self.red_style
        elif style_name == 'amber':
            return self.amber_style
        elif style_name == 'green':
            return self.green_style
        else:
            return None
    
    def _format_for_numbers(self, value: Any, format_config: Optional[Dict]) -> Any:
        """Format a value for Numbers output based on format configuration.
        
        Args:
            value: The value to format
            format_config: Format configuration dictionary
            
        Returns:
            Formatted value for Numbers output
        """
        # Handle None/NaN values
        if pd.isna(value) or value is None or value == '':
            return ''
        
        # Handle missing format configuration
        if not format_config or not isinstance(format_config, dict) or 'type' not in format_config:
            return value
        
        format_type = format_config['type']
        
        if format_type == 'currency':
            currency = format_config.get('currency', 'GBP') if isinstance(format_config, dict) else 'GBP'
            return (value, currency)  # Tuple for Numbers currency formatting
        elif format_type == 'integer':
            return int(value) if not math.isnan(value) else 0
        else:
            return value
    
