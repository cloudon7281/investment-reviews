#!/usr/bin/env python3
"""
Google Sheets API client for portfolio updates.

Handles authentication, reading, writing, and chart updates.
"""

import os
import yaml
from typing import List, Dict, Optional, Any
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSheetsClient:
    """Client for interacting with Google Sheets API."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, config_path: str):
        """Initialize the Google Sheets client.
        
        Args:
            config_path: Path to config.yaml file
        """
        # Load configuration
        with open(os.path.expanduser(config_path), 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Extract Google Sheets configuration
        gs_config = self.config['google_sheets']
        self.spreadsheet_id = gs_config['spreadsheet_id']
        self.worksheet_name = gs_config['worksheet_name']
        credentials_path = os.path.expanduser(gs_config['credentials_path'])
        
        # Authenticate
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=self.SCOPES)
        
        # Build service
        self.service = build('sheets', 'v4', credentials=credentials)
        self.sheets = self.service.spreadsheets()
    
    def get_headers(self) -> List[str]:
        """Get column headers from the first row.
        
        Returns:
            List of column header names
        """
        result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!1:1"
        ).execute()
        
        values = result.get('values', [[]])
        return values[0] if values else []
    
    def get_last_row_values(self) -> Dict[str, Any]:
        """Get the last row of data as a dictionary.
        
        Returns:
            Dictionary mapping column headers to values in last row
        """
        # Get all data
        result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:ZZ"
        ).execute()
        
        values = result.get('values', [])
        if len(values) < 2:  # Need header + at least one data row
            return {}
        
        headers = values[0]
        last_row = values[-1]
        
        # Pad last_row if shorter than headers
        last_row = last_row + [''] * (len(headers) - len(last_row))
        
        return dict(zip(headers, last_row))
    
    def get_last_row_formulas(self) -> Dict[str, str]:
        """Get the last row with formulas (not evaluated values).
        
        Returns:
            Dictionary mapping column headers to formulas/values in last row
        """
        # Get formulas using valueRenderOption='FORMULA'
        result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:ZZ",
            valueRenderOption='FORMULA'
        ).execute()
        
        values = result.get('values', [])
        if len(values) < 2:  # Need header + at least one data row
            return {}
        
        headers = values[0]
        last_row = values[-1]
        
        # Pad last_row if shorter than headers
        last_row = last_row + [''] * (len(headers) - len(last_row))
        
        return dict(zip(headers, last_row))
    
    def get_row_count(self) -> int:
        """Get the number of rows in the sheet (including header).

        Returns:
            Number of rows
        """
        result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:A"
        ).execute()

        values = result.get('values', [])
        return len(values)

    def get_last_row_formats(self) -> List[Optional[Dict]]:
        """Get the cell formats from the last row.

        Returns:
            List of format dictionaries for each cell in the last row.
            Each format dict contains 'numberFormat' and other formatting info.
            Returns None for cells with no specific formatting.
        """
        import logging
        logger = logging.getLogger(__name__)

        row_count = self.get_row_count()
        if row_count < 2:
            logger.debug("get_last_row_formats: fewer than 2 rows, returning empty")
            return []

        sheet_id = self._get_sheet_id()
        logger.info(f"Getting formats from row {row_count}")

        # Get spreadsheet with cell formatting data for the last row only
        result = self.sheets.get(
            spreadsheetId=self.spreadsheet_id,
            ranges=[f"{self.worksheet_name}!{row_count}:{row_count}"],
            fields='sheets.data.rowData.values.userEnteredFormat'
        ).execute()

        formats = []
        try:
            row_data = result['sheets'][0]['data'][0].get('rowData', [])
            if row_data:
                cells = row_data[0].get('values', [])
                for col_idx, cell in enumerate(cells):
                    cell_format = cell.get('userEnteredFormat')
                    formats.append(cell_format)
                    # Log interesting formats (non-None, especially numberFormat)
                    if cell_format and 'numberFormat' in cell_format:
                        logger.info(f"  Column {col_idx}: numberFormat = {cell_format['numberFormat']}")
        except (KeyError, IndexError) as e:
            logger.warning(f"Error parsing format data: {e}")

        logger.info(f"Retrieved {len(formats)} format entries, {sum(1 for f in formats if f)} non-empty")
        return formats

    def apply_row_formatting(self, row_index: int, formats: List[Optional[Dict]]) -> None:
        """Apply formatting to a specific row.

        Args:
            row_index: 1-based row index to format
            formats: List of format dictionaries (from get_last_row_formats)
        """
        import logging
        logger = logging.getLogger(__name__)

        if not formats:
            logger.debug("apply_row_formatting: no formats to apply")
            return

        sheet_id = self._get_sheet_id()
        requests = []

        for col_index, fmt in enumerate(formats):
            if fmt is not None:
                # Build a request to update this cell's format
                requests.append({
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': row_index - 1,  # 0-based
                            'endRowIndex': row_index,
                            'startColumnIndex': col_index,
                            'endColumnIndex': col_index + 1
                        },
                        'cell': {
                            'userEnteredFormat': fmt
                        },
                        'fields': 'userEnteredFormat'
                    }
                })

        if requests:
            logger.info(f"Applying {len(requests)} format updates to row {row_index}")
            self.sheets.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': requests}
            ).execute()
            logger.info("Formatting applied successfully")

    def append_row(self, row_data: List[Any], inherit_formatting: bool = False) -> None:
        """Append a single row of data to the sheet.

        Args:
            row_data: List of values to append (must match column count)
            inherit_formatting: If True, copy formatting from the previous row
        """
        # Get formatting from last row before appending (if requested)
        formats = None
        if inherit_formatting:
            formats = self.get_last_row_formats()

        body = {
            'values': [row_data]
        }

        self.sheets.values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:A",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()

        # Apply formatting to the new row
        if formats:
            new_row_index = self.get_row_count()  # Row just added
            self.apply_row_formatting(new_row_index, formats)
    
    def insert_column(self, column_index: int, header_name: str, backfill_value: Any = 0) -> None:
        """Insert a new column at the specified index.
        
        Args:
            column_index: 0-based column index where to insert
            header_name: Name for the column header
            backfill_value: Value to fill all existing rows with (default: 0)
        """
        # Get current row count
        row_count = self.get_row_count()
        
        # Insert blank column
        request = {
            'insertDimension': {
                'range': {
                    'sheetId': self._get_sheet_id(),
                    'dimension': 'COLUMNS',
                    'startIndex': column_index,
                    'endIndex': column_index + 1
                }
            }
        }
        
        self.sheets.batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': [request]}
        ).execute()
        
        # Set header
        column_letter = self._column_number_to_letter(column_index)
        self.sheets.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!{column_letter}1",
            valueInputOption='USER_ENTERED',
            body={'values': [[header_name]]}
        ).execute()
        
        # Backfill existing rows (skip header)
        if row_count > 1:
            backfill_data = [[backfill_value]] * (row_count - 1)
            self.sheets.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.worksheet_name}!{column_letter}2:{column_letter}{row_count}",
                valueInputOption='USER_ENTERED',
                body={'values': backfill_data}
            ).execute()
    
    def update_chart_ranges(self, chart_title: str, new_row_count: int, new_col_count: Optional[int] = None) -> None:
        """Update chart data range to include new rows/columns.
        
        Args:
            chart_title: Title of the chart to update
            new_row_count: New total row count (including header)
            new_col_count: Optional new column count (if columns were added)
        """
        # Get spreadsheet to find chart
        spreadsheet = self.sheets.get(spreadsheetId=self.spreadsheet_id).execute()
        
        sheet_id = self._get_sheet_id()
        charts = []
        
        # Find charts in the sheet
        for sheet in spreadsheet.get('sheets', []):
            if sheet['properties']['sheetId'] == sheet_id:
                charts = sheet.get('charts', [])
                break
        
        # Find the specific chart by title
        target_chart = None
        for chart in charts:
            if chart.get('spec', {}).get('title') == chart_title:
                target_chart = chart
                break
        
        if not target_chart:
            print(f"Warning: Chart '{chart_title}' not found, skipping update")
            return
        
        # Update the chart spec with new ranges
        chart_id = target_chart['chartId']
        spec = target_chart['spec']
        
        # Update row ranges in the spec
        # This is complex and depends on chart type - for now, we'll update the domain and series ranges
        # The actual implementation depends on chart structure
        
        update_request = {
            'updateChartSpec': {
                'chartId': chart_id,
                'spec': spec  # Would need to modify endRowIndex in spec
            }
        }
        
        # Note: Full implementation would recursively update all sourceRange objects in spec
        # For initial version, charts can be manually adjusted or recreated
        print(f"Chart update for '{chart_title}' - manual adjustment may be needed")
    
    def _get_sheet_id(self) -> int:
        """Get the sheet ID (not spreadsheet ID) for the worksheet.
        
        Returns:
            Integer sheet ID
        """
        spreadsheet = self.sheets.get(spreadsheetId=self.spreadsheet_id).execute()
        
        for sheet in spreadsheet.get('sheets', []):
            if sheet['properties']['title'] == self.worksheet_name:
                return sheet['properties']['sheetId']
        
        raise ValueError(f"Worksheet '{self.worksheet_name}' not found")
    
    @staticmethod
    def _column_number_to_letter(n: int) -> str:
        """Convert 0-based column number to letter (0='A', 25='Z', 26='AA', etc.).
        
        Args:
            n: 0-based column index
            
        Returns:
            Column letter(s)
        """
        result = ""
        while True:
            result = chr(n % 26 + ord('A')) + result
            n = n // 26
            if n == 0:
                break
            n -= 1  # Adjust for 0-based indexing
        return result
    
    def upload_csv_data(self, csv_path: str) -> None:
        """Upload CSV data to Google Sheet.
        
        Args:
            csv_path: Path to CSV file to upload
        """
        import csv
        
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            data = list(reader)
        
        # Clear existing data first
        self.sheets.values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:ZZ"
        ).execute()
        
        # Upload new data
        body = {'values': data}
        self.sheets.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A1",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        print(f"Uploaded {len(data)} rows, {len(data[0]) if data else 0} columns")


if __name__ == '__main__':
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Google Sheets client for portfolio data'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test authentication and connection')
    test_parser.add_argument('--config', required=True, help='Path to config.yaml')
    
    # Upload CSV command
    upload_parser = subparsers.add_parser('upload-csv', help='Upload CSV file to Google Sheet')
    upload_parser.add_argument('--csv', required=True, help='Path to CSV file to upload')
    upload_parser.add_argument('--config', required=True, help='Path to config.yaml')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'test':
            # Test authentication
            client = GoogleSheetsClient(args.config)
            print("✓ Authentication successful")
            print(f"✓ Connected to spreadsheet: {client.spreadsheet_id}")
            print(f"✓ Worksheet: {client.worksheet_name}")
            
            # Test getting headers
            headers = client.get_headers()
            print(f"✓ Current headers: {headers[:5]}..." if len(headers) > 5 else f"✓ Current headers: {headers}")
            
            # Test getting row count
            row_count = client.get_row_count()
            print(f"✓ Current row count: {row_count}")
            
        elif args.command == 'upload-csv':
            # Upload CSV data
            client = GoogleSheetsClient(args.config)
            print(f"Uploading CSV: {args.csv}")
            print(f"Target sheet: {client.worksheet_name}")
            
            client.upload_csv_data(args.csv)
            print("✓ Upload complete")
        
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

