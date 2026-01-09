# Cursor AI instructions

## Purpose

These are standing user instructions to Cursor to be followed when working on this project.

## Overview

The purpose of this project is a tool to help analysis of an investment portfolio.  The tool takes
as input stock notes in a variety of formats (PDF, MHTML etc.) representing individual transactions:
purchases, sales or more complex transactions such as stock splits or mergers.  It then either:
- in 'full-history' mode producs a report showing for every stock ever purchased key information 
  such as amount invested, current value, profit and loss etc.
- in 'periodic-review' mode produces a report with the information required for regularly monthly
  portfolio reviews: information on the subsequent performance of stocks bought, retained or sold
  as a result of the previous review
- in 'tax-report' mode produces a report on those transactions relevant for a tax report for a given
  financial year.

There is also a stock_splits.py file containing hard-coded stock splits for which the user has no
original note.

All reports take the form of both console output and a Numbers spreadsheet, with identical information
output to both.

Full-history mode also has an optional value-over-time mode, with additional output showing the 
portfolio value over time, in CSV format.

Stock notes live in a directory hierarchy of <root>/<category>/<year>/<tag>/<file>, where:
- category is one of ISA, Taxable or Pension
- year is in YYYY format
- tag is optional and is an arbitrary string.

These are used in the analysis and output of results.

## Architecture

The tool follows a simple architecture with the following separation-of-concerns.  This 
architecture should be followed.

- PortfolioReview is responsible for parsing all the input stock notes and turning them into 
  a dict of StockNotes.  This is generally 1-1 input note<->StockNote, but other than in tax-report
  mode it can 'collapse' bed-and-ISA transactions (where a stock is sold from outside a tax wrapper
  then bought back within a tax wrapper on the same day) into a single 'transfer' operation.

- PortfolioAnalysis performs all calculations, which are mode-specific, turning the output of PortfolioReview
  into mode-specific Pandas dataframes.
  - All calculations of how many stocks are held on a given day, what the prices were, what the
    exchange rates were, aggregation by tag etc. are done in PortfolioAnalysis.  No calculations should
    ever be done elsewhere.
  - Prices and exchange rates are obtained from the Yahoo Finance (YF) API.  This data is not 100% clean,
    and the logic to clean it lives in PortfolioAnalysis.  This includes detecting and omitting 'spikes'
    where a stock rises and then falls back more than 20% in a single day, or when UK stocks flip from
    pence to punds and back again, or handling gaps in data caused by bank holidays, weekends etc.
  - Within PortfolioAnalysis, batch_get_stock_prices is reponsible for returning stock prices in GBP.  It
    must handle all currency conversions.
  - PortfolioAnalysis maintains a price cache for efficiency - this is used for full-history + value-over-time
    processing.

- PortfolioReporter is responsible for rendering the dataframes to various output formats, currently
  console, Numbers and CSV.  It uses a data-driven approach for console and Numbers output, with 
  columns, formats and thresholds (for colour-coding) defined in data structures in reporter_definitions.py.

- portfolio.py contains the main(), which parses user input then invokes PortfolioReview, PortfolioAnalysis then
  PortfolioReporter in turn.

## Naming conventions

The following conventions are use for output file names.
 
 - Numbers: user-specified via --output-file
 - CSV: {Numbers_root}_value_over_time.csv
 - Logs: logs/stock_log_YYMMDD_nnn.log (auto-generated)

## Regression Tests

The tool has a test-mode for regression testing.  This runs a mix of unit tests and tests with real data.
- The input data for test-mode lives in test_data.
- The reference outputs that are checked against live in test_data/reference_outputs.

When developing new features, the final step must be to check for regressions by running test-mode and
checking for differences.  Typically these will be expected and will be additions.  All such differences
must be presented to the user and confirmed by the user before new reference outputs are cut.

## Development and debug practices

- Always remember to run in the correct Python virtual environment by running .venv/bin/activate.

- Always remember that debug output goes to the log files under logs/ (only the last 4 are kept), not
  to the console.

- The regression test input lives under test_data.  There are two other input data sources to be aware of.
  - "/Users/cl/Library/Mobile Documents/com~apple~Pages/Documents/Investment/history" contains the full
    live data set.  THIS MUST NEVER BE CHANGED, other than by the user.
  - "/Users/cl/Library/Mobile Documents/com~apple~Pages/Documents/Investment/debug" contains whatever
    subset of the full live data set is needed to diagnose the current problem.
  There is a "manage_test_data.py" tool you can use to select the subset of stock notes matching given
  phrases and either:
  - set up the debug directory just to include those stock notes and no others
  - add them to the test_data inputs.

- Never change the test dates for the periodic-review reference outputs or any other parameters without
  first explaining why you want to do that and seeking the user's explicit permission.

- All temporary working files (temporary scripts, console/Numbers outputs etc) should be put in the
  scratch/ directory.

- All files associated with plans - the plan itself, implementation details, test details, 'read me's
  etc. - should live in a plan-specific directory underneath the plans/ directory so that they are 
  cleanly separated from each other.

- Never run git commit or git push unless the user has given you explicit, bounded permission for the
  current session.

## Market Data Cache Behavior

The `MarketDataFetcher` class maintains in-memory caches that are **NOT persistent** between Python runs:

- **Price Cache (`self.price_cache`)**: Dictionary mapping ticker symbols to DataFrames with historical price data
- **Exchange Rate Cache (`self.exchange_rate_cache`)**: Dictionary mapping currency pairs to exchange rates

**Key behaviors:**
- Caches are **instance-based** - created fresh when `MarketDataFetcher()` is instantiated
- Caches are **NOT saved to disk** - cleared when Python process exits
- Caches persist **only during a single run** - reused within the same execution to avoid redundant API calls
- Cache is populated when `batch_get_stock_prices()` is called - if ticker not in cache, fetches from YF API and stores result
- Cache lookup happens before API calls - if ticker is in cache, returns cached data regardless of requested date range

**Implications:**
- First run in a session: cache empty, fetches fresh from YF API
- Subsequent calls in same session: uses cached data (may be shorter date range than requested)
- Different Python runs: cache is empty again, will fetch fresh

**Cache management:**
- Cache is populated by `batch_get_stock_prices()` which adds a 21-day buffer before requested start_date
- Volatility calculations need 90 days of data - if cache has less, calculations will be inaccurate
- `full_history` mode currently requests only 7 days (with buffer = 28 days max), which is insufficient for volatility

## Source control

The project is maintained under Git.