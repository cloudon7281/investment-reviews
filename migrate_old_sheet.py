#!/usr/bin/env python3
"""
One-time migration script to import historical data from old Google Sheet.

Reads sparse historical data, forward-fills to daily frequency, and merges
into new Google Sheet while preserving existing data.
"""

import sys
import os
import yaml
import argparse
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List
import logging

from google_sheets_client import GoogleSheetsClient


class SheetMigrator:
    """Handles migration from old Google Sheet to new daily sheet."""
    
    def __init__(self, config_path: str, dry_run: bool = False):
        """Initialize the migrator.
        
        Args:
            config_path: Path to migration_config.yaml
            dry_run: If True, show what would be done without doing it
        """
        self.dry_run = dry_run
        
        # Load migration configuration
        with open(os.path.expanduser(config_path), 'r') as f:
            self.migration_config = yaml.safe_load(f)
        
        # Load main config for new sheet details
        main_config_path = self.migration_config.get('main_config', 'config.yaml')
        self.sheets_client = GoogleSheetsClient(main_config_path)
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        if dry_run:
            self.logger.info("DRY RUN MODE - No actual changes will be made")
    
    def migrate(self) -> bool:
        """Execute the migration process.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("="*80)
            self.logger.info("MIGRATING HISTORICAL DATA FROM OLD SHEET")
            self.logger.info("="*80)
            
            # Step 1: Read old sheet data
            self.logger.info("Reading old Google Sheet...")
            old_data_df = self._read_old_sheet()
            self.logger.info(f"Old sheet: {len(old_data_df)} rows, {len(old_data_df.columns)} columns")
            self.logger.info(f"Date range: {old_data_df['Date'].min()} to {old_data_df['Date'].max()}")
            
            # Step 2: Forward-fill to daily frequency
            self.logger.info("Forward-filling sparse data to daily frequency...")
            daily_df = self._forward_fill_to_daily(old_data_df)
            self.logger.info(f"Forward-filled to {len(daily_df)} daily rows")
            
            # Step 3: Read new sheet data
            self.logger.info("Reading new Google Sheet...")
            new_data_df = self._read_new_sheet()
            self.logger.info(f"New sheet: {len(new_data_df)} rows, {len(new_data_df.columns)} columns")
            
            # Step 4: Merge data
            self.logger.info("Merging old and new data...")
            merged_df = self._merge_data(daily_df, new_data_df)
            self.logger.info(f"Merged: {len(merged_df)} rows, {len(merged_df.columns)} columns")
            
            # Step 5: Write back to new sheet
            if not self.dry_run:
                self.logger.info("Writing merged data to new Google Sheet...")
                self._write_merged_data(merged_df)
                self.logger.info("✓ Migration complete")
            else:
                self.logger.info("[DRY RUN] Would write merged data")
                self.logger.info(f"Preview of merged columns: {list(merged_df.columns)}")
                self.logger.info(f"Preview of first 5 rows:")
                print(merged_df.head())
            
            return True
            
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            self.logger.exception("Full traceback:")
            return False
    
    def _read_old_sheet(self) -> pd.DataFrame:
        """Read data from old Google Sheet.
        
        Returns:
            DataFrame with old sheet data
        """
        old_config = self.migration_config['old_sheet']
        
        # Create temporary client for old sheet
        temp_config = {
            'google_sheets': {
                'credentials_path': self.migration_config.get('google_sheets', {}).get('credentials_path', 
                    self.sheets_client.config['google_sheets']['credentials_path']),
                'spreadsheet_id': old_config['spreadsheet_id'],
                'worksheet_name': old_config['worksheet_name']
            }
        }
        
        # Save temp config
        temp_config_path = '/tmp/migration_temp_config.yaml'
        with open(temp_config_path, 'w') as f:
            yaml.dump(temp_config, f)
        
        old_client = GoogleSheetsClient(temp_config_path)
        
        # Read all data
        result = old_client.sheets.values().get(
            spreadsheetId=old_config['spreadsheet_id'],
            range=f"{old_config['worksheet_name']}!A:ZZ"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            raise ValueError("Old sheet is empty")
        
        # Pad shorter rows to match header length (Google Sheets API omits trailing empty cells)
        headers = values[0]
        num_cols = len(headers)
        data_rows = []
        for row in values[1:]:
            # Pad row with empty strings if it's shorter than the header
            padded_row = row + [''] * (num_cols - len(row))
            data_rows.append(padded_row)
        
        # Convert to DataFrame
        df = pd.DataFrame(data_rows, columns=headers)
        
        # Parse dates
        date_col = old_config['date_column']
        date_format = old_config.get('date_format', '%Y-%m-%d')
        df['Date'] = pd.to_datetime(df[date_col], format=date_format)
        
        # Drop rows with NaN dates
        df = df.dropna(subset=['Date'])
        
        # Sort by date
        df = df.sort_values('Date')
        
        # Apply column mapping and filter to only mapped columns
        column_mapping = self.migration_config.get('column_mapping', {})
        if column_mapping:
            # Keep only columns that are in the mapping (old column names)
            # Plus the Date column
            old_col_names = list(column_mapping.keys())
            columns_to_keep = ['Date'] + [col for col in old_col_names if col in df.columns]
            df = df[columns_to_keep]
            
            # Now rename using the mapping
            df = df.rename(columns=column_mapping)
            self.logger.info(f"Applied {len(column_mapping)} column mappings, keeping only mapped columns")
            
            # Convert values from thousands to pounds (multiply by 1000)
            # All columns except Date should be numeric and in thousands
            for col in df.columns:
                if col != 'Date':
                    # Convert to numeric, replacing any non-numeric values with 0
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    # Multiply by 1000 to convert from thousands to pounds
                    df[col] = df[col] * 1000
            self.logger.info(f"Converted values from thousands to pounds (multiplied by 1000)")
        else:
            self.logger.warning("No column_mapping defined - no old sheet data will be migrated")
            df = df[['Date']]  # Keep only Date column if no mapping
        
        return df
    
    def _forward_fill_to_daily(self, df: pd.DataFrame) -> pd.DataFrame:
        """Forward-fill sparse data to daily frequency.
        
        Args:
            df: DataFrame with sparse dates
            
        Returns:
            DataFrame with daily dates, values forward-filled
        """
        if not self.migration_config.get('options', {}).get('forward_fill', True):
            return df
        
        # Create complete date range
        date_range = pd.date_range(
            start=df['Date'].min(),
            end=df['Date'].max(),
            freq='D'
        )
        
        # Create new DataFrame with complete date range
        daily_df = pd.DataFrame({'Date': date_range})
        
        # Merge with existing data
        merged = daily_df.merge(df, on='Date', how='left')
        
        # Forward-fill all columns except Date
        for col in merged.columns:
            if col != 'Date':
                merged[col] = merged[col].ffill()
        
        return merged
    
    def _read_new_sheet(self) -> pd.DataFrame:
        """Read current data from new Google Sheet.
        
        Returns:
            DataFrame with new sheet data
        """
        result = self.sheets_client.sheets.values().get(
            spreadsheetId=self.sheets_client.spreadsheet_id,
            range=f"{self.sheets_client.worksheet_name}!A:ZZ"
        ).execute()
        
        values = result.get('values', [])
        if not values or len(values) < 2:
            # Empty sheet - return empty DataFrame with just headers
            return pd.DataFrame()
        
        # Pad shorter rows to match header length (Google Sheets API omits trailing empty cells)
        headers = values[0]
        num_cols = len(headers)
        data_rows = []
        for row in values[1:]:
            # Pad row with empty strings if it's shorter than the header
            padded_row = row + [''] * (num_cols - len(row))
            data_rows.append(padded_row)
        
        df = pd.DataFrame(data_rows, columns=headers)
        df['Date'] = pd.to_datetime(df['Date'])
        
        return df
    
    def _merge_data(self, old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
        """Merge old and new data.
        
        Args:
            old_df: Forward-filled old sheet data
            new_df: New sheet data (from value-over-time)
            
        Returns:
            Merged DataFrame
        """
        conflict_resolution = self.migration_config.get('options', {}).get('conflict_resolution', 'new')
        
        if new_df.empty:
            # No new data yet, just use old data
            return old_df
        
        # Only merge columns that exist in the new sheet
        # This ensures we don't create new columns, only populate existing ones
        new_sheet_columns = list(new_df.columns)
        
        self.logger.info(f"  New sheet columns: {new_sheet_columns}")
        self.logger.info(f"  Old sheet columns (after mapping): {list(old_df.columns)}")
        
        old_columns_to_merge = [col for col in old_df.columns if col in new_sheet_columns]
        
        self.logger.info(f"  Columns found in BOTH sheets: {old_columns_to_merge}")
        self.logger.info(f"Merging {len(old_columns_to_merge)-1} columns from old sheet into new sheet: {[c for c in old_columns_to_merge if c != 'Date']}")
        
        # Filter old_df to only columns that exist in new sheet
        old_df_filtered = old_df[old_columns_to_merge]
        
        # Get all columns (only those in new sheet)
        all_columns = new_sheet_columns
        
        # Merge on Date
        if conflict_resolution == 'new':
            # New data takes precedence
            merged = new_df.merge(old_df_filtered, on='Date', how='outer', suffixes=('', '_old'))
            
            self.logger.info(f"  After merge: {len(merged)} rows, {len(merged.columns)} columns")
            self.logger.info(f"  Columns with '_old' suffix: {[c for c in merged.columns if c.endswith('_old')]}")
            
            # For overlapping columns, prefer new (non-suffixed) version
            for col in all_columns:
                if col == 'Date':
                    continue
                if f"{col}_old" in merged.columns:
                    # Replace empty/zero values in new column with old values
                    if col in merged.columns:
                        # Check how many values need updating (NaN, empty string, or 0)
                        needs_update = merged[col].isna() | (merged[col] == '') | (merged[col] == 0)
                        values_updated = needs_update.sum()
                        
                        # Use old values where new values are empty/zero/NaN
                        merged.loc[needs_update, col] = merged.loc[needs_update, f"{col}_old"]
                        self.logger.info(f"  Updated {values_updated} empty/zero values in '{col}' from old data")
                    else:
                        merged[col] = merged[f"{col}_old"]
                        self.logger.info(f"  Created '{col}' column from old data")
                    # Drop the _old column
                    merged = merged.drop(columns=[f"{col}_old"])
        else:
            # Old data takes precedence
            merged = old_df_filtered.merge(new_df, on='Date', how='outer', suffixes=('', '_new'))
            
            for col in all_columns:
                if col == 'Date':
                    continue
                if f"{col}_new" in merged.columns:
                    if col in merged.columns:
                        # Keep old values, only use new where old is empty/zero/NaN
                        needs_update = merged[col].isna() | (merged[col] == '') | (merged[col] == 0)
                        values_updated = needs_update.sum()
                        merged.loc[needs_update, col] = merged.loc[needs_update, f"{col}_new"]
                        self.logger.info(f"  Filled {values_updated} empty values in '{col}' from new data")
                    else:
                        merged[col] = merged[f"{col}_new"]
                        self.logger.info(f"  Created '{col}' column from new data")
                    merged = merged.drop(columns=[f"{col}_new"])
        
        # Sort by date and reorder columns
        merged = merged.sort_values('Date')
        merged = merged[all_columns]
        
        # Fill any remaining NaN with 0
        merged = merged.fillna(0)
        
        return merged
    
    def _write_merged_data(self, df: pd.DataFrame) -> None:
        """Write merged data back to new Google Sheet.
        
        Args:
            df: Merged DataFrame to write
        """
        # Convert DataFrame to list of lists
        # Format dates as strings
        df_copy = df.copy()
        df_copy['Date'] = df_copy['Date'].dt.strftime('%Y-%m-%d')
        
        # Debug: Check if specific migrated columns have non-zero data
        check_cols = ['Morgan Stanley', 'BLEND', 'Crypto', 'Savings']
        for col in check_cols:
            if col in df_copy.columns:
                non_zero_count = (df_copy[col] != 0).sum()
                sample_val = df_copy[col].iloc[0] if len(df_copy) > 0 else 'N/A'
                # Show numeric value if available
                try:
                    numeric_val = float(str(sample_val).replace('£', '').replace(',', ''))
                    self.logger.info(f"  Column '{col}': {non_zero_count} non-zero values, first value: {sample_val} (numeric: {numeric_val:.2f})")
                except:
                    self.logger.info(f"  Column '{col}': {non_zero_count} non-zero values, first value: {sample_val}")
            else:
                self.logger.info(f"  Column '{col}': NOT FOUND in final data")
        
        data = [df_copy.columns.tolist()] + df_copy.values.tolist()
        
        # Debug: Show sample of first row with data
        if len(data) > 1:
            self.logger.info(f"  Sample row 1: Date={data[1][0]}, first 5 cols: {data[1][:5]}")
        
        # Clear existing data
        self.sheets_client.sheets.values().clear(
            spreadsheetId=self.sheets_client.spreadsheet_id,
            range=f"{self.sheets_client.worksheet_name}!A:ZZ"
        ).execute()
        
        # Write merged data
        body = {'values': data}
        self.sheets_client.sheets.values().update(
            spreadsheetId=self.sheets_client.spreadsheet_id,
            range=f"{self.sheets_client.worksheet_name}!A1",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        self.logger.info(f"Wrote {len(data)} rows, {len(data[0])} columns to new sheet")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate historical data from old Google Sheet to new sheet'
    )
    parser.add_argument(
        '--config',
        default='migration_config.yaml',
        help='Path to migration configuration file (default: migration_config.yaml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    
    args = parser.parse_args()
    
    # Run migration
    migrator = SheetMigrator(args.config, dry_run=args.dry_run)
    success = migrator.migrate()
    
    if success:
        print("\n" + "="*80)
        print("✓ Migration completed successfully")
        if not args.dry_run:
            print("  Check your Google Sheet to verify the data")
        print("="*80)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

