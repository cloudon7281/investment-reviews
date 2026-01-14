# Investment Portfolio Analyzer

A command-line tool for analyzing investment portfolios across multiple brokers, generating tax reports, and tracking performance over time.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

This tool processes stock transaction notes from various UK brokers (Hargreaves Lansdown, Interactive Investor, Interactive Brokers) to provide comprehensive portfolio analysis for personal use by investors. Key features include:

- **Complete investment history** with current holdings and performance metrics
- **Periodic portfolio reviews** - performance snapshots since a given date comparing new purchases, retained holdings, and disposals
- **Annual portfolio reviews** - year-over-year performance analysis with optional price history CSV
- **Tax year capital gains reporting** - aligned to UK tax years (6 April to 5 April)
- **Multi-currency support** with automatic GBP conversion
- **Multiple export formats** - console output, Apple Numbers spreadsheets, CSV, Google Sheets
- **Comprehensive test suite** with anonymized test data

## Features

### Portfolio Analysis Modes

**Full History Mode**
- Complete transaction history across all accounts
- Current holdings with valuations
- Realized and unrealized profit/loss
- ROI and Money-Weighted Rate of Return (MWRR) calculations
- Optional value-over-time CSV for charts

**Periodic Review Mode**
- Performance analysis since given date range
- Stocks categorized as: new purchases (stocks bought within date range), retained holdings (stocks already owned before date range), sold positions (stocks completely sold during date range)
- Performance metrics for each category
- Tag-based grouping for thematic investing

**Tax Report Mode**
- Capital gains calculations for UK tax years
- Average cost basis methodology
- Detailed transaction breakdown for HMRC reporting

**Annual Review Mode**
- Year-over-year performance analysis from a specified start date
- Grouping by whole portfolio, account category (ISA/Taxable/Pension), and tags
- Metrics: start value, bought/sold since, current value, P&L, MWRR
- Optional price-over-time CSV with daily prices for all stocks held during period
- Transaction history alongside prices (BOUGHT/SOLD/SPLIT/CONVERTED) for counterfactual analysis

**Test Mode**
- Automated regression testing
- Validates against reference outputs
- Includes 33 unit tests + 4 integration tests

### Broker Support

- **Hargreaves Lansdown (HL)** - PDF contract notes
- **Interactive Investor (II)** - PDF contract notes and CSV exports
- **Interactive Brokers (IBKR)** - MHTML transaction exports
- **Manual transactions** - YAML format for corporate actions, stock splits, conversions

### Export Options

- **Console** - Colored tables with formatted output
- **Apple Numbers** - Spreadsheet with multiple tabs
- **CSV** - Value-over-time data for charting
- **Google Sheets** - Direct upload to Google Drive

## Quick Start

### Prerequisites

- Python 3.9 or higher
- pip for package management

### Installation

1. Clone the repository:
```bash
git clone https://github.com/[username]/investment-reviews.git
cd investment-reviews
```

2. Create and activate virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### First Run

Run tests with anonymized data to verify installation:
```bash
python3 portfolio.py --mode test
```

Expected output: All 37 tests passing (33 unit + 4 integration tests).

**Note:** Some tests may fail due to market price volatility exceeding the 50% tolerance threshold. This is expected behavior with live market data.

## Usage

### Basic Usage

The tool reads transaction files from a directory structure:
```
base_dir/
  ├── ISA/
  │   └── YYYY/
  │       └── [tag]/
  │           └── transaction_files
  ├── Taxable/
  └── Pension/
```

### Full History Report

View complete portfolio history:
```bash
python3 portfolio.py --mode full-history --base-dir ~/path/to/transaction/data
```

Export to Numbers spreadsheet:
```bash
python3 portfolio.py --mode full-history --base-dir ~/path/to/data --output-file ~/Documents/portfolio_report
```

Generate value-over-time CSV (last 365 days):
```bash
python3 portfolio.py --mode full-history --base-dir ~/path/to/data \
  --output-file ~/Documents/portfolio_report --value-over-time 365
```

### Periodic Review

Monthly performance review:
```bash
python3 portfolio.py --mode periodic-review \
  --base-dir ~/path/to/data \
  --start-date 2024-12-01 \
  --end-date 2025-01-01 \
  --eval-date 2025-02-01
```

**Parameters:**
- `--start-date`: Beginning of review period
- `--end-date`: End of review period
- `--eval-date`: Date for portfolio valuation (default: today)

### Tax Report

Generate capital gains report for UK tax year:
```bash
python3 portfolio.py --mode tax-report --base-dir ~/path/to/data --tax-year FY25
```

Tax years use format `FYxx` where FY25 = 6 April 2024 to 5 April 2025.

### Annual Review

Year-over-year performance analysis:
```bash
python3 portfolio.py --mode annual-review --base-dir ~/path/to/data --start-date 2025-01-01
```

Export to Numbers spreadsheet with price history CSV:
```bash
python3 portfolio.py --mode annual-review --base-dir ~/path/to/data \
  --start-date 2025-01-01 --output-file ~/Documents/annual_review --price-over-time
```

**Parameters:**
- `--start-date`: Beginning of review period (required)
- `--price-over-time`: Generate CSV with daily stock prices and transaction history

The price-over-time CSV includes:
- Daily closing prices (in GBP) for all stocks held at any point during the period
- Transaction columns showing BOUGHT/SOLD quantities, stock splits, and conversions
- Useful for counterfactual analysis ("what if I hadn't sold?")

### Filtering Options

Filter by account category:
```bash
--include-category ISA,Taxable
```

Filter by tags (thematic investing):
```bash
--include-tags "AI,Defense"
# or exclude:
--exclude-tags "Commodities"
```

Filter by year range:
```bash
--include-years 2020,2023-2025
```

### Test Mode

Run tests with default anonymized data:
```bash
python3 portfolio.py --mode test
```

Run tests with custom test data:
```bash
python3 portfolio.py --mode test --test-data ~/path/to/test/data
```

### Google Sheets Integration

**Setup:**
1. Copy `config.yaml.template` to `config.yaml`
2. Add Google Sheets credentials (see Google Sheets API documentation)
3. Configure spreadsheet ID in config.yaml

**Upload to Google Sheets:**
```bash
python3 update_google_sheet.py
```

## Architecture

The tool follows a three-layer architecture with strict separation of concerns:

### Layer 1: Portfolio Review (`portfolio_review.py`)
**Responsibility:** Parse input files → dict of StockNotes

- Parses PDF, MHTML, CSV, YAML transaction notes
- Extracts: ticker, date, quantity, price, currency, charges, category, tag
- Collapses bed-and-ISA transactions into single 'transfer'
- **No calculations performed at this layer**

**Key parsers:**
- `pdf_parser.py` - Multiple broker formats, subdivisions, conversions, mergers
- `mhtml_parser.py` - IBKR transaction HTML
- `csv_parser.py` - II pension CSV format
- `yaml_parser.py` - Manual transactions (corporate actions, splits)

### Layer 2: Portfolio Analysis (Modular Architecture)
**Responsibility:** StockNotes → mode-specific Pandas DataFrames

Organized as a **facade pattern** with specialized modules:

**Core facade:** `portfolio_analysis.py`
- Unified API for portfolio analysis
- Delegates to specialized modules

**Calculation modules:**
- `financial_metrics.py` - Pure financial calculations (MWRR, ROI, volatility)
- `transaction_processor.py` - Transaction aggregation and cashflow building
- `market_data_fetcher.py` - Yahoo Finance API integration, including data cleaning to deal with missing data, spikes, pence<->pound changes mid-stream etc.
- `holdings_calculator.py` - Holdings and valuations at specific dates

**Mode processors:**
- `full_history_processor.py` - Complete portfolio history analysis
- `periodic_review_processor.py` - Monthly review classification and metrics
- `tax_report_processor.py` - Capital gains calculations
- `annual_review_processor.py` - Year-over-year performance analysis
- `value_over_time_processor.py` - Time series valuation data

### Layer 3: Portfolio Reporter (`portfolio_reporter.py`)
**Responsibility:** DataFrames → output (console/Numbers/CSV)

- Data-driven approach with column definitions in `reporter_definitions.py`
- `ConsoleTableWriter` - Colored console tables via `tabulate`
- `NumbersTableWriter` - Apple Numbers spreadsheets via `numbers-parser`
- `CSVWriter` - CSV export for value-over-time data
- Color-coding based on configurable thresholds (red/amber/green)

**Data flow:**
```
Transaction Files
    ↓
[PortfolioReview] Parse files → StockNotes
    ↓
[PortfolioAnalysis] Calculate metrics → DataFrames
    ↓
[PortfolioReporter] Format output → Console/Numbers/CSV/Sheets
```

## Test Data

The repository includes anonymized test data in `anonymised_test_data/`:

- **62 test files** covering various scenarios
- **PII removed** - names, addresses, client references anonymized
- **Quantities randomized** - but consistent per ticker
- **Zero holdings preserved** - for testing edge cases
- **Prices and dates unchanged** - for accurate testing

Test data structure matches production format with three categories:
- `ISA/` - Individual Savings Account transactions
- `Taxable/` - General investment account transactions
- `Pension/` - Pension fund transactions

Each category contains yearly subdirectories with optional tags for thematic grouping.

### Managing Test Data

The `manage_test_data.py` tool helps create isolated test environments and add anonymized test data.

**Debug Mode - Set up isolated debugging environment:**

Extract specific stocks to a debug directory for testing:
```bash
# Single stock
python3 manage_test_data.py --debug NVDA

# Multiple stocks (comma-separated)
python3 manage_test_data.py --debug NVDA,PLTR,MSFT

# Dry run (preview without copying)
python3 manage_test_data.py --debug RGTI --dry-run
```

This copies matching transaction files to the debug directory, allowing you to test against a subset of your portfolio.

**Test Mode - Add anonymized data to test suite:**

Validate and add new anonymized test data:
```bash
# Add stock to anonymised_test_data
python3 manage_test_data.py --test AAPL

# Skip confirmation prompts
python3 manage_test_data.py --test TSLA --yes

# Dry run to preview
python3 manage_test_data.py --test GOOG --dry-run
```

**How test mode works:**
1. **Phase 1:** Finds matching transaction files in your raw data
2. **Validation:** Generates anonymized versions and validates they produce equivalent outputs
3. **Phase 2:** Copies anonymized files to `anonymised_test_data/`
4. **Testing:** Runs full test suite with new data
5. **Confirmation:** Asks to keep changes (unless `--yes` flag used)

This ensures new test data is properly anonymized and doesn't break existing tests.

**Note:** The `--test` mode requires access to raw (non-anonymized) transaction data for validation.

## Development Philosophy

This project is an **experiment in AI-assisted development** ("vibe coding"):

- Primary development tool: [Claude Code](https://claude.ai/code) by Anthropic
- Iterative refinement through natural language specifications
- AI-assisted code generation, refactoring, and testing
- Human oversight for architecture, requirements, and quality assurance

The architecture demonstrates how AI can help maintain clean separation of concerns and comprehensive test coverage across a complex financial analysis tool.

## Configuration

### Manual Transactions

For corporate actions not captured in broker notes (stock splits, conversions, mergers):

1. Copy `manual_transaction.yaml.template`
2. Fill in transaction details
3. Place in appropriate directory: `[category]/[year]/[tag]/`

### Google Sheets (Optional)

1. Set up Google Cloud project with Sheets API enabled
2. Download service account credentials
3. Configure in `config.yaml` (copy from `config.yaml.template`)

## Contributing

This is a personal tool, but issues and suggestions are welcome:

1. Check existing issues before creating new ones
2. For bugs, include: Python version, transaction file format, error output
3. For features, describe use case and expected behavior

## License

MIT License - see LICENSE file for details.

## Disclaimer

**This tool is for personal use only and is not financial advice.**

- No warranty or guarantee of accuracy
- User responsible for verifying all calculations
- Tax calculations should be reviewed by qualified professionals
- Not suitable for commercial or professional investment management
- Users assume all risk from use of this software

Always verify portfolio values and tax calculations against official broker statements and consult with qualified financial advisors for investment decisions.

## Acknowledgments

- **Yahoo Finance** - Market data via `yfinance` library
- **Anthropic Claude** - AI-assisted development and architecture design
- **numbers-parser** - Apple Numbers file format support
- **tabulate** - Console table formatting

---

**Built with AI assistance using [Claude Code](https://claude.ai/code)**
