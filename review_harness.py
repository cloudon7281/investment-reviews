from datetime import datetime

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

def strip_log_lines(output):
    """Remove log records from captured output, leaving only the report itself.

    The run_* helpers capture stdout and stderr together, so log records land in the
    middle of the report.  Comparing them as report content made two tests fail every
    time the code gained a warning (investment-reviews#29).
    """
    return '\n'.join(
        line for line in output.split('\n')
        if not any(level in line for level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
    ).strip()


def check_review_run(output, mode_name, required_tables):
    """Check a price-dependent review by its invariants, not against a stored snapshot.

    Reference outputs cannot work for these modes: their values come from live market
    prices on the day the reference was captured, so the comparison goes stale and
    fails spuriously, or is loosened until it cannot fail (investment-reviews#29).

    Two things are asserted instead.  The run must report no invariant violation — the
    review itself checks those, see review_invariants.py — and every table it should
    have produced must be present with at least one row.  The second half matters as
    much as the first: without it a run that collapsed and printed nothing would report
    no violations and pass, which is how the periodic test came to pass vacuously.

    Args:
        output: Combined stdout and stderr from the CLI run
        mode_name: Mode name, for logging
        required_tables: Table titles that must be present and non-empty

    Returns:
        True if the run is sound
    """
    passed = True

    violations = [line for line in output.split('\n') if 'INVARIANT VIOLATION' in line]
    for violation in violations:
        logger.error(f"{mode_name}: {violation.strip()}")
    if violations:
        passed = False

    for table in required_tables:
        rows = extract_table_data(output, table_name=table)
        if not rows:
            logger.error(f"{mode_name}: table '{table}' is missing or empty")
            passed = False
        else:
            logger.info(f"{mode_name}: '{table}' produced {len(rows)} row(s)")

    return passed


def compare_tax_report_outputs(current_output, reference_output):
    """Compare tax report outputs exactly.

    Tax reports are computed from parsed broker notes with no live market data, so the
    output is deterministic and an exact comparison is the right gate.  Log records are
    stripped first: they are captured alongside the report but are not part of it.
    """
    current_clean = strip_log_lines(current_output)
    reference_clean = strip_log_lines(reference_output)

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


def compare_list_trades_outputs(current_output, reference_output):
    """Compare list trades outputs exactly.

    All data is from parsed broker notes — no live market data — so the output
    is fully deterministic and can be compared as a plain string.  Log records are
    stripped first: they are captured alongside the report but are not part of it.
    """
    current_clean = strip_log_lines(current_output)
    reference_clean = strip_log_lines(reference_output)

    if current_clean != reference_clean:
        logger.error("List trades output does not match reference")
        logger.error(f"Current length: {len(current_clean)}, Reference length: {len(reference_clean)}")

        current_lines = current_clean.split('\n')
        reference_lines = reference_clean.split('\n')
        logger.error(f"Current lines: {len(current_lines)}, Reference lines: {len(reference_lines)}")

        for i, (curr_line, ref_line) in enumerate(zip(current_lines, reference_lines)):
            if curr_line != ref_line:
                logger.error(f"Line {i} differs:")
                logger.error(f"  Current:   {repr(curr_line)}")
                logger.error(f"  Reference: {repr(ref_line)}")
                break

        return False

    return True


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

            # Keep any row that carries data.  This used to require a non-empty 'Ticker'
            # for every table but Portfolio Summary, so the summary tables — keyed on
            # Category or Group, with no Ticker column — silently yielded no rows at all
            # (investment-reviews#29).  Separator rows are already dropped above.
            if any(value.strip() for value in row_data.values()):
                table_data.append(row_data)

    return table_data

