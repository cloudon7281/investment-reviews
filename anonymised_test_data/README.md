# Anonymised Test Data Directory

**IMPORTANT**: This directory contains anonymized test data for the investment portfolio analysis system.

## Anonymization

All test data in this directory has been anonymized to remove personal information:

- **Personal details**: All names replaced with "Mr John Doe"
- **Addresses**: All addresses replaced with "123 Test Street, London, SW1A 1AA"
- **Client references**: All references replaced with anonymized values
- **Contract numbers**: Randomly generated following HL pattern
- **Quantities**: Randomized to 1-100 range while maintaining consistency (same ticker = same quantity across all files)
- **Preserved data**: Dates, prices, tickers, ISINs, currencies, exchange rates (for validation)

## File Formats

- **PDF files (48 total)**:
  - Contract notes (45): HL-style purchase/sale confirmations with anonymized quantities
  - Letter-format (3): Subdivision, conversion, and merger notices
- **MHTML files (2)**: IBKR transaction data (no personal info)
- **CSV files (1)**: II pension transaction data (no personal info)
- **YAML files (7)**: Manual transaction notes for stock splits, conversions, renames (no personal info)

## Structure

```
anonymised_test_data/
├── ISA/              # ISA account transactions
│   ├── 2020/         # Transaction files from 2020
│   ├── 2021/         # Transaction files from 2021
│   ├── 2023/         # Transaction files from 2023
│   ├── 2024/         # Transaction files from 2024
│   └── 2025/         # Transaction files from 2025
│       ├── Defense/  # Defense stock transactions
│       └── Subdivision/  # Sezzle subdivision
├── Pension/          # Pension account transactions
│   └── 2025/
├── Taxable/          # Taxable account transactions
│   ├── 2020/
│   │   └── Conversion/  # JPMorgan conversion
│   ├── 2021/
│   ├── 2022/
│   ├── 2023/
│   ├── 2024/
│   │   └── Merger/      # Everbridge merger
│   └── 2025/
│       ├── Conversion/  # JPMorgan conversion
│       ├── Merger/      # Everbridge merger
│       └── tag_IBKR/    # IBKR transactions
└── reference_outputs/   # Reference test outputs
```

## Test Coverage

This test data covers the following test cases:

### Edge Cases
- **Subdivision**: Sezzle Inc (4 files: subdivision notice + 3 contract notes)
- **Conversion**: JPMorgan fund class conversion (2 files: conversion notice + contract note)
- **Merger**: Everbridge acquisition (2 files: merger notice + contract note)
- **Stock splits**: PNL, NVDA, etc. (via YAML files)
- **Ticker rename**: Kwesst → Defense Security (YAML file)

### Stock Categories
- **New stocks** (bought in period): AEVA, RHM.DE, PARRO.PA, KWE
- **Retained stocks** (held throughout): PLTR, FRCB, funds, CLS.TO, GOEV
- **Sold stocks** (sold during period): TECK, MSFT, ABX.TO, NVDA, SEZL
- **Bed-and-ISA**: Same-day sell/buy pairs (automatically detected and collapsed)

### Account Types
- **ISA**: Stocks & Shares ISA
- **Taxable**: Fund and Share Account
- **Pension**: SIPP

### Currencies
- **GBP**: PNL.L, 0P0000UR3O.L, 0P0000XNBQ.L, 0P0000XOMV.L
- **USD**: AEVA, PLTR, MSFT, FRCB, GOEV, NVDA, BE
- **EUR**: RHM.DE, PARRO.PA
- **CAD**: TECK, CLS.TO, ABX.TO

### Brokers
- **HL** (Hargreaves Lansdown): 45 contract note PDFs + 3 letter PDFs
- **IBKR** (Interactive Brokers): 2 MHTML files
- **II** (interactive investor): 1 CSV file
- **Manual**: 7 YAML files

## Usage

To use this test data, point the portfolio analysis tool to the `anonymised_test_data` directory:

```bash
python3 cli.py --base-dir anonymised_test_data --mode full-history
python3 cli.py --base-dir anonymised_test_data --mode periodic-review --start-date 2025-03-01 --end-date 2025-03-31 --eval-date 2025-06-16
python3 cli.py --base-dir anonymised_test_data --mode tax-report --tax-year FY25
python3 cli.py --base-dir anonymised_test_data --mode test
```

## Ticker → Quantity Mapping

Each ticker has been assigned a consistent random quantity (1-100 range):

| Ticker | Anonymized Qty | Notes |
|--------|----------------|-------|
| Various | 1-100 | Run batch_anonymize.py to see current mapping |

The exact mapping changes each time the anonymization scripts are run, but consistency within a run is maintained.

## Validation

All anonymized PDFs have been validated to ensure:
- ✅ Parser can extract all transaction fields
- ✅ Quantities are consistent across buy/sell pairs for same ticker
- ✅ Charges scale proportionally with quantity changes
- ✅ Dates, prices, tickers, currencies preserved
- ✅ No personal information remains

## Generation Scripts

These files were generated using:
- `scratch/batch_anonymize.py`: All HL contract note PDFs (45 files)
- `scratch/anonymize_special_pdfs.py`: Letter-format PDFs (3 files)
- Direct copy: MHTML, CSV, YAML files (no personal info)

To regenerate with different random quantities, run these scripts again.

## Total Files

- **PDF files**: 48 (45 contract notes + 3 letters)
- **MHTML files**: 2
- **CSV files**: 1
- **YAML files**: 7
- **Total transaction files**: 58
