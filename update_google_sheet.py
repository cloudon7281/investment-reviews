#!/usr/bin/env python3
"""
Daily portfolio update script for Google Sheets.

Runs portfolio analysis, extracts current values, and appends to Google Sheet.
Handles:
- New tags (add columns, backfill with 0)
- Missing tags (carry forward last value)
- Chart range updates
"""

import sys
import os
import subprocess
import yaml
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

from console_parser import ConsoleOutputParser
from google_sheets_client import GoogleSheetsClient


class PortfolioUpdater:
    """Coordinates daily portfolio updates to Google Sheets."""
    
    def __init__(self, config_path: str, dry_run: bool = False):
        """Initialize the updater.
        
        Args:
            config_path: Path to config.yaml
            dry_run: If True, show what would be done without doing it
        """
        self.config_path = config_path
        self.dry_run = dry_run
        
        # Load configuration
        with open(os.path.expanduser(config_path), 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set up logging
        self._setup_logging()
        
        # Initialize Google Sheets client (needed even in dry-run to read current state)
        self.sheets_client = GoogleSheetsClient(config_path)
        
        if dry_run:
            self.logger.info("DRY RUN MODE - No actual changes will be made")
    
    def _setup_logging(self) -> None:
        """Set up logging to file and console."""
        log_config = self.config.get('logging', {})
        log_dir = os.path.expanduser(log_config.get('log_dir', 'logs/daily_updates'))
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log file with timestamp
        log_file = os.path.join(log_dir, f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging to: {log_file}")
        
        # Clean up old logs
        self._cleanup_old_logs(log_dir, log_config.get('retention_days', 30))
    
    def _cleanup_old_logs(self, log_dir: str, retention_days: int) -> None:
        """Delete log files older than retention period.
        
        Args:
            log_dir: Directory containing log files
            retention_days: Number of days to keep logs
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        
        for filename in os.listdir(log_dir):
            if filename.startswith('update_') and filename.endswith('.log'):
                filepath = os.path.join(log_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_time < cutoff:
                    os.remove(filepath)
                    self.logger.debug(f"Deleted old log: {filename}")
    
    def _cleanup_old_output_files(self, output_dir: str, root_filename: str, number_to_keep: int) -> None:
        """Delete old output files, keeping only the most recent ones.
        
        Only deletes files matching the pattern <root_filename>_*.numbers.
        All other files in the directory are left untouched.
        
        Args:
            output_dir: Directory containing output files
            root_filename: Root filename pattern to match
            number_to_keep: Number of most recent files to keep
        """
        if not os.path.exists(output_dir):
            return
        
        # Find all files matching the pattern
        matching_files = []
        pattern_prefix = f"{root_filename}_"
        
        for filename in os.listdir(output_dir):
            if filename.startswith(pattern_prefix) and filename.endswith('.numbers'):
                filepath = os.path.join(output_dir, filename)
                if os.path.isfile(filepath):
                    matching_files.append(filepath)
        
        if len(matching_files) <= number_to_keep:
            return
        
        # Sort by modification time (oldest first)
        matching_files.sort(key=os.path.getmtime)
        
        # Delete oldest files until we're down to number_to_keep
        files_to_delete = matching_files[:-number_to_keep]
        
        for filepath in files_to_delete:
            filename = os.path.basename(filepath)
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would delete old output file: {filename}")
            else:
                try:
                    os.remove(filepath)
                    self.logger.info(f"Deleted old output file: {filename}")
                except OSError as e:
                    self.logger.warning(f"Could not delete {filename}: {e}")
    
    def run(self) -> bool:
        """Execute the daily update process.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Run portfolio analysis
            self.logger.info("="*80)
            self.logger.info("DAILY PORTFOLIO UPDATE - " + datetime.now().strftime('%Y-%m-%d'))
            self.logger.info("="*80)
            
            console_output = self._run_portfolio_analysis()
            
            # Clean up old output files (if new format is used)
            if hasattr(self, '_output_dir'):
                self._cleanup_old_output_files(
                    self._output_dir,
                    self._root_filename,
                    self._number_to_keep
                )
            
            # Step 2: Parse console output
            self.logger.info("Parsing console output...")
            self.logger.debug(f"Console output length: {len(console_output)} characters")
            
            try:
                parsed_values = ConsoleOutputParser.extract_values_from_output(console_output)
                self.logger.info(f"Extracted {len(parsed_values)} values from console output")
            except ValueError as e:
                # Save console output for debugging
                debug_file = f"/tmp/console_output_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(debug_file, 'w') as f:
                    f.write(console_output)
                self.logger.error(f"Failed to parse console output. Full output saved to: {debug_file}")
                raise
            
            # Step 3: Get current sheet state
            # Note: Reading sheet state is safe even in dry-run mode (doesn't modify anything)
            self.logger.info("Reading current Google Sheet state...")
            current_headers = self.sheets_client.get_headers()
            last_row_formulas = self.sheets_client.get_last_row_formulas()
            
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Sheet has {len(current_headers)} columns, {self.sheets_client.get_row_count()} rows")
            else:
                self.logger.info(f"Sheet has {len(current_headers)} columns, {self.sheets_client.get_row_count()} rows")
            
            # Step 4: Build new row
            self.logger.info("Building new row...")
            new_row, new_columns = self._build_new_row(
                parsed_values, 
                current_headers, 
                last_row_formulas
            )
            
            # Step 5: Add new columns if needed
            if new_columns:
                self.logger.info(f"Adding {len(new_columns)} new columns: {new_columns}")
                if not self.dry_run:
                    for col_name in new_columns:
                        col_index = len(current_headers)
                        self.sheets_client.insert_column(col_index, col_name, backfill_value=0)
                        current_headers.append(col_name)
                else:
                    self.logger.info(f"  [DRY RUN] Would add columns: {new_columns}")
            
            # Step 6: Append new row
            self.logger.info(f"Appending new row with {len(new_row)} values")
            if not self.dry_run:
                self.sheets_client.append_row(new_row)
                self.logger.info("✓ Row appended successfully")
            else:
                self.logger.info(f"  [DRY RUN] Would append: {dict(zip(current_headers, new_row))}")
            
            # Step 7: Update charts (if rows or columns were added)
            if not self.dry_run:
                new_row_count = self.sheets_client.get_row_count()
                if new_columns:
                    self.logger.info("Updating chart ranges...")
                    # Note: Chart updates are complex and may need manual adjustment
                    # For now, just log that they might need updating
                    self.logger.info("Note: Charts may need range adjustment in Google Sheets UI")
            
            self.logger.info("="*80)
            self.logger.info("✓ Update complete")
            self.logger.info("="*80)
            return True
            
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            self.logger.exception("Full traceback:")
            return False
    
    def _run_portfolio_analysis(self) -> str:
        """Run the portfolio analysis tool and capture console output.
        
        Returns:
            Console output as string
            
        Raises:
            RuntimeError: If analysis execution fails
        """
        portfolio_config = self.config['portfolio']
        base_dir = os.path.expanduser(portfolio_config['base_dir'])
        
        # Handle new config format with backward compatibility
        if 'output_directory' in portfolio_config and 'root_filename' in portfolio_config:
            # New format: generate dated filename
            output_dir = os.path.expanduser(portfolio_config['output_directory'])
            root_filename = portfolio_config['root_filename']
            number_to_keep = portfolio_config.get('number_to_keep', 7)
            
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate dated filename
            date_str = datetime.now().strftime('%Y_%m_%d')
            output_file = os.path.join(output_dir, f"{root_filename}_{date_str}.numbers")
            
            # Store for cleanup later
            self._output_dir = output_dir
            self._root_filename = root_filename
            self._number_to_keep = number_to_keep
        elif 'temp_output' in portfolio_config:
            # Old format: backward compatibility
            output_file = os.path.expanduser(portfolio_config['temp_output'])
            self.logger.warning(
                "Using deprecated 'temp_output' config. "
                "Please update to use 'output_directory', 'root_filename', and 'number_to_keep'"
            )
            # Extract directory and filename for potential cleanup (best effort)
            output_dir = os.path.dirname(output_file)
            filename = os.path.basename(output_file)
            if '.' in filename:
                root_filename = filename.rsplit('.', 1)[0]
            else:
                root_filename = filename
            self._output_dir = output_dir
            self._root_filename = root_filename
            self._number_to_keep = 7  # Default
        else:
            raise ValueError(
                "Portfolio config must contain either:\n"
                "- 'output_directory', 'root_filename', and optionally 'number_to_keep' (new format), or\n"
                "- 'temp_output' (deprecated format)"
            )
        
        # Build command
        cmd = [
            sys.executable,  # Use same Python as this script
            '-m', 'portfolio',
            '--mode', 'full-history',
            '--base-dir', base_dir,
            '--output-file', output_file
        ]
        
        self.logger.info(f"Running: {' '.join(cmd)}")
        
        # Execute and capture output
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            self.logger.info("Portfolio analysis completed successfully")
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Portfolio analysis failed with exit code {e.returncode}")
            self.logger.error(f"STDOUT: {e.stdout}")
            self.logger.error(f"STDERR: {e.stderr}")
            raise RuntimeError("Portfolio analysis execution failed")
    
    def _build_new_row(self, parsed_values: Dict[str, float], 
                       current_headers: List[str], 
                       last_row_formulas: Dict[str, str]) -> tuple:
        """Build the new row to append, copying formulas/values from row above.
        
        Args:
            parsed_values: Values extracted from console output
            current_headers: Current column headers in sheet
            last_row_formulas: Formulas/values from the last row
            
        Returns:
            Tuple of (new_row_data, new_columns_to_add)
            - new_row_data: List of values matching current_headers order
            - new_columns_to_add: List of new column names to add
        """
        new_row = []
        new_columns = []
        
        # Build case-insensitive mapping from parsed values
        # Map lowercase tag name -> (original tag name, value)
        parsed_values_lower = {tag.lower(): (tag, value) for tag, value in parsed_values.items()}
        
        # Build case-insensitive mapping from headers
        # Map lowercase header -> original header
        headers_lower = {h.lower(): h for h in current_headers}
        
        # Today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        for header in current_headers:
            if header == 'Date':
                new_row.append(today)
            else:
                # Try to find this header in parsed values (case-insensitive)
                header_lower = header.lower()
                if header_lower in parsed_values_lower:
                    # Tag matched - use parsed value
                    original_tag, value = parsed_values_lower[header_lower]
                    new_row.append(value)
                    self.logger.debug(f"Matched '{header}' -> '{original_tag}' = {value}")
                elif header in last_row_formulas:
                    # Not a tag - copy formula/value from above
                    cell_content = last_row_formulas[header]
                    # Convert to string to check if it's a formula
                    cell_str = str(cell_content) if cell_content is not None else ''
                    if cell_str.startswith('='):
                        # It's a formula - increment row numbers
                        new_formula = self._increment_formula_rows(cell_str)
                        new_row.append(new_formula)
                        self.logger.debug(f"Copying formula for '{header}': {cell_str} -> {new_formula}")
                    else:
                        # It's a value - copy as-is (handle empty as 0)
                        value = cell_content if cell_content else 0
                        new_row.append(value)
                        self.logger.debug(f"Copying value for '{header}': {value}")
                else:
                    # Column exists but no previous content - use 0
                    new_row.append(0)
                    self.logger.debug(f"No previous content for '{header}', using 0")
        
        # Check for new tags in output that aren't in sheet yet (case-insensitive)
        for tag, value in parsed_values.items():
            tag_lower = tag.lower()
            if tag_lower not in headers_lower:
                new_columns.append(tag)
                self.logger.info(f"New tag detected: '{tag}' = {value}")
        
        return new_row, new_columns
    
    def _column_index_to_letter(self, index: int) -> str:
        """Convert 0-based column index to Excel-style letter (A, B, ... Z, AA, AB, ...).
        
        Args:
            index: 0-based column index
            
        Returns:
            Column letter(s)
        """
        result = ""
        index += 1  # Convert to 1-based
        while index > 0:
            index -= 1
            result = chr(index % 26 + ord('A')) + result
            index //= 26
        return result
    
    def _increment_formula_rows(self, formula: str, increment: int = 1) -> str:
        """Increment all row numbers in a formula by the specified amount.
        
        Args:
            formula: Formula string (e.g., "=SUM(B2,C2)")
            increment: Amount to increment row numbers by (default: 1)
            
        Returns:
            Formula with incremented row numbers (e.g., "=SUM(B3,C3)")
        """
        import re
        
        def increment_match(match):
            col_letter = match.group(1)
            row_num = int(match.group(2))
            return f"{col_letter}{row_num + increment}"
        
        # Match column letter(s) followed by row number (e.g., A1, AB123)
        return re.sub(r'([A-Z]+)(\d+)', increment_match, formula)
    
    def _send_error_notification(self, error: Exception) -> None:
        """Send error notification email if configured.
        
        Args:
            error: The exception that occurred
        """
        email = self.config.get('notifications', {}).get('email_on_error')
        if not email:
            return
        
        # Simple notification via mail command (requires mail to be configured on Ubuntu)
        subject = f"Portfolio Update Failed: {datetime.now().strftime('%Y-%m-%d')}"
        body = f"Portfolio update failed with error:\n\n{str(error)}\n\nCheck logs for details."
        
        try:
            subprocess.run(
                ['mail', '-s', subject, email],
                input=body.encode(),
                check=False
            )
            self.logger.info(f"Error notification sent to {email}")
        except Exception as e:
            self.logger.warning(f"Could not send email notification: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Update Google Sheets with daily portfolio values'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    
    args = parser.parse_args()
    
    # Run update
    updater = PortfolioUpdater(args.config, dry_run=args.dry_run)
    success = updater.run()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

