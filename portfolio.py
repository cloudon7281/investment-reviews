#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
from logger import setup_logger, logger
from portfolio_analysis import PortfolioAnalysis
from portfolio_reporter import PortfolioReporter
from portfolio_review import PortfolioReview
from test_runner import run_tests
import pandas as pd

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Process stock portfolio data.',
        # Exit with error if unknown arguments are provided
        allow_abbrev=False
    )
    parser.add_argument('--log-level', default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Set the logging level')
    parser.add_argument('--base-dir', default='stocks',
                      help='Base directory containing stock notes')
    parser.add_argument('--output-file', default=None,
                      help='Output filename for the Numbers report (if not specified, console output only)')
    parser.add_argument('--mode', default='full-history',
                      choices=['full-history', 'periodic-review', 'test', 'tax-report', 'annual-review'],
                      help='Processing mode: full-history (complete investment history), periodic-review (performance analysis for a specific period), annual-review (annual portfolio performance review), test (run automated tests), or tax-report (tax reporting for a specific tax year)')
    parser.add_argument('-s', '--show-summary', action='store_true',
                      help='Show portfolio summary')
    parser.add_argument('-d', '--show-details', action='store_true',
                      help='Show detailed stock information')
    
    # Periodic review specific arguments
    parser.add_argument('--start-date', type=str,
                      help='Start date for periodic review (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                      help='End date for periodic review (YYYY-MM-DD format)')
    parser.add_argument('--eval-date', type=str,
                      help='Evaluation date for periodic review (YYYY-MM-DD format, defaults to today)')
    
    # Tax reporting specific arguments
    parser.add_argument('--tax-year', type=str,
                      help='Tax year for tax reporting (FYxx format, e.g., FY25 for tax year ending 5 April 2025)')
    
    # Value over time specific arguments
    parser.add_argument('--value-over-time', type=int, metavar='N',
                      help='Generate CSV showing portfolio value over the past N days (full-history mode only, requires --output-file)')

    # Price over time specific arguments (annual-review mode)
    parser.add_argument('--price-over-time', action='store_true',
                      help='Generate CSV showing individual stock prices since start date (annual-review mode only, requires --output-file)')

    # Test mode specific arguments
    parser.add_argument('--test-data', type=str,
                      default='anonymised_test_data',
                      help='Directory containing test data and reference outputs (test mode only). Default: anonymised_test_data')

    # Filtering arguments (apply to full-history and periodic-review modes only)
    parser.add_argument('--include-category', type=str,
                      help='Comma-separated list of categories to include (ISA,Taxable,Pension)')
    parser.add_argument('--include-tags', type=str,
                      help='Comma-separated list of tag phrases to include (cannot use with --exclude-tags)')
    parser.add_argument('--exclude-tags', type=str,
                      help='Comma-separated list of tag phrases to exclude (cannot use with --include-tags)')
    parser.add_argument('--include-years', type=str,
                      help='Comma-separated list of years or ranges to include (e.g., 2010,2023-2025)')
    
    return parser.parse_args()

def parse_year_ranges(year_str):
    """Parse year ranges like '2010,2023-2025' into list of years.
    
    Args:
        year_str: Comma-separated list of years or ranges
        
    Returns:
        List of individual years
    """
    years = []
    for part in year_str.split(','):
        part = part.strip()
        if '-' in part:
            # Range like "2023-2025"
            start, end = part.split('-')
            years.extend(range(int(start), int(end) + 1))
        else:
            # Single year
            years.append(int(part))
    return sorted(set(years))

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

def main():
    """Main entry point for the CLI."""
    args = parse_args()
    
    # Initialize logging
    setup_logger(args.log_level)
    
    # Validate filter arguments
    if args.include_tags and args.exclude_tags:
        logger.error("Cannot specify both --include-tags and --exclude-tags")
        sys.exit(1)
    
    try:
        # In test mode, use the --test-data directory; otherwise use --base-dir
        base_dir = args.base_dir
        if args.mode == 'test':
            base_dir = args.test_data
            if not Path(base_dir).exists():
                logger.error(f"Test data directory not found: {base_dir}")
                sys.exit(1)

        # Parse filter arguments
        include_categories = None
        if args.include_category:
            include_categories = [c.strip().lower() for c in args.include_category.split(',')]

        # Tax-report mode implicitly filters to Taxable category only
        if args.mode == 'tax-report':
            include_categories = ['taxable']

        include_tags = None
        if args.include_tags:
            include_tags = [t.strip() for t in args.include_tags.split(',')]

        exclude_tags = None
        if args.exclude_tags:
            exclude_tags = [t.strip() for t in args.exclude_tags.split(',')]

        include_years = None
        if args.include_years:
            include_years = parse_year_ranges(args.include_years)

        # Initialize portfolio review and scan directory
        portfolio_review = PortfolioReview(
            base_dir,
            args.mode,
            include_categories=include_categories,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            include_years=include_years
        )
        
        # Initialize portfolio analysis and reporter
        portfolio_analysis = PortfolioAnalysis()
        reporter = PortfolioReporter(numbers_filename=args.output_file)
        
        if args.mode == 'full-history':
            # Validate value-over-time parameter
            if args.value_over_time is not None:
                if not args.output_file:
                    logger.error("--value-over-time requires --output-file to be specified")
                    sys.exit(1)
                if args.value_over_time < 1:
                    logger.error("--value-over-time must be a positive number")
                    sys.exit(1)
            
            # Full-history mode: Direct processing
            # Pass value_over_time parameter so prices are fetched once and value-over-time is calculated
            full_history_results = portfolio_analysis.process_full_history(
                portfolio_review,
                value_over_time_days=args.value_over_time
            )
            reporter.display_full_history(full_history_results)

            # Write value-over-time CSV if it was calculated
            if full_history_results.get('value_over_time') is not None:
                reporter.write_value_over_time_csv(
                    full_history_results['value_over_time'],
                    args.value_over_time
                )
        elif args.mode == 'test':
            # Test mode: Run automated tests
            # base_dir was already set above based on --test-data flag
            run_tests(portfolio_review, portfolio_analysis, reporter, base_dir)
        elif args.mode == 'tax-report':
            # Tax reporting mode: Generate tax report for specific tax year
            if not args.tax_year:
                logger.error("Tax reporting mode requires --tax-year argument (e.g., --tax-year FY25)")
                sys.exit(1)
            
            # Parse tax year
            from datetime import datetime
            tax_year_start, tax_year_end = parse_tax_year(args.tax_year)
            
            # Process tax report
            tax_report_results = portfolio_analysis.process_tax_report(portfolio_review, tax_year_start, tax_year_end)
            reporter.display_tax_report(tax_report_results, args.tax_year)
        elif args.mode == 'annual-review':
            # Annual review mode: Performance analysis from start date to today
            if not args.start_date:
                logger.error("Annual review mode requires --start-date argument")
                sys.exit(1)

            # Validate price-over-time parameter
            if args.price_over_time and not args.output_file:
                logger.error("--price-over-time requires --output-file to be specified")
                sys.exit(1)

            # Parse start date
            from datetime import datetime
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

            # Process annual review
            annual_results = portfolio_analysis.process_annual_review(
                portfolio_review, start_date, price_over_time=args.price_over_time
            )
            reporter.display_annual_review(annual_results, start_date)

            # Write price-over-time CSV if requested
            if args.price_over_time and annual_results.get('price_over_time') is not None:
                reporter.write_price_over_time_csv(annual_results['price_over_time'], start_date)
        else:  # periodic-review
            # Periodic review mode: Performance analysis for specific period
            if not args.start_date or not args.end_date:
                logger.error("Periodic review mode requires --start-date and --end-date arguments")
                sys.exit(1)

            # Parse dates
            from datetime import datetime
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
            eval_date = None
            if args.eval_date:
                eval_date = datetime.strptime(args.eval_date, '%Y-%m-%d')

            # Process periodic review
            periodic_results = portfolio_analysis.process_periodic_review(portfolio_review, start_date, end_date, eval_date)
            reporter.display_periodic_review(periodic_results, start_date, end_date, eval_date)
        
    except Exception as e:
        logger.error(f"Error processing portfolio: {str(e)}")
        logger.exception("Full traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main() 