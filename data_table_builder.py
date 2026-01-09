"""
DataTableBuilder - Common data preparation for console and Numbers output.

This module provides a unified way to build table data from DataFrames
using configuration from reporter_definitions.py, eliminating duplication
between console and Numbers output formatting.
"""

import pandas as pd
import math
from typing import Dict, List, Any, Optional, Tuple
from logger import logger
import reporter_definitions as rd


class DataTableBuilder:
    """Builds standardized table data with formatting metadata for both console and Numbers output."""
    
    def __init__(self):
        """Initialize the data table builder."""
        pass
    
    def build_table(self, df: pd.DataFrame, config: Dict[str, Any], title: str = None) -> List[Dict[str, Any]]:
        """Build standardized table data with raw values and format metadata.
        
        Args:
            df: DataFrame containing the data
            config: Configuration dictionary from reporter_definitions.py
            title: Optional title for the table
            
        Returns:
            List of dictionaries, each containing:
            - 'raw_value': The original value from the DataFrame
            - 'format_config': Format configuration dictionary
            - 'style': Style name determined by threshold logic
            - 'title': Table title (if provided)
        """
        if df.empty:
            return []
        
        logger.debug(f"Building table with {len(df)} rows using config: {config.get('headers', [])}")
        
        table_data = []
        
        for row_idx, row in df.iterrows():
            row_data = []
            
            # Check if this row has a row type marker (for visual styling)
            row_type = row.get('_row_type', None) if '_row_type' in df.columns else None
            
            for col_idx, col_name in enumerate(config['columns']):
                try:
                    # Get the raw value from the DataFrame, handle missing columns gracefully
                    if col_name in row.index:
                        raw_value = row[col_name]
                    else:
                        raw_value = None
                        logger.debug(f"Column {col_name} not found in DataFrame, using None")
                    
                    # Get format configurations
                    format_config = config['column_formats'][col_idx] if col_idx < len(config['column_formats']) else None
                    threshold_config = config['column_thresholds'][col_idx] if col_idx < len(config['column_thresholds']) else None
                    
                    # Use format configuration (already a dictionary or None)
                    format_dict = format_config
                    
                    logger.debug(f"Format config for column {col_name}: {format_dict}, type: {type(format_dict)}")
                    
                    
                    # Build the standardized data structure
                    cell_data = self._build_cell_data(
                        raw_value, 
                        col_name, 
                        format_dict, 
                        threshold_config
                    )
                    
                    row_data.append(cell_data)
                    
                except Exception as e:
                    logger.error(f"Error processing column {col_name}: {str(e)}")
                    # Create a fallback cell data structure
                    row_data.append({
                        'raw_value': '',
                        'format_config': None,
                        'style': None
                    })
            
            # Add row type metadata if present (but don't include _row_type column itself in the row)
            row_dict = {'cells': row_data}
            if row_type:
                row_dict['row_type'] = row_type
            
            table_data.append(row_dict)
        
        logger.debug(f"Built table with {len(table_data)} rows")
        
        # Add title to the table data structure
        if title:
            return {
                'title': title,
                'data': table_data
            }
        else:
            return table_data
    
    def _build_cell_data(self, raw_value: Any, col_name: str, format_config: Optional[Dict], threshold_config: Optional[Dict]) -> Dict[str, Any]:
        """Build standardized cell data with raw values and format metadata.
        
        Args:
            raw_value: The original value from the DataFrame
            col_name: Name of the column
            format_config: Format configuration dictionary
            threshold_config: Threshold configuration for styling
            
        Returns:
            Dictionary with raw value, format metadata, and determined style
        """
        # Handle None/NaN values
        if pd.isna(raw_value) or raw_value is None:
            return {
                'raw_value': '',
                'format_config': None,
                'style': None
            }
        
        # Handle tuple values (value, currency)
        if isinstance(raw_value, tuple) and len(raw_value) == 2:
            value, currency = raw_value
            
            # Override currency in format config if this is a currency column
            if format_config and format_config.get('type') == 'currency':
                format_config = format_config.copy()
                format_config['currency'] = currency
            
            # Use the value for threshold determination and display
            raw_value = value
        
        # Apply threshold logic to determine style
        style = self._determine_style(raw_value, threshold_config)
        
        return {
            'raw_value': raw_value,
            'format_config': format_config,
            'style': style
        }
    
    def _determine_style(self, value: Any, threshold_config: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """Determine style based on value thresholds.
        
        Args:
            value: The value to check against thresholds
            threshold_config: List of threshold dictionaries, each with 'threshold' and 'style' keys
            
        Returns:
            Style name ('red', 'amber', 'green') if thresholds are met, None otherwise
        """
        # First check if the value is a number
        if not isinstance(value, (int, float)):
            return None
        
        # If no threshold config, return None
        if not threshold_config:
            return None
            
        # Walk through thresholds in ascending order
        for threshold_dict in threshold_config:
            threshold = threshold_dict['threshold']
            style = threshold_dict['style']
            
            # If we hit a None threshold or value is less than threshold, return the style
            if threshold is None or value < threshold:
                return style
                
        return None
    
