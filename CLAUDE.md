# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Investment portfolio analysis tool that processes stock transaction notes (PDF, MHTML, CSV, YAML) to generate reports showing portfolio performance, tax information, and historical analysis.

**Operating modes:**
- `full-history`: Complete investment history with current holdings, P&L, and optional value-over-time CSV
- `periodic-review`: Monthly portfolio review showing performance of stocks bought/retained/sold since last review
- `annual-review`: Year-over-year performance from start date, with optional price-over-time CSV including transaction history
- `tax-report`: Tax year reporting (FYxx format, e.g., FY25 = 6 Apr 2024 to 5 Apr 2025)
- `test`: Regression testing with reference output validation

**Input structure:** `<root>/<category>/<year>/<tag>/<file>`
- Categories: ISA, Taxable, Pension
- Year: YYYY format
- Tag: Optional arbitrary string used for grouping/filtering
- Special handling: Bed-and-ISA transactions (same-day sell + buy) collapsed into single 'transfer' (except in tax-report mode)

**Output formats:** Console (tabulate), Numbers spreadsheet, CSV (value-over-time only)

## Development Commands

**Virtual environment:** Always activate before running commands:
```bash
source .venv/bin/activate
```

**Run modes:**
```bash
# Full history report to console
python3 portfolio.py --mode full-history --base-dir <path>

# Full history with Numbers output and value-over-time CSV
python3 portfolio.py --mode full-history --base-dir <path> --output-file scratch/report --value-over-time 365

# Periodic review
python3 portfolio.py --mode periodic-review --base-dir <path> --start-date 2024-12-01 --end-date 2025-01-01 --eval-date 2025-02-01

# Tax report
python3 portfolio.py --mode tax-report --base-dir <path> --tax-year FY25

# Annual review with price-over-time CSV
python3 portfolio.py --mode annual-review --base-dir <path> --start-date 2025-01-01 --output-file scratch/annual --price-over-time

# Run regression tests
python3 portfolio.py --mode test --base-dir test_data
```

**Filtering options:**
```bash
--include-category ISA,Taxable
--include-tags "phrase1,phrase2"  # Cannot use with --exclude-tags
--exclude-tags "phrase1,phrase2"  # Cannot use with --include-tags
--include-years 2020,2023-2025
```

**Testing:**
- Unit tests run automatically as part of `--mode test`
- Test input data: `test_data/`
- Reference outputs: `test_data/reference_outputs/`
- When developing features, always run test mode and verify diffs before cutting new reference outputs
- **CRITICAL:** Never change test dates or parameters in reference outputs without explicit user permission

**Test data management:**
```bash
# Set up debug directory with specific stocks
python3 manage_test_data.py --phrases "NVDA,Tesla" --action setup-debug

# Add stocks to test_data
python3 manage_test_data.py --phrases "NVDA" --action add-to-test-data
```

**Data locations:**
- Live data: `/Users/cl/Library/Mobile Documents/com~apple~Pages/Documents/Investment/history` (NEVER modify)
- Debug subset: `/Users/cl/Library/Mobile Documents/com~apple~Pages/Documents/Investment/debug`
- Temporary files: `scratch/` directory

## Architecture

Three-layer separation of concerns (strictly enforced):

### 1. PortfolioReview (`portfolio_review.py`)
**Responsibility:** Parse input files → dict of StockNotes

- Parses PDF (various formats), MHTML, CSV, YAML transaction notes
- Extracts: ticker, date, quantity, price, currency, charges, category, tag
- Collapses bed-and-ISA transactions into single 'transfer' (except tax-report mode)
- **No calculations performed here**

**Key parsers:**
- `pdf_parser.py`: Handles multiple broker formats (HL, II, etc.), subdivisions, conversions, mergers
- `mhtml_parser.py`: IBKR transaction HTML
- `csv_parser.py`: II pension CSV format
- `yaml_parser.py`: Manual transactions (stock splits, conversions, etc.)

### 2. PortfolioAnalysis (Modular Architecture)
**Responsibility:** StockNotes → mode-specific Pandas DataFrames

The PortfolioAnalysis has been refactored into a **facade pattern** with specialized modules:

#### Core Facade: `portfolio_analysis.py` (formerly `roi_calculator.py`)
- Provides unified API for portfolio analysis
- Delegates all calculations to specialized modules
- Maintains backward compatibility with existing code
- **No complex logic - pure delegation**

#### Specialized Calculation Modules:

**`financial_metrics.py`** (125 lines)
- Pure financial calculations with generic inputs
- `calculate_mwrr()`: XIRR-based Money-Weighted Rate of Return
- `calculate_roi()`: Simple ROI calculation
- `calculate_highs_and_volatility()`: Recent highs and annualized volatility

**`transaction_processor.py`** (251 lines)
- Transaction data transformation and aggregation
- `transaction_to_cashflow()`: Convert transactions to cashflow tuples
- `build_cashflows()`: Build cashflow series from transactions
- `calculate_mwrr_for_transactions()`: MWRR for transaction list
- `calculate_aggregated_mwrr()`: Aggregated MWRR across groups (tags, categories)
- `calculate_transactions_through_date()`: Comprehensive transaction analysis
- **Cashflow convention:** BUY=negative, SELL=positive, TRANSFER=as-is, STOCK_CONVERSION=zero

**`market_data_fetcher.py`** (496 lines)
- Yahoo Finance API interactions and data cleaning
- `batch_get_stock_prices()`: Fetch prices for multiple tickers, returns GBP values
- `batch_get_ticker_info()`: Get comprehensive ticker information
- `get_current_exchange_rate()`: Live FX rates
- **Data cleaning logic:**
  - Spike detection: >20% rise/fall in single day
  - UK stocks: pence/pounds transition handling
  - Gaps: bank holidays, weekends
  - Price cache: Used for full-history + value-over-time performance

**`holdings_calculator.py`** (267 lines)
- Holdings and valuation calculations at specific dates
- `get_holdings_at_date()`: Calculate units held at target date
- `get_subsequent_stock_splits()`: Track post-date stock splits
- `get_stock_price_from_data()`: Extract price from pre-fetched data
- `get_stock_valuations_at_date()`: Complete valuation with holdings
- `calculate_start_value_from_transactions()`: Initial value for new/sold stocks
- `calculate_retained_stock_performance_unified()`: Retained stock performance

**Mode Processors:**

**`full_history_processor.py`** (437 lines)
- Three-phase full history analysis:
  1. Analyze transactions for each stock
  2. Fetch current prices and exchange rates
  3. Calculate final metrics
- `process_full_history()`: Complete portfolio history with current holdings
- `create_portfolio_summaries()`: Aggregate summaries (whole, by-tag, by-category)
- `calculate_group_summaries()`: Group-level statistics

**`periodic_review_processor.py`** (656 lines)
- Monthly portfolio review analysis
- `process_periodic_review()`: Classify and analyze stocks by period
- `classify_stocks_by_review_period()`: Categorize as new/retained/sold/out-of-scope
- `calculate_periodic_performance()`: Performance metrics for each category
- `create_periodic_review_summary()`: Category-level summary
- `create_tag_summary()`: Tag-level aggregations
- `add_tag_grouping()` / `add_tag_grouping_periodic()`: Tag-based grouping

**`tax_report_processor.py`** (157 lines)
- Tax year reporting for capital gains
- `process_tax_report()`: Generate tax report for specific tax year
- `calculate_tax_pnl()`: P&L calculation using average cost basis
- Processes taxable accounts only, skips bed-and-ISA processing

**`annual_review_processor.py`**
- Year-over-year performance analysis from a start date
- `process_annual_review()`: Main entry point for annual review mode
- `calculate_price_over_time()`: Daily prices with transaction columns for CSV export
- Groups by whole portfolio, category (ISA/Taxable/Pension), and tags
- MWRR calculated using synthetic transactions (start value as BUY, current value as SELL)

**`value_over_time_processor.py`** (177 lines)
- Portfolio valuation over time calculation
- `calculate_value_over_time()`: Daily valuations by category and tag
- Generates time series data for charts/analysis

#### Module Dependencies:
```
financial_metrics (pure functions)
    ↑
transaction_processor ← market_data_fetcher
    ↑                       ↑
holdings_calculator ────────┘
    ↑
mode processors (full_history, periodic_review, tax_report, annual_review, value_over_time)
    ↑
portfolio_analysis (facade)
```

### 3. PortfolioReporter (`portfolio_reporter.py`)
**Responsibility:** DataFrames → output (console/Numbers/CSV)

- Data-driven approach: column definitions, formats, thresholds in `reporter_definitions.py`
- Console: `ConsoleTableWriter` (via `tabulate`)
- Numbers: `NumbersTableWriter` (via `numbers-parser`)
- CSV: `CSVWriter` (value-over-time only)
- Color-coding based on thresholds (red/amber/green)

**Supporting infrastructure:**
- `data_table_builder.py`: Builds tables from DataFrames
- `console_table_writer.py`: Console rendering
- `numbers_table_writer.py`: Numbers spreadsheet generation
- `csv_writer.py`: CSV export

### 4. CLI (`portfolio.py`)
Entry point: parses args → invokes PortfolioReview → PortfolioAnalysis → PortfolioReporter

## File Naming Conventions

- Numbers: User-specified via `--output-file`
- CSV: `{Numbers_root}_value_over_time.csv`
- Logs: `logs/stock_log_YYMMDD_nnn.log` (auto-generated, last 4 kept)

## Debugging

- Debug output goes to log files in `logs/`, **NOT to console**
- Log level controlled via `--log-level DEBUG`
- All temporary scripts/outputs go in `scratch/`

## Git Workflow

- Project maintained under Git
- **Never run git commit/push without explicit, bounded user permission for current session**

**Remotes:**
- `jarvis`: Gitea on jarvis (ssh://git@jarvis:2222/jarvis/investment-reviews.git) — canonical Tier 1
- `github`: GitHub (git@github.com:cloudon7281/investment-reviews.git)

When pushing, push to both remotes:
```bash
git push jarvis main && git push github main
```

## Plans and Documentation

- Plan-specific files (plan, implementation, tests, READMEs) go in `claude_plans/<plan-name>/`
- Keep plans cleanly separated from each other
- Note: `plans/` directory is used by Cursor

## Development Process

The tool will be developed and deployed in my local production environment, as described in ssh://git@jarvis:2222/jarvis/devops-model.git.

You may be invoked from either my local MacBook (hostname 'MacBook') on a local git clone, or on my local MacBook ssh-connected to jarvis working on the canonical dev check out, or on jarvis itself (hostname 'jarvis').  In all environments you should use the installed Gitea CLI tool 'tea' to access Gitea.


