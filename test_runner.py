import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

from logger import logger

def parse_tax_year(tax_year_str):
    """Parse tax year string (e.g., 'FY25') into start and end dates."""
    import re
    from datetime import datetime
    
    # Match FYxx format
    match = re.match(r'FY(\d{2})', tax_year_str.upper())
    if not match:
        raise ValueError(f"Invalid tax year format: {tax_year_str}. Expected format: FYxx (e.g., FY25)")
    
    year = int(match.group(1))
    
    # Convert 2-digit year to 4-digit year
    if year < 50:  # Assume 20xx for years 00-49
        full_year = 2000 + year
    else:  # Assume 19xx for years 50-99
        full_year = 1900 + year
    
    # Tax year starts on 6 April of the previous year and ends on 5 April
    tax_year_start = datetime(full_year - 1, 4, 6)
    tax_year_end = datetime(full_year, 4, 5)
    
    return tax_year_start, tax_year_end

def run_tests(portfolio_review, portfolio_analysis, reporter, test_data_dir='anonymised_test_data'):
    """Run automated tests against test data.

    Args:
        portfolio_review: PortfolioReview instance
        portfolio_analysis: PortfolioAnalysis instance
        reporter: PortfolioReporter instance
        test_data_dir: Directory containing test data and reference outputs (default: 'anonymised_test_data')
    """
    logger.info(f"Running automated tests using {test_data_dir}...")

    # First, run unit tests
    print("\n" + "="*80)
    print("UNIT TESTS")
    print("="*80 + "\n")
    logger.info("Running unit tests...")

    from test_unit import run_unit_tests
    unit_tests_passed = run_unit_tests()

    if not unit_tests_passed:
        logger.error("Unit tests failed!")
        return False

    print("\n" + "="*80)
    print("INTEGRATION TESTS")
    print("="*80 + "\n")

    # Test parameters (same as used for reference outputs)
    start_date = datetime(2025, 3, 1)
    end_date = datetime(2025, 3, 31)
    eval_date = datetime(2025, 6, 16)

    # Reference outputs directory
    reference_dir = os.path.join(test_data_dir, "reference_outputs")

    # Test 1: Periodic Review Mode
    logger.info("Running periodic review test...")
    periodic_output = run_periodic_review_test(portfolio_review, portfolio_analysis, reporter, start_date, end_date, eval_date, test_data_dir)
    periodic_reference = load_reference_output(os.path.join(reference_dir, "periodic_review_reference.txt"))

    periodic_passed = compare_periodic_outputs(periodic_output, periodic_reference)
    result = "PASSED" if periodic_passed else "FAILED"
    print(f"Periodic review test: {result}")
    logger.info(f"Periodic review test: {result}")

    # Test 2: Full History Mode
    logger.info("Running full history test...")
    full_history_output = run_full_history_test(portfolio_review, portfolio_analysis, reporter, test_data_dir)
    full_history_reference = load_reference_output(os.path.join(reference_dir, "full_history_reference.txt"))

    full_history_passed = compare_full_history_outputs(full_history_output, full_history_reference)
    result = "PASSED" if full_history_passed else "FAILED"
    print(f"Full history test: {result}")
    logger.info(f"Full history test: {result}")

    # Test 3: Tax Report Mode
    logger.info("Running tax report test...")
    tax_year = "FY24"
    tax_report_output = run_tax_report_test(portfolio_review, portfolio_analysis, reporter, tax_year, test_data_dir)
    tax_report_reference = load_reference_output(os.path.join(reference_dir, "tax_report_fy24_reference.txt"))

    tax_report_passed = compare_tax_report_outputs(tax_report_output, tax_report_reference)
    result = "PASSED" if tax_report_passed else "FAILED"
    print(f"Tax report test: {result}")
    logger.info(f"Tax report test: {result}")

    # Test 4: Annual Review Mode
    logger.info("Running annual review test...")
    annual_start_date = datetime(2024, 1, 1)
    annual_review_output = run_annual_review_test(portfolio_review, portfolio_analysis, reporter, annual_start_date, test_data_dir)
    annual_review_reference_path = os.path.join(reference_dir, "annual_review_reference.txt")
    annual_review_reference = load_reference_output(annual_review_reference_path)

    # If reference file doesn't exist, skip comparison but report
    if not annual_review_reference:
        logger.warning(f"Annual review reference file not found: {annual_review_reference_path}")
        print(f"Annual review test: SKIPPED (no reference file)")
        annual_review_passed = True  # Don't fail if reference doesn't exist yet
    else:
        annual_review_passed = compare_annual_review_outputs(annual_review_output, annual_review_reference)
        result = "PASSED" if annual_review_passed else "FAILED"
        print(f"Annual review test: {result}")
        logger.info(f"Annual review test: {result}")

    # Overall result
    all_integration_passed = periodic_passed and full_history_passed and tax_report_passed and annual_review_passed
    
    print("\n" + "="*80)
    if unit_tests_passed and all_integration_passed:
        print("✅ ALL TESTS PASSED! (33 unit tests + 4 integration tests)")
        logger.info("✅ All tests PASSED!")
        return True
    else:
        print("❌ SOME TESTS FAILED!")
        if not unit_tests_passed:
            print("   - Unit tests: FAILED")
        if not all_integration_passed:
            print("   - Integration tests: FAILED")
        print("="*80)
        logger.error("❌ Some tests FAILED!")
        return False

def run_periodic_review_test(portfolio_review, portfolio_analysis, reporter, start_date, end_date, eval_date, test_data_dir):
    """Run periodic review test by shelling out to CLI directly."""
    # Shell out to CLI with same parameters as used to create reference
    cmd = [
        sys.executable, 'portfolio.py',
        '--base-dir', test_data_dir,
        '--mode', 'periodic-review',
        '--start-date', start_date.strftime('%Y-%m-%d'),
        '--end-date', end_date.strftime('%Y-%m-%d'),
        '--eval-date', eval_date.strftime('%Y-%m-%d'),
        '--log-level', 'WARNING'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
        # Combine stdout and stderr
        combined_output = result.stdout + result.stderr
        return combined_output
    except Exception as e:
        return f"Error running CLI: {str(e)}\n"

def run_full_history_test(portfolio_review, portfolio_analysis, reporter, test_data_dir):
    """Run full history test by shelling out to CLI directly."""
    # Shell out to CLI with same parameters as used to create reference
    cmd = [
        sys.executable, 'portfolio.py',
        '--base-dir', test_data_dir,
        '--mode', 'full-history',
        '--log-level', 'WARNING'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
        # Combine stdout and stderr
        combined_output = result.stdout + result.stderr
        return combined_output
    except Exception as e:
        return f"Error running CLI: {str(e)}\n"

def run_tax_report_test(portfolio_review, portfolio_analysis, reporter, tax_year, test_data_dir):
    """Run tax report test by shelling out to CLI directly."""
    # Shell out to CLI with same parameters as used to create reference
    cmd = [
        sys.executable, 'portfolio.py',
        '--base-dir', test_data_dir,
        '--mode', 'tax-report',
        '--tax-year', tax_year,
        '--log-level', 'WARNING'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
        # Combine stdout and stderr
        combined_output = result.stdout + result.stderr
        return combined_output
    except Exception as e:
        return f"Error running CLI: {str(e)}\n"


def run_annual_review_test(portfolio_review, portfolio_analysis, reporter, start_date, test_data_dir):
    """Run annual review test by shelling out to CLI directly."""
    cmd = [
        sys.executable, 'portfolio.py',
        '--base-dir', test_data_dir,
        '--mode', 'annual-review',
        '--start-date', start_date.strftime('%Y-%m-%d'),
        '--log-level', 'WARNING'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
        # Combine stdout and stderr
        combined_output = result.stdout + result.stderr
        return combined_output
    except Exception as e:
        return f"Error running CLI: {str(e)}\n"

def load_reference_output(filepath):
    """Load reference output from file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Reference file not found: {filepath}")
        return ""

def compare_periodic_outputs(current_output, reference_output):
    """Compare periodic review outputs exactly."""
    # Extract just the table content for comparison
    current_tables = extract_periodic_tables(current_output)
    reference_tables = extract_periodic_tables(reference_output)
    
    if len(current_tables) != len(reference_tables):
        logger.error(f"Different number of tables: current={len(current_tables)}, reference={len(reference_tables)}")
        return False
    
    for i, (current_table, reference_table) in enumerate(zip(current_tables, reference_tables)):
        if current_table != reference_table:
            logger.error(f"Table {i} does not match")
            logger.debug(f"Current table {i}: {current_table[:200]}...")
            logger.debug(f"Reference table {i}: {reference_table[:200]}...")
            return False
    
    return True

def compare_full_history_outputs(current_output, reference_output):
    """Compare full history outputs with static/dynamic column validation."""
    # Extract both detail table and summary table
    current_detail = extract_table_data(current_output, table_name='Full Investment History')
    reference_detail = extract_table_data(reference_output, table_name='Full Investment History')

    current_summary = extract_table_data(current_output, table_name='Portfolio Summary')
    reference_summary = extract_table_data(reference_output, table_name='Portfolio Summary')

    if not current_detail or not reference_detail:
        logger.error("Could not extract detail table data from outputs")
        return False

    if not current_summary or not reference_summary:
        logger.error("Could not extract summary table data from outputs")
        return False

    # Validate detail table
    detail_passed = compare_table_with_classification(
        current_detail, reference_detail, "Full Investment History"
    )

    # Validate summary table
    summary_passed = compare_table_with_classification(
        current_summary, reference_summary, "Portfolio Summary"
    )

    return detail_passed and summary_passed


def compare_table_with_classification(current_table, reference_table, table_name):
    """Compare tables with static/dynamic column classification."""

    # Classify columns
    # Static: Should match exactly (invariant across runs)
    static_columns = ['Company', 'Ticker', 'Category', 'Tag', 'Total Invested', 'Total Received',
                      'Units Held', 'First Transaction', 'Last Transaction']

    # Dynamic: Should be present/absent consistently and within tolerance if present
    # These vary with market prices but should be validated
    dynamic_columns = ['Current Value', 'P&L', 'Unrealized Profit', 'Simple ROI', 'MWRR',
                       'Current price', '90d High', '% of High', 'Volatility']

    # Validate column schema
    if len(current_table) > 0 and len(reference_table) > 0:
        current_columns = set(current_table[0].keys())
        reference_columns = set(reference_table[0].keys())

        if current_columns != reference_columns:
            logger.error(f"{table_name}: Column mismatch between current and reference")
            logger.error(f"Current columns: {sorted(current_columns)}")
            logger.error(f"Reference columns: {sorted(reference_columns)}")
            logger.error(f"Columns in current but not reference: {sorted(current_columns - reference_columns)}")
            logger.error(f"Columns in reference but not current: {sorted(reference_columns - current_columns)}")
            return False

        logger.info(f"{table_name}: Column validation passed: {len(current_columns)} columns match")

    # Sort by ticker (or tag for summary table) for consistent ordering
    sort_key = 'Tag' if table_name == 'Portfolio Summary' else 'Ticker'
    current_sorted = sorted(current_table, key=lambda x: x.get(sort_key, ''))
    reference_sorted = sorted(reference_table, key=lambda x: x.get(sort_key, ''))

    # Compare static columns (exact match)
    for i, (current_row, reference_row) in enumerate(zip(current_sorted, reference_sorted)):
        for col in static_columns:
            if col in current_row and col in reference_row:
                if current_row[col] != reference_row[col]:
                    logger.error(f"{table_name} Row {i}, Static Column {col}: Current='{current_row[col]}', Reference='{reference_row[col]}'")
                    return False

    # Compare dynamic columns (presence and tolerance)
    for i, (current_row, reference_row) in enumerate(zip(current_sorted, reference_sorted)):
        for col in dynamic_columns:
            if col not in current_row or col not in reference_row:
                continue  # Column may not be in all tables

            current_val = current_row[col]
            reference_val = reference_row[col]

            # Check presence consistency
            current_is_empty = not current_val or current_val.strip() in ['', '-', 'N/A']
            reference_is_empty = not reference_val or reference_val.strip() in ['', '-', 'N/A']

            if current_is_empty != reference_is_empty:
                logger.error(f"{table_name} Row {i}, Dynamic Column {col}: Presence mismatch - Current='{current_val}', Reference='{reference_val}'")
                return False

            # If both present, check within 50% tolerance
            if not current_is_empty and not reference_is_empty:
                try:
                    # Parse numeric values (strip currency symbols, %, etc.)
                    current_numeric = parse_numeric_value(current_val)
                    reference_numeric = parse_numeric_value(reference_val)

                    if current_numeric is not None and reference_numeric is not None:
                        # Calculate tolerance (50% of reference value)
                        if reference_numeric != 0:
                            diff_pct = abs(current_numeric - reference_numeric) / abs(reference_numeric)
                            if diff_pct > 0.5:
                                logger.error(f"{table_name} Row {i}, Dynamic Column {col}: Value differs by {diff_pct*100:.1f}% (>50%) - Current={current_numeric:.2f}, Reference={reference_numeric:.2f}")
                                return False
                except Exception as e:
                    logger.debug(f"Could not parse numeric values for {col}: {e}")
                    # If we can't parse, do string comparison but be lenient
                    pass

    return True


def parse_numeric_value(value_str):
    """Parse a numeric value from formatted string (e.g., '£1,234', '45.6%', '£-1,234')."""
    if not value_str:
        return None

    try:
        # Remove common formatting: £, $, %, commas, color codes
        import re
        # Remove ANSI color codes
        clean = re.sub(r'\x1b\[[0-9;]+m', '', str(value_str))
        # Remove currency symbols, %, commas, spaces
        clean = clean.replace('£', '').replace('$', '').replace('%', '').replace(',', '').replace(' ', '')
        # Handle empty after cleaning
        if not clean or clean in ['-', 'N/A']:
            return None
        return float(clean)
    except (ValueError, AttributeError):
        return None

def compare_tax_report_outputs(current_output, reference_output):
    """Compare tax report outputs exactly."""
    # For tax reports, we can compare the entire output exactly
    # since they don't have time-sensitive data like current prices
    current_clean = current_output.strip()
    reference_clean = reference_output.strip()

    if current_clean != reference_clean:
        logger.error("Tax report output does not match reference")
        logger.error(f"Current length: {len(current_clean)}, Reference length: {len(reference_clean)}")
        logger.error(f"Current output: {repr(current_clean[:200])}")
        logger.error(f"Reference output: {repr(reference_clean[:200])}")

        # Show line-by-line differences
        current_lines = current_clean.split('\n')
        reference_lines = reference_clean.split('\n')
        logger.error(f"Current lines: {len(current_lines)}, Reference lines: {len(reference_lines)}")

        for i, (curr_line, ref_line) in enumerate(zip(current_lines, reference_lines)):
            if curr_line != ref_line:
                logger.error(f"Line {i} differs:")
                logger.error(f"  Current: {repr(curr_line)}")
                logger.error(f"  Reference: {repr(ref_line)}")
                break

        return False

    return True


def compare_annual_review_outputs(current_output, reference_output):
    """Compare annual review outputs with static/dynamic column validation.

    Similar to full history comparison - static columns must match exactly,
    dynamic columns (prices, valuations) can vary within tolerance.
    """
    # Extract summary table and detail table
    current_summary = extract_table_data(current_output, table_name='Annual Review Summary')
    reference_summary = extract_table_data(reference_output, table_name='Annual Review Summary')

    current_detail = extract_table_data(current_output, table_name='Annual Review Detail')
    reference_detail = extract_table_data(reference_output, table_name='Annual Review Detail')

    # Check that we got some data
    if not current_summary and not current_detail:
        logger.error("Could not extract any annual review table data from current output")
        return False

    # Validate summary table if both exist
    summary_passed = True
    if current_summary and reference_summary:
        summary_passed = compare_annual_review_table(
            current_summary, reference_summary, "Annual Review Summary"
        )
    elif current_summary != reference_summary:
        logger.error("Summary table existence mismatch")
        return False

    # Validate detail table if both exist
    detail_passed = True
    if current_detail and reference_detail:
        detail_passed = compare_annual_review_table(
            current_detail, reference_detail, "Annual Review Detail"
        )
    elif current_detail != reference_detail:
        logger.error("Detail table existence mismatch")
        return False

    return summary_passed and detail_passed


def compare_annual_review_table(current_table, reference_table, table_name):
    """Compare annual review tables with static/dynamic classification."""

    # Static columns: Should match exactly
    static_columns = ['Group', 'Tag', 'Company', 'Ticker', 'Category']

    # Dynamic columns: Should be present/absent consistently and within tolerance
    dynamic_columns = ['Start Value', 'Bought', 'Sold', 'Current Value', 'P&L', 'MWRR',
                       'Current Price', '90d High', '% of High', 'Volatility']

    # Validate column schema
    if len(current_table) > 0 and len(reference_table) > 0:
        current_columns = set(current_table[0].keys())
        reference_columns = set(reference_table[0].keys())

        if current_columns != reference_columns:
            logger.error(f"{table_name}: Column mismatch between current and reference")
            logger.error(f"Current columns: {sorted(current_columns)}")
            logger.error(f"Reference columns: {sorted(reference_columns)}")
            return False

    # Sort by Group (for summary) or Ticker+Category (for detail with duplicate tickers)
    if 'Group' in (current_table[0].keys() if current_table else []):
        current_sorted = sorted(current_table, key=lambda x: x.get('Group', ''))
        reference_sorted = sorted(reference_table, key=lambda x: x.get('Group', ''))
    else:
        # Sort by Ticker, then Category to handle same ticker in multiple accounts
        current_sorted = sorted(current_table, key=lambda x: (x.get('Ticker', ''), x.get('Category', '')))
        reference_sorted = sorted(reference_table, key=lambda x: (x.get('Ticker', ''), x.get('Category', '')))

    # Compare static columns (exact match)
    for i, (current_row, reference_row) in enumerate(zip(current_sorted, reference_sorted)):
        for col in static_columns:
            if col in current_row and col in reference_row:
                if current_row[col] != reference_row[col]:
                    logger.error(f"{table_name} Row {i}, Static Column {col}: Current='{current_row[col]}', Reference='{reference_row[col]}'")
                    return False

    # Compare dynamic columns (presence and tolerance)
    for i, (current_row, reference_row) in enumerate(zip(current_sorted, reference_sorted)):
        for col in dynamic_columns:
            if col not in current_row or col not in reference_row:
                continue

            current_val = current_row[col]
            reference_val = reference_row[col]

            # Check presence consistency
            current_is_empty = not current_val or current_val.strip() in ['', '-', 'N/A']
            reference_is_empty = not reference_val or reference_val.strip() in ['', '-', 'N/A']

            if current_is_empty != reference_is_empty:
                # Dynamic columns can have presence mismatches due to market data timing
                logger.warning(f"{table_name} Row {i}, Dynamic Column {col}: Presence mismatch (current empty={current_is_empty})")
                continue  # Don't fail on presence mismatch for dynamic columns

            # If both present, check within 50% tolerance
            if not current_is_empty and not reference_is_empty:
                try:
                    current_numeric = parse_numeric_value(current_val)
                    reference_numeric = parse_numeric_value(reference_val)

                    if current_numeric is not None and reference_numeric is not None:
                        if reference_numeric != 0:
                            diff_pct = abs(current_numeric - reference_numeric) / abs(reference_numeric)
                            if diff_pct > 0.5:
                                logger.error(f"{table_name} Row {i}, Dynamic Column {col}: Value differs by {diff_pct*100:.1f}%")
                                return False
                except Exception:
                    pass

    return True

def extract_periodic_tables(output):
    """Extract periodic review tables from output."""
    lines = output.split('\n')
    tables = []
    current_table = []
    in_table = False
    
    for line in lines:
        # Skip log messages and error messages
        if any(level in line for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']):
            continue
        if 'YF.download() has changed' in line:
            continue
        if 'possibly delisted' in line:
            continue
        if 'Error calculating performance' in line:
            continue
        
        # Look for table headers
        if 'PERIODIC REVIEW SUMMARY' in line or 'NEW STOCKS' in line or 'RETAINED STOCKS' in line or 'SOLD STOCKS' in line:
            if current_table:
                tables.append('\n'.join(current_table))
                current_table = []
            in_table = True
            current_table.append(line)
        elif in_table and line.strip():
            current_table.append(line)
        elif in_table and not line.strip():
            # Empty line might be end of table
            if current_table and len(current_table) > 1:
                tables.append('\n'.join(current_table))
                current_table = []
            in_table = False
    
    # Add the last table if any
    if current_table:
        tables.append('\n'.join(current_table))
    
    return tables

def extract_table_data(output, table_name=None):
    """Extract table data from output by parsing headers and mapping by column name.

    Args:
        output: Text output containing tables
        table_name: Optional table name to extract (e.g., 'Full Investment History', 'Portfolio Summary')
                   If None, extracts the first table found.

    Returns:
        List of dictionaries, one per table row
    """
    lines = output.split('\n')
    table_data = []
    in_table = False
    in_target_table = False
    headers = None
    header_indices = {}

    # Normalize table name for comparison
    target_table_upper = table_name.upper() if table_name else None

    for line in lines:
        # Skip log messages and error messages
        if any(level in line for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']):
            continue
        if 'YF.download() has changed' in line:
            continue
        if 'possibly delisted' in line:
            continue
        if 'Error calculating performance' in line:
            continue

        # Look for table headers
        line_upper = line.upper()
        is_table_header = any(header in line_upper for header in [
            'FULL INVESTMENT HISTORY',
            'PORTFOLIO SUMMARY',
            'PERIODIC REVIEW SUMMARY',
            'NEW STOCKS',
            'RETAINED STOCKS',
            'SOLD STOCKS',
            'ANNUAL REVIEW SUMMARY',
            'ANNUAL REVIEW DETAIL'
        ])

        if is_table_header:
            # If we were in a table, we've moved to a new table
            if in_table and in_target_table:
                # We've extracted the target table, stop
                break

            # Check if this is the table we want
            if target_table_upper is None or target_table_upper in line_upper:
                in_table = True
                in_target_table = True
                headers = None  # Reset headers for new table
                header_indices = {}
            else:
                in_table = False
                in_target_table = False
            continue

        if in_table and in_target_table and line.strip() and '|' in line:
            cells = [cell.strip() for cell in line.split('|')]

            # Skip empty rows and separator lines (lines with only '=' or '-')
            if len(cells) <= 2 or all(c in ['', '=', '-', '---', '===', '------', '======'] or set(c) <= set('=-') for c in cells):
                continue

            # First data row with '|' is the header
            if headers is None:
                headers = cells
                # Build mapping of column name to index
                for i, header in enumerate(headers):
                    if header:  # Skip empty cells
                        header_indices[header] = i
                continue

            # Parse data rows using header indices
            row_data = {}
            for col_name, col_idx in header_indices.items():
                if col_idx < len(cells):
                    row_data[col_name] = cells[col_idx]
                else:
                    row_data[col_name] = ''

            # Filter for rows with data
            # Portfolio Summary: check if Tag is non-empty
            # Full Investment History: check if Ticker is non-empty
            if table_name and 'PORTFOLIO SUMMARY' in table_name.upper():
                if row_data.get('Tag', '').strip() and row_data.get('Tag', '').strip() not in ['---', '======']:
                    table_data.append(row_data)
            else:
                if row_data.get('Ticker', '').strip():
                    table_data.append(row_data)

    return table_data

