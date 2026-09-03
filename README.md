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
- Progress towards the next doubling and count of completed profit-takings
- Daily price change for held stocks
- Recent highs and the current price against each of them (see below)
- Optional value-over-time CSV for charts

**Periodic Review Mode**
- Performance analysis since given date range
- Stocks categorized as: new purchases (stocks bought within date range), retained holdings (stocks already owned before date range), sold positions (stocks completely sold during date range)
- Performance metrics for each category
- Tag-based grouping for thematic investing
- Recent highs and the current price against each of them (see below)
- Optional thesis candidate analysis: how the wider candidate universe for each investment thesis performed, and how the candidates actually held compare with it

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
- Deterministic modes (tax report, list trades) are compared against reference outputs
- Price-dependent modes are checked against invariants rather than a stored snapshot
- Runs every unit test in `test_unit.py` plus 5 integration tests

### Recent Highs

Full history and periodic review report three recent highs per stock, each measured over
the same window: the 90 calendar days ending at the evaluation date.

| Column | Meaning |
|--------|---------|
| `90d High` | Highest close in the window |
| `10d Smoothed High` | Highest 10-trading-day rolling average close in the window |
| `P90 High` | 90th percentile of the closes in the window |

Each is followed by the current price as a percentage of it (`% of High`,
`% of Smoothed High`, `% of P90 High`), colour-coded against the stop-loss thresholds.

`90d High` is set by a single day's close, so one brief spike can drag the stop-loss
percentage down and trigger a divestment review that the underlying trend does not
justify. The smoothed and percentile highs discount short spikes — a spike has to persist
for ten trading days to move the smoothed high in full, and has to occupy more than a tenth
of the window's days to move the percentile high at all — so they show what the stock has
actually sustained.

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

Expected output: all unit tests and all 5 integration tests passing.

### How the integration tests work

Three of the five modes value the portfolio at live market prices, so their output is a
function of the market on the day it ran, not of the code alone. Comparing them against a
stored snapshot cannot work: the reference goes stale and fails spuriously, or the
tolerance is widened until the test cannot fail. Both happened (investment-reviews#29).

The suite therefore uses two mechanisms:

- **Tax report and list trades** are computed from parsed broker notes with no market
  data, so they are deterministic and compared against a reference output exactly. Log
  records are stripped first — they are captured alongside the report but are not part
  of it.
- **Full history, periodic review and annual review** are checked against invariants:
  properties that hold on any trading day whatever prices did. Each run must report no
  invariant violation, and must produce every table it should with at least one row. The
  second half matters as much as the first — without it a run that collapsed and printed
  nothing would report no violations and pass.

The invariants live in `review_invariants.py` and are asserted by the review itself, not
only by the test harness, so a nightly or ad-hoc run reports the same violations. They
are deliberately few, and each is chosen because it can genuinely fail:

| Invariant | What it catches |
|-----------|-----------------|
| Every position still held has a price and a value | Price fetching silently failing for some or all holdings |
| Grouped totals reconcile with the holdings total | A grouping that drops rows — an unexpected category, a null tag |
| The smoothed and percentile highs never exceed the raw high | A broken recent-high window |
| Every configured benchmark produces a row | Benchmarks being dropped silently, which they are when prices are missing |
| Progress to a doubling matches the multiple the holding's return implies | Transaction prices recorded in the wrong units |

A check that cannot run — a column it needs is absent — reports that, rather than
passing quietly.

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
- `--thesis-candidates`: JSON file defining a candidate universe per investment thesis (optional)

#### Thesis Candidate Analysis

Supplying `--thesis-candidates` measures how the wider investable set behind each thesis
performed, which distinguishes a weak thesis from a weak expression of a good thesis:

```bash
python3 portfolio.py --mode periodic-review \
  --base-dir ~/path/to/data \
  --start-date 2024-12-01 \
  --end-date 2025-01-01 \
  --thesis-candidates ~/path/to/theses.json
```

The file lists the candidate stocks for each thesis:

```json
{
  "schema_version": 1,
  "theses": [
    {
      "name": "European Defence",
      "candidates": [
        {"ticker": "RHM.DE", "name": "Rheinmetall"},
        {"ticker": "KOG.OL", "name": "Kongsberg Gruppen"}
      ]
    }
  ]
}
```

Tickers are Yahoo Finance symbols, as used elsewhere in the tool. Whether a candidate is
held is derived by matching the ticker against the parsed portfolio (holdings at the end of
the review period) and is never recorded in the file.

Each candidate is valued on the same basis as a benchmark: £1,000 invested at the start date
and valued at the evaluation date. Candidates with no usable price data are omitted and
warned about. Three outputs are added:

- **Summary tab**: one candidate-basket row per thesis, after the benchmark rows.
- **Thesis Summary tab**: per thesis, the equal-weighted candidate basket return, the
  equal-weighted return of the held candidates (each counted once, whatever the position
  size), the difference between them, and breadth — the proportion of candidates with a
  positive return, out of those with valid returns.
- **Thesis Candidate Performance tab**: every candidate, whether it is held, and its
  return, price, 90-day high and volatility.

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

### Nightly Alerts

The Google Sheets wrapper also watches for stocks that need attention before the next
monthly review, so brief price spikes are not missed:

- **Approaching a doubling** - `Progress to 2x` above 1.95, i.e. close to the profit-taking rule
- **Big movers** - a daily price change of at least the threshold, 3% by default

```bash
python3 update_google_sheet.py --daily-change-threshold 5
```

An email is sent only on nights where at least one stock qualifies. Configure the recipient
and SMTP relay under `notifications.alerts` in `config.yaml`; leaving `to` empty disables
alerts. On jarvis the relay is the `infra_mail` Proton Bridge on the host
(`host.docker.internal:1025`).

### Checking New Notes (`check_notes.py`)

A note's Yahoo Finance identity cannot be derived from the note. ISINs are only sometimes
accepted, unit trusts state their venue as "the manager of the unit trust", and one
exchange carries lines of the same fund in different currencies — `ARMG.L` and `ARMR.L`
are both Global X Defence Tech on the LSE, one priced in GBP and one in USD. Getting that
wrong is silent: it reports a plausible number for a different instrument.

It can be checked, though, and that is worth doing **before** new notes are copied into
the live tree:

```bash
python3 check_notes.py ~/Downloads/new-notes/
python3 check_notes.py one_note.pdf --json
python3 check_notes.py <history-dir> --since 2026-06-01 --quiet
```

For each security in each note it reports whether the note parses, the currency the note
states, the Yahoo identifier that would be used and where it came from, whether that
identifier resolves, and whether the market agrees with the note. Exit status is 0 when
everything checks out and 1 otherwise, so it can gate a script.

Two details carry most of the weight:

- **The currency comparison is the cheapest decisive check.** The note states a currency
  and so does Yahoo; if they differ, the identifier is wrong. That alone catches the
  `WDEF` and `ARMG` mispricings.
- **The price is compared against the trade date's high/low range**, not its closing
  price, because a trade executes intraday — and against *unadjusted* history, because
  adjusted history is back-corrected for dividends and a note from several years ago
  would otherwise sit 20-25% above its own range.

Where a price does not match, the ratio says what kind of wrong it is: about 100 is pence
against pounds, close to an FX rate is the right fund on the wrong currency line, a round
integer is Yahoo's split-adjusted history against an unadjusted note (reported as
something to look at rather than something wrong), and anything else is a different
instrument.

Run over the whole history the tool also reports holdings that have since been delisted
or renamed, which is true but not actionable — `--since` keeps a routine check to the
notes that are actually new.

### Reconciling a Stock's Tag (`reconcile_tags.py`)

A stock's tag is the directory its notes sit in — `<category>/<year>/<tag>/`. The scanner
takes the tag from the first note it processes for a given `(ticker, category)` and only
*warns* when later notes disagree, so a stock whose notes are split across two tags
aggregates under whichever was seen first, silently.

The notes exist in three places, and the two sync hops do not behave alike:

```
iCloud    ~/Library/Mobile Documents/com~apple~Pages/Documents/Investment/history
   |  ditto, hourly            — additive: never deletes from staging
staging   ~/Documents/iCloud-Staging/history
   |  rsync -a --delete, hourly — a mirror: jarvis is forced to match staging
jarvis    /Users/cl/srv/investment-reviews/state/history
```

That asymmetry dictates the order a retag must be made in. Because the first hop never
deletes, a note left behind in iCloud is copied back into staging; because the second hop
mirrors, anything left in staging is pushed to jarvis — and equally, anything removed
from staging is removed from jarvis on its own. So moves go **upstream first**, and each
step leaves nothing behind it that a later sync could use to recreate the old path.
Moving in the other order guarantees the move is undone within the hour.

```bash
# Where are this stock's notes filed?
python3 reconcile_tags.py Microsoft

# Exit 1 if they are not under one tag per category in all three locations
python3 reconcile_tags.py Microsoft --check

# Show what would move (no changes)
python3 reconcile_tags.py Microsoft --move-to "AI application layer"

# Move them, then verify nothing was left behind or recreated
python3 reconcile_tags.py Microsoft --move-to "AI application layer" --apply
```

The fragment is matched case-insensitively against note *filenames* (`.pdf`, `.csv`,
`.mhtml`); nothing else in the tree is touched. Category and year are always preserved —
only the tag directory changes.

It also reports notes that exist in some copies and not others, classified by direction,
because only one direction is a fault. A note upstream of where it is missing is waiting
for an hourly sync. A note in staging that is no longer in iCloud is a fault: `ditto`
does not delete, so staging keeps pushing it to jarvis. A note on jarvis that has left
staging removes itself on the next mirror. Only the middle case fails `--check`.

`--apply` refuses to start while either sync job is running, checks every destination
before moving anything, and re-checks all three locations afterwards. The pre-flight
matters: a collision discovered halfway through would leave the notes split across the
three locations, which is worse than the state being fixed.

Tag names are compared case-insensitively, because both hosts are macOS and a tag
directory is case-insensitively unique within its year. Asking for a tag that already
exists under a different spelling is therefore a no-op, and the difference is reported
rather than applied — respelling a tag renames a directory that other stocks are filed
under, so it is a tag-wide change and not one this tool makes on one holding's behalf.

Run it on the Macbook: it needs the iCloud and staging trees locally and reaches jarvis
over ssh. The same stock holding different tags in ISA and Taxable is not a fault — the
scanner keys the tag on `(ticker, category)` — and is reported without complaint.

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
- `thesis_config.py` - Thesis candidate configuration (`--thesis-candidates`)

### Layer 2: Portfolio Analysis (Modular Architecture)
**Responsibility:** StockNotes → mode-specific Pandas DataFrames

Organized as a **facade pattern** with specialized modules:

**Core facade:** `portfolio_analysis.py`
- Unified API for portfolio analysis
- Delegates to specialized modules

**Calculation modules:**
- `financial_metrics.py` - Pure financial calculations (MWRR, ROI, volatility)
- `review_invariants.py` - Properties every valid review must satisfy, checked on each run
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
