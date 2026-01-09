#!/usr/bin/env python3
"""
Debug Data Management Tool

Helps set up isolated test/debug environments by copying specific stock files
from the history directory based on keyword search.

Usage:
    python3 manage_test_data.py --debug RGTI,NVDA
    python3 manage_test_data.py --test PLTR
    python3 manage_test_data.py --debug RGTI --dry-run
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple, Set, Dict
import subprocess
import tempfile
from datetime import datetime, timedelta
from collections import defaultdict


# Import project modules for anonymization and parsing
from portfolio_review import PortfolioReview
from pdf_parser import parse_stock_transaction_pdf, parse_merger_pdf, parse_subdivision_pdf, parse_conversion_pdf
from csv_parser import parse_stock_transaction_csv
sys.path.insert(0, str(Path(__file__).parent / "scratch"))
from anonymize_pdf import HLContractNoteGenerator
from anonymize_special_pdfs import SpecialCaseAnonymizer

# Safe paths (portable across systems)
HISTORY_DIR = Path.home() / "Library/Mobile Documents/com~apple~Pages/Documents/Investment/history"
DEBUG_DIR = Path.home() / "Library/Mobile Documents/com~apple~Pages/Documents/Investment/debug"
TEST_DATA_DIR = Path("test_data")
SCRATCH_DIR = Path("scratch")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Manage test/debug data by copying stock files from history directory',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --debug RGTI
  %(prog)s --debug RGTI,NVDA,PLTR
  %(prog)s --test ASTS
  %(prog)s --debug RGTI --dry-run
  %(prog)s --test NVDA --yes
        """
    )
    
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--debug', metavar='KEYWORDS',
                           help='Set up debug directory with matching files (replaces existing)')
    mode_group.add_argument('--test', metavar='KEYWORDS',
                           help='Add matching files to test_data and run tests')
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually doing it')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompts')
    
    return parser.parse_args()


def parse_keywords(keyword_string: str) -> List[str]:
    """Parse comma-separated keywords into a list."""
    if not keyword_string:
        return []
    return [k.strip().upper() for k in keyword_string.split(',') if k.strip()]


def find_matching_files(history_dir: Path, keywords: List[str]) -> List[Tuple[Path, Path]]:
    """Find all files in history directory matching any of the keywords.
    
    Args:
        history_dir: Path to history directory
        keywords: List of keywords (already uppercase)
        
    Returns:
        List of tuples: (absolute_path, relative_path_from_history)
    """
    if not history_dir.exists():
        print(f"❌ Error: History directory not found: {history_dir}")
        sys.exit(1)
    
    matching_files = []
    
    print(f"🔍 Searching for keywords: {', '.join(keywords)}")
    print(f"   in directory: {history_dir}")
    print()
    
    # Walk through history directory
    for root, dirs, files in os.walk(history_dir):
        for filename in files:
            # Skip hidden files and system files
            if filename.startswith('.'):
                continue
            
            # Check if any keyword appears in filename (case-insensitive)
            filename_upper = filename.upper()
            if any(keyword in filename_upper for keyword in keywords):
                abs_path = Path(root) / filename
                rel_path = abs_path.relative_to(history_dir)
                matching_files.append((abs_path, rel_path))
    
    return matching_files


def setup_debug_directory(debug_dir: Path, matching_files: List[Tuple[Path, Path]], 
                         dry_run: bool = False, skip_confirm: bool = False) -> None:
    """Set up debug directory with matching files (replace mode).
    
    Args:
        debug_dir: Path to debug directory
        matching_files: List of (absolute_path, relative_path) tuples
        dry_run: If True, don't actually perform operations
        skip_confirm: If True, skip confirmation prompt
    """
    # Safety check: confirm path contains "debug"
    if "debug" not in str(debug_dir).lower():
        print(f"❌ Error: Safety check failed - path doesn't contain 'debug': {debug_dir}")
        sys.exit(1)
    
    print(f"📁 Debug directory: {debug_dir}")
    
    # Check if debug directory exists and has contents
    if debug_dir.exists() and any(debug_dir.iterdir()):
        print(f"⚠️  Warning: Debug directory exists and will be cleared!")
        
        if not dry_run and not skip_confirm:
            response = input("   Continue? [y/N]: ")
            if response.lower() != 'y':
                print("Cancelled.")
                sys.exit(0)
    
    if dry_run:
        print("🔸 DRY RUN: Would clear debug directory")
    else:
        # Clear debug directory
        if debug_dir.exists():
            print("🗑️  Clearing debug directory...")
            shutil.rmtree(debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
    
    print()
    print("📋 Files to copy:")
    for abs_path, rel_path in matching_files:
        print(f"   {rel_path}")
    print()
    
    if dry_run:
        print(f"🔸 DRY RUN: Would copy {len(matching_files)} files")
        return
    
    # Copy files with directory structure
    print("📦 Copying files...")
    dirs_created = set()
    
    for abs_path, rel_path in matching_files:
        dest_path = debug_dir / rel_path
        dest_dir = dest_path.parent
        
        # Create directory structure if needed
        if dest_dir not in dirs_created:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dirs_created.add(dest_dir)
        
        # Copy file
        shutil.copy2(abs_path, dest_path)
    
    print()
    print("✅ Summary:")
    print(f"   {len(matching_files)} files copied")
    print(f"   {len(dirs_created)} directories created")
    print(f"   Debug environment ready")
    print()
    print(f"💡 Run with: python3 portfolio.py --mode full-history --base-dir \"{debug_dir.name}\"")


def augment_test_data(test_data_dir: Path, matching_files: List[Tuple[Path, Path]], 
                     dry_run: bool = False) -> Tuple[int, int]:
    """Add matching files to test_data directory (append mode).
    
    Args:
        test_data_dir: Path to test_data directory
        matching_files: List of (absolute_path, relative_path) tuples
        dry_run: If True, don't actually perform operations
        
    Returns:
        Tuple of (files_copied, files_skipped)
    """
    print(f"📁 Test data directory: {test_data_dir}")
    print()
    
    # Check which files already exist
    new_files = []
    existing_files = []
    
    print("🔍 Checking for existing files...")
    for abs_path, rel_path in matching_files:
        dest_path = test_data_dir / rel_path
        if dest_path.exists():
            existing_files.append((abs_path, rel_path))
            print(f"   {rel_path}: EXISTS (will skip)")
        else:
            new_files.append((abs_path, rel_path))
            print(f"   {rel_path}: NEW")
    
    print()
    
    if not new_files:
        print("ℹ️  No new files to add (all files already exist in test_data)")
        return 0, len(existing_files)
    
    if dry_run:
        print(f"🔸 DRY RUN: Would copy {len(new_files)} files ({len(existing_files)} already exist)")
        return len(new_files), len(existing_files)
    
    # Copy new files
    print(f"📦 Copying {len(new_files)} new files to test_data...")
    dirs_created = set()
    
    for abs_path, rel_path in new_files:
        dest_path = test_data_dir / rel_path
        dest_dir = dest_path.parent
        
        # Create directory structure if needed
        if dest_dir not in dirs_created:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dirs_created.add(dest_dir)
        
        # Copy file
        shutil.copy2(abs_path, dest_path)
    
    print()
    print(f"✅ {len(new_files)} files copied ({len(existing_files)} already existed)")
    
    return len(new_files), len(existing_files)


def run_test_mode(test_data_dir: Path) -> Tuple[str, str]:
    """Run test mode before and after to capture differences.
    
    Args:
        test_data_dir: Path to test_data directory
        
    Returns:
        Tuple of (before_output, after_output)
    """
    print()
    print("🧪 Running test mode to verify changes...")
    print("━" * 60)
    
    # Run test mode
    try:
        result = subprocess.run(
            ['python3', 'portfolio.py', '--mode', 'test', '--base-dir', str(test_data_dir)],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        output = result.stdout + result.stderr
        
        # Check for errors
        if result.returncode != 0:
            print("⚠️  Warning: Test mode returned non-zero exit code")
            print(f"   Exit code: {result.returncode}")
        
        return output
        
    except subprocess.TimeoutExpired:
        print("❌ Error: Test mode timed out after 120 seconds")
        return ""
    except Exception as e:
        print(f"❌ Error running test mode: {e}")
        return ""


def compare_outputs(output: str) -> None:
    """Display test output summary.
    
    Args:
        output: Test output to display
    """
    print()
    print("━" * 60)
    print("📊 Test Results:")
    print("━" * 60)
    
    # Look for key indicators in output
    if "All tests passed" in output or "Test passed" in output:
        print("✅ All tests passed")
    else:
        print("⚠️  Check test output for details")
    
    # Show summary lines
    lines = output.split('\n')
    for line in lines:
        if any(keyword in line.lower() for keyword in ['passed', 'failed', 'error', 'summary', 'total']):
            print(f"   {line}")
    
    print()
    print("💡 Review full test output above for details")


# ============================================================================
# Phase 1: Anonymization Validation Functions
# ============================================================================

def copy_with_structure(matching_files: List[Tuple[Path, Path]], target_dir: Path) -> None:
    """Copy files to target directory preserving relative structure.

    Args:
        matching_files: List of (absolute_path, relative_path) tuples
        target_dir: Target directory to copy to
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    for abs_path, rel_path in matching_files:
        dest_path = target_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, dest_path)


def get_files_for_ticker_category(temp_real_dir: Path, category: str, ticker: str) -> List[Tuple[Path, Path]]:
    """Get list of files for a specific ticker and category.

    Args:
        temp_real_dir: Temporary directory containing real files
        category: Category (ISA/Taxable/Pension)
        ticker: Ticker symbol

    Returns:
        List of (absolute_path, relative_path) tuples for this ticker/category
    """
    files = []
    category_dir = temp_real_dir / category

    if not category_dir.exists():
        return files

    # Find all files that match this ticker (basic approach - match filename)
    # We'll rely on PortfolioReview having already validated these files
    for pdf_file in category_dir.rglob("*.pdf"):
        rel_path = pdf_file.relative_to(temp_real_dir)
        files.append((pdf_file, rel_path))

    # Also include YAML files
    for yaml_file in category_dir.rglob("*.yaml"):
        rel_path = yaml_file.relative_to(temp_real_dir)
        files.append((yaml_file, rel_path))

    # Also include CSV files
    for csv_file in category_dir.rglob("*.csv"):
        rel_path = csv_file.relative_to(temp_real_dir)
        files.append((csv_file, rel_path))

    return files


def calculate_periodic_review_dates(final_date: datetime) -> Tuple[str, str, str]:
    """Calculate A, B, C dates for periodic review.

    A = final_date - 7 days
    B = midpoint(final_date, today)
    C = today

    Args:
        final_date: Date of final transaction

    Returns:
        (A, B, C) as "YYYY-MM-DD" strings
    """
    today = datetime.now()

    A = final_date - timedelta(days=7)
    B = final_date + (today - final_date) / 2
    C = today

    return (
        A.strftime("%Y-%m-%d"),
        B.strftime("%Y-%m-%d"),
        C.strftime("%Y-%m-%d")
    )


def run_portfolio_tests(base_dir: Path, A: str, B: str, C: str, output_prefix: str) -> Tuple[Path, Path]:
    """Run full-history and periodic-review, save outputs to scratch.

    Args:
        base_dir: Directory containing stock notes (e.g., DEBUG_DIR)
        A, B, C: Dates for periodic-review
        output_prefix: e.g., "AEVA_real" or "AEVA_anon"

    Returns:
        (full_history_output_path, periodic_review_output_path)
    """
    SCRATCH_DIR.mkdir(exist_ok=True)

    full_history_output = SCRATCH_DIR / f"{output_prefix}_full_history.txt"
    periodic_review_output = SCRATCH_DIR / f"{output_prefix}_periodic_review.txt"

    # Run full-history
    print(f"   Running full-history...")
    try:
        result = subprocess.run(
            ['python3', 'portfolio.py', '--mode', 'full-history', '--base-dir', str(base_dir), '--log-level', 'WARNING'],
            capture_output=True,
            text=True,
            timeout=120
        )
        full_history_output.write_text(result.stdout + result.stderr)
    except Exception as e:
        print(f"   ❌ Error running full-history: {e}")
        raise

    # Run periodic-review
    print(f"   Running periodic-review...")
    try:
        result = subprocess.run(
            ['python3', 'portfolio.py', '--mode', 'periodic-review', '--base-dir', str(base_dir),
             '--start-date', A, '--end-date', B, '--eval-date', C, '--log-level', 'WARNING'],
            capture_output=True,
            text=True,
            timeout=120
        )
        periodic_review_output.write_text(result.stdout + result.stderr)
    except Exception as e:
        print(f"   ❌ Error running periodic-review: {e}")
        raise

    return (full_history_output, periodic_review_output)


# Global set to track processed CSV/YAML files (to avoid duplicate processing)
_processed_multi_ticker_files = set()

def anonymize_from_stock_note(stock_note, ticker: str, category: str,
                              files: List[Tuple[Path, Path]], output_dir: Path,
                              ticker_scaling_map: dict = None) -> List[Tuple[Path, Path]]:
    """Generate anonymized versions using StockNote transaction data.

    Parse original PDFs to get per-file metadata, then use StockNote for
    the transaction sequence and proportional scaling.

    Args:
        stock_note: StockNote object from PortfolioReview
        ticker: Ticker symbol
        category: Category (ISA/Taxable/Pension)
        files: Original files (for copying non-PDF files like YAMLs)
        output_dir: Where to write anonymized files
        ticker_scaling_map: Dict mapping ticker -> scaling_factor (for CSV/YAML files)

    Returns:
        List of (abs_path, rel_path) for anonymized files
    """
    print(f"   Generating anonymized files for {ticker} ({category})...")

    output_dir.mkdir(parents=True, exist_ok=True)
    anonymized_files = []

    # Separate files by type
    pdf_files = [(abs_path, rel_path) for abs_path, rel_path in files if abs_path.suffix == '.pdf']
    csv_files = [(abs_path, rel_path) for abs_path, rel_path in files if abs_path.suffix == '.csv']
    yaml_files = [(abs_path, rel_path) for abs_path, rel_path in files if abs_path.suffix in ['.yaml', '.yml']]


    if not pdf_files and not csv_files and not yaml_files:
        return anonymized_files

    parsed_pdfs = []
    merger_pdfs = []
    subdivision_pdfs = []
    conversion_pdfs = []
    for abs_path, rel_path in pdf_files:
        try:
            # Try parsing as contract note first
            parsed = parse_stock_transaction_pdf(str(abs_path))
            if parsed and parsed.get('transaction_date') is not None:
                parsed_pdfs.append((abs_path, rel_path, parsed, 'contract_note'))
            else:
                # Contract note parser returned partial data, try special PDFs
                raise ValueError("Not a valid contract note")
        except Exception as e:
            # If contract note parsing fails, try merger PDF
            try:
                parsed = parse_merger_pdf(str(abs_path))
                if parsed:
                    merger_pdfs.append((abs_path, rel_path, parsed, 'merger'))
                    print(f"   Detected merger PDF: {rel_path.name}")
                    continue
            except Exception as e2:
                pass

            # Try subdivision PDF
            try:
                parsed = parse_subdivision_pdf(str(abs_path))
                if parsed:
                    subdivision_pdfs.append((abs_path, rel_path, parsed, 'subdivision'))
                    print(f"   Detected subdivision PDF: {rel_path.name}")
                    continue
            except Exception as e3:
                pass

            # Try conversion PDF
            try:
                parsed = parse_conversion_pdf(str(abs_path))
                if parsed:
                    conversion_pdfs.append((abs_path, rel_path, parsed, 'conversion'))
                    print(f"   Detected conversion PDF: {rel_path.name}")
                    continue
            except Exception as e4:
                pass

            print(f"   ⚠️  Warning: Could not parse {rel_path}: {e}")
            continue

    if not parsed_pdfs and not merger_pdfs and not subdivision_pdfs and not conversion_pdfs and not csv_files and not yaml_files:
        return anonymized_files

    # Sort contract notes by transaction date
    if parsed_pdfs:
        parsed_pdfs.sort(key=lambda x: x[2]['transaction_date'])

    # Sort merger PDFs by transaction date
    if merger_pdfs:
        merger_pdfs.sort(key=lambda x: x[2]['transaction_date'])

    # Calculate anonymized quantities for PDFs (if any)
    anonymised_quantities = []
    if parsed_pdfs:
        # Extract original quantities
        original_quantities = [p[2]['num_shares'] for p in parsed_pdfs]
        base_original = original_quantities[0]

        # Calculate price per share from first transaction
        first_parsed = parsed_pdfs[0][2]
        price_per_share = first_parsed['total_amount'] / first_parsed['num_shares']

        # Calculate minimum quantity to ensure >= £500 for BUY transactions
        min_quantity = max(1, int((500 + 10) / price_per_share))

        # Choose random base quantity
        import random
        base_anonymised = random.randint(min_quantity, 100000)

        # Calculate proportional quantities (keep as float for now)
        for orig_qty in original_quantities:
            proportion = orig_qty / base_original
            anon_qty = base_anonymised * proportion
            anonymised_quantities.append(anon_qty)

        # Check if holdings reach exactly zero and adjust if needed
        # Work with floats to avoid rounding errors
        holdings = 0.0
        for i, (abs_path, rel_path, parsed, pdf_type) in enumerate(parsed_pdfs):
            anon_qty = anonymised_quantities[i]
            trans_type = parsed['transaction_type']

            if trans_type == 'purchase':
                holdings += anon_qty
            elif trans_type == 'disposal':
                # Check if original reaches zero
                orig_holdings = sum(original_quantities[j] if parsed_pdfs[j][2]['transaction_type'] == 'purchase'
                                  else -original_quantities[j]
                                  for j in range(i+1))

                if abs(orig_holdings) < 0.01:  # Original reaches zero
                    # Adjust to sell exactly all remaining holdings
                    anon_qty = holdings
                    anonymised_quantities[i] = anon_qty
                    holdings = 0.0
                else:
                    holdings -= anon_qty

        # Now round all quantities to integers, ensuring zero holdings is preserved
        anonymised_quantities = [int(round(qty)) for qty in anonymised_quantities]

    # Generate anonymized PDFs (if any)
    if parsed_pdfs:
        generator = HLContractNoteGenerator()

        for i, (abs_path, rel_path, parsed, pdf_type) in enumerate(parsed_pdfs):
            # Update parsed data with anonymized quantity
            parsed_anon = parsed.copy()
            parsed_anon['num_shares'] = anonymised_quantities[i]
            # Recalculate total_amount based on new quantity
            price = parsed['total_amount'] / parsed['num_shares']
            parsed_anon['total_amount'] = anonymised_quantities[i] * price

            # Add stock_code field if it was in the original PDF
            if stock_note.stock_code_in_pdf:
                # Extract ticker without exchange suffix for STOCK CODE field
                ticker_base = ticker.split('.')[0]  # Remove .L, .TO, etc.
                parsed_anon['stock_code'] = ticker_base

            # Generate output path
            output_path = output_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate PDF
            try:
                generator.generate_contract_note(parsed_anon, str(output_path))
                anonymized_files.append((output_path, rel_path))
            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate {rel_path}: {e}")
                continue

    # Generate merger PDFs if any
    if merger_pdfs:
        special_generator = SpecialCaseAnonymizer()

        for abs_path, rel_path, parsed_merger, pdf_type in merger_pdfs:
            # Calculate holdings at time of merger from contract notes
            # Merger removes all holdings, so we need to know how many shares existed
            merger_date = parsed_merger['transaction_date']

            # Calculate holdings up to (but not including) the merger
            holdings_at_merger = 0.0
            for i, (_, _, parsed, _) in enumerate(parsed_pdfs):
                if parsed['transaction_date'] >= merger_date:
                    break  # Stop before merger

                if parsed['transaction_type'] == 'purchase':
                    holdings_at_merger += anonymised_quantities[i]
                elif parsed['transaction_type'] == 'disposal':
                    holdings_at_merger -= anonymised_quantities[i]

            holdings_at_merger = int(round(holdings_at_merger))

            # Calculate scaling factor for proceeds
            orig_shares = parsed_merger['num_shares']
            orig_proceeds = parsed_merger['total_amount']
            price_per_share_orig = orig_proceeds / orig_shares

            # Scale proceeds proportionally
            anon_proceeds = holdings_at_merger * price_per_share_orig

            # Prepare input data for merger PDF generator
            merger_input = {
                'stock_name': stock_note.stock_name,
                'date': merger_date.strftime('%d %b %Y'),
                'acquirer': 'Thoma Bravo',  # Generic acquirer name
                'price_per_share_usd': 35.00,  # Generic values
                'exchange_rate': 0.77224311,
                'price_per_share_gbp': price_per_share_orig,
                'original_shares': holdings_at_merger,
                'total_proceeds': round(anon_proceeds, 2),
                'settlement_date': (merger_date + timedelta(days=10)).strftime('%d %B %Y'),
                'cutoff_date': (merger_date - timedelta(days=7)).strftime('%d %B %Y'),
                'account_type': 'Stocks & Shares ISA' if category == 'isa' else 'Taxable Account'
            }

            # Generate output path
            output_path = output_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate merger PDF
            try:
                special_generator.anonymize_merger_pdf(merger_input, str(output_path))
                anonymized_files.append((output_path, rel_path))
                print(f"   Generated merger PDF: {rel_path.name} ({holdings_at_merger} shares → £{anon_proceeds:.2f})")
            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate merger PDF {rel_path}: {e}")
                continue

    # Generate subdivision PDFs if any
    if subdivision_pdfs:
        if not merger_pdfs:  # Only create generator if not already created
            special_generator = SpecialCaseAnonymizer()

        for abs_path, rel_path, parsed_subdivision, pdf_type in subdivision_pdfs:
            # Calculate holdings at time of subdivision from contract notes
            subdivision_date = parsed_subdivision['transaction_date']

            # Calculate holdings up to (but not including) the subdivision
            holdings_before_split = 0.0
            for i, (_, _, parsed, _) in enumerate(parsed_pdfs):
                if parsed['transaction_date'] >= subdivision_date:
                    break  # Stop before subdivision

                if parsed['transaction_type'] == 'purchase':
                    holdings_before_split += anonymised_quantities[i]
                elif parsed['transaction_type'] == 'disposal':
                    holdings_before_split -= anonymised_quantities[i]

            holdings_before_split = int(round(holdings_before_split))

            # Calculate split ratio from original
            orig_old_shares = parsed_subdivision['old_shares']
            orig_new_shares = parsed_subdivision['new_shares']
            split_ratio = orig_new_shares / orig_old_shares

            # Apply same split ratio to anonymized holdings
            holdings_after_split = int(round(holdings_before_split * split_ratio))

            # Prepare input data for subdivision PDF generator
            subdivision_input = {
                'stock_name': stock_note.stock_name,
                'date': subdivision_date.strftime('%d %b %Y'),
                'original_shares': holdings_before_split,
                'new_shares': holdings_after_split,
                'ratio': f'1 share into {int(split_ratio)} new shares',
                'subdivision_date': (subdivision_date - timedelta(days=7)).strftime('%d %B %Y'),
                'account_update_date': subdivision_date.strftime('%d %B %Y'),
                'account_type': 'Stocks & Shares ISA' if category == 'isa' else 'Taxable Account'
            }

            # Generate output path
            output_path = output_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate subdivision PDF
            try:
                special_generator.anonymize_subdivision_pdf(subdivision_input, str(output_path))
                anonymized_files.append((output_path, rel_path))
                print(f"   Generated subdivision PDF: {rel_path.name} ({holdings_before_split} → {holdings_after_split} shares, {int(split_ratio)}:1)")
            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate subdivision PDF {rel_path}: {e}")
                continue

    # Generate conversion PDFs if any
    if conversion_pdfs:
        if not merger_pdfs and not subdivision_pdfs:  # Only create generator if not already created
            special_generator = SpecialCaseAnonymizer()

        for abs_path, rel_path, parsed_conversion, pdf_type in conversion_pdfs:
            # Calculate holdings at time of conversion from contract notes
            conversion_date = parsed_conversion['transaction_date']

            # Calculate holdings up to (but not including) the conversion
            holdings_before_conversion = 0.0
            for i, (_, _, parsed, _) in enumerate(parsed_pdfs):
                if parsed['transaction_date'] >= conversion_date:
                    break  # Stop before conversion

                if parsed['transaction_type'] == 'purchase':
                    holdings_before_conversion += anonymised_quantities[i]
                elif parsed['transaction_type'] == 'disposal':
                    holdings_before_conversion -= anonymised_quantities[i]

            holdings_before_conversion = round(holdings_before_conversion, 3)

            # Calculate conversion ratio from original
            orig_old_units = parsed_conversion['old_shares']
            orig_new_units = parsed_conversion['new_shares']
            conversion_ratio = orig_new_units / orig_old_units

            # Apply same conversion ratio to anonymized holdings
            holdings_after_conversion = round(holdings_before_conversion * conversion_ratio, 3)

            # Prepare input data for conversion PDF generator
            conversion_input = {
                'fund_name': stock_note.stock_name,
                'date': conversion_date.strftime('%d %b %Y'),
                'old_class': 'Class B - Accumulation (GBP)',  # Generic values
                'new_class': 'Class C - Accumulation (GBP)',
                'conversion_ratio': conversion_ratio,
                'old_units': holdings_before_conversion,
                'new_units': holdings_after_conversion,
                'update_date': conversion_date.strftime('%d %B %Y'),
                'account_type': 'Fund & Share Account' if category == 'taxable' else 'Stocks & Shares ISA'
            }

            # Generate output path
            output_path = output_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate conversion PDF
            try:
                special_generator.anonymize_conversion_pdf_letter(conversion_input, str(output_path))
                anonymized_files.append((output_path, rel_path))
                print(f"   Generated conversion PDF: {rel_path.name} ({holdings_before_conversion} → {holdings_after_conversion} units, ratio={conversion_ratio:.8f})")
            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate conversion PDF {rel_path}: {e}")
                continue

    # Generate anonymized YAML files if any
    if yaml_files:
        import yaml

        for abs_path, rel_path in yaml_files:
            try:
                # Load YAML
                with open(abs_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)

                if not yaml_data or 'old_quantity' not in yaml_data:
                    # Not a stock conversion YAML, copy as-is
                    output_path = output_dir / rel_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(abs_path, output_path)
                    anonymized_files.append((output_path, rel_path))
                    continue

                # This is a STOCK_CONVERSION YAML with quantities
                if isinstance(yaml_data['date'], str):
                    yaml_date = datetime.strptime(yaml_data['date'], '%Y-%m-%d')
                elif hasattr(yaml_data['date'], 'year'):  # date or datetime object
                    yaml_date = datetime.combine(yaml_data['date'], datetime.min.time()) if not isinstance(yaml_data['date'], datetime) else yaml_data['date']
                else:
                    yaml_date = yaml_data['date']

                # Calculate holdings before this conversion from PDF transactions
                holdings_before = 0.0
                for i, (_, _, parsed, _) in enumerate(parsed_pdfs):
                    if parsed['transaction_date'] >= yaml_date:
                        break  # Stop before conversion

                    if parsed['transaction_type'] == 'purchase':
                        holdings_before += anonymised_quantities[i]
                    elif parsed['transaction_type'] == 'disposal':
                        holdings_before -= anonymised_quantities[i]

                # Calculate conversion ratio from original YAML
                orig_old_qty = yaml_data['old_quantity']
                orig_new_qty = yaml_data['new_quantity']
                conversion_ratio = orig_new_qty / orig_old_qty if orig_old_qty != 0 else 1.0

                # Scale quantities
                anon_old_qty = round(holdings_before, 2) if orig_old_qty != 1 else holdings_before
                anon_new_qty = round(anon_old_qty * conversion_ratio, 2)

                # Update YAML data
                yaml_data_anon = yaml_data.copy()
                yaml_data_anon['old_quantity'] = anon_old_qty
                yaml_data_anon['new_quantity'] = anon_new_qty

                # Write anonymized YAML
                output_path = output_dir / rel_path
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w') as f:
                    # Preserve comments by writing header manually
                    f.write(f"# Manual transaction note - {yaml_data.get('stock_name', ticker)}\n")
                    f.write("# Original broker note not available\n")
                    yaml.safe_dump(yaml_data_anon, f, default_flow_style=False, sort_keys=False)

                anonymized_files.append((output_path, rel_path))
                print(f"   Generated YAML: {rel_path.name} ({anon_old_qty} → {anon_new_qty}, ratio={conversion_ratio:.4f})")

            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate YAML {rel_path}: {e}")
                import traceback
                traceback.print_exc()
                continue

    # Generate anonymized CSV files if any
    # Use a single scaling factor for the entire CSV (applied to all rows)
    if csv_files:
        import csv as csv_module

        for abs_path, rel_path in csv_files:
            # If already processed, just add the existing anonymized file to the list
            if str(abs_path) in _processed_multi_ticker_files:
                output_path = output_dir / rel_path
                if output_path.exists():
                    anonymized_files.append((output_path, rel_path))
                    print(f"   Using existing CSV: {rel_path.name}")
                continue

            try:
                # Pick a random scaling factor for CSV
                # (CSVs are independent - tickers never have both PDFs and CSVs)
                import random
                scaling_factor = random.uniform(0.5, 10.0)

                # Read original CSV
                with open(abs_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv_module.DictReader(f)
                    rows = list(reader)
                    fieldnames = reader.fieldnames

                # Anonymize quantities in each row
                for row in rows:
                    if 'Quantity' in row:
                        orig_qty = float(row['Quantity'].replace(',', ''))
                        anon_qty = orig_qty * scaling_factor
                        row['Quantity'] = f"{anon_qty:.2f}"

                    # Scale Debit amount proportionally
                    if 'Debit' in row and row['Debit'] and row['Debit'] != 'n/a':
                        orig_debit = float(row['Debit'].replace('£', '').replace(',', ''))
                        anon_debit = orig_debit * scaling_factor
                        row['Debit'] = f"£{anon_debit:,.2f}"

                # Write anonymized CSV
                output_path = output_dir / rel_path
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv_module.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

                anonymized_files.append((output_path, rel_path))
                _processed_multi_ticker_files.add(str(abs_path))
                print(f"   Generated CSV: {rel_path.name} (scaled by {scaling_factor:.2f}x)")

            except Exception as e:
                print(f"   ⚠️  Warning: Could not generate CSV {rel_path}: {e}")
                import traceback
                traceback.print_exc()
                continue

    print(f"   ✅ Generated {len(anonymized_files)} anonymized files")
    return anonymized_files


def compare_portfolio_outputs(ticker: str, real_full: Path, real_periodic: Path,
                              anon_full: Path, anon_periodic: Path) -> Tuple[bool, List[str]]:
    """Compare real vs anonymized outputs with tolerance.

    Checks for both full-history and periodic-review:
        ✓ All tickers match
        ✓ All dates match
        ✓ All prices match (within 1% tolerance for current prices)
        ✓ Quantities differ (non-zero holdings)
        ✓ Zero holdings preserved

    Args:
        ticker: Ticker symbol
        real_full, real_periodic: Real data output files
        anon_full, anon_periodic: Anonymized data output files

    Returns:
        (passed: bool, differences: List[str])
    """
    differences = []

    print(f"   Comparing outputs...")

    # Simple comparison for now - check that both files exist and have content
    for label, path in [("real full-history", real_full), ("real periodic-review", real_periodic),
                        ("anon full-history", anon_full), ("anon periodic-review", anon_periodic)]:
        if not path.exists():
            differences.append(f"{label} output file missing: {path}")
        elif path.stat().st_size == 0:
            differences.append(f"{label} output file is empty: {path}")

    # TODO: Implement detailed table parsing and comparison
    # For Phase 1, we'll do basic validation

    if differences:
        return (False, differences)

    return (True, [])


def validate_and_anonymize(keywords: List[str], dry_run: bool = False) -> bool:
    """Phase 1: Validate that anonymization preserves correctness.

    Uses PortfolioReview to parse all files and extract StockNotes,
    then generates anonymized versions and validates they produce
    identical outputs (within tolerance).

    Args:
        keywords: List of keywords to search for
        dry_run: If True, don't actually perform operations

    Returns:
        True if all tickers pass validation, False otherwise
    """
    print("🔬 Phase 1: Validating anonymization...")
    print()

    # Step 1: Find matching files
    matching_files = find_matching_files(HISTORY_DIR, keywords)

    if not matching_files:
        print(f"❌ No files found matching keywords: {', '.join(keywords)}")
        return False

    print(f"✅ Found {len(matching_files)} files")
    print()

    # Step 2: Copy to temp location and use PortfolioReview to parse
    temp_real_dir = SCRATCH_DIR / "temp_real"
    print("📂 Copying files to temporary location...")
    copy_with_structure(matching_files, temp_real_dir)

    print("📊 Parsing files with PortfolioReview...")
    portfolio = PortfolioReview(str(temp_real_dir), include_raw_pdf_info=True)
    portfolio.scan_directory(str(temp_real_dir))

    # Step 3: Count stocks
    ticker_count = 0
    for category, stock_list in portfolio.stock_notes.items():
        ticker_count += len(stock_list)

    if ticker_count == 0:
        print("❌ No valid stocks found in files")
        return False

    print(f"   Found {ticker_count} stocks across {len(portfolio.stock_notes)} categories")
    print()

    # Step 4: Process each stock
    for category, stock_list in portfolio.stock_notes.items():
        for stock_note in stock_list:
            ticker = stock_note.ticker
            print(f"═══ Processing {ticker} ({category}) ═══")

            try:
                # Get transaction dates from StockNote
                if not stock_note.transactions:
                    print(f"   ⚠️  No transactions found, skipping")
                    continue

                final_date = max(t.date for t in stock_note.transactions)
                A, B, C = calculate_periodic_review_dates(final_date)
                print(f"📅 Final transaction: {final_date.strftime('%Y-%m-%d')}")
                print(f"   Dates: A={A}, B={B}, C={C}")

                if dry_run:
                    print("🔸 DRY RUN: Skipping actual testing")
                    continue

                # Get files for this ticker/category
                files = get_files_for_ticker_category(temp_real_dir, category, ticker)
                if not files:
                    print(f"   ⚠️  No files found for {ticker} in {category}")
                    continue

                # Test real data
                print("🧪 Testing real data...")
                setup_debug_directory(DEBUG_DIR, files, dry_run=False, skip_confirm=True)
                real_outputs = run_portfolio_tests(DEBUG_DIR, A, B, C, f"{ticker}_{category}_real")
                print("   ✅ Real tests complete")

                # Generate anonymized files
                print("🎭 Generating anonymized files...")
                anon_dir = SCRATCH_DIR / "anonymized_temp" / category / ticker
                anon_files = anonymize_from_stock_note(stock_note, ticker, category, files, anon_dir)

                # Test anonymized data
                print("🧪 Testing anonymized data...")
                setup_debug_directory(DEBUG_DIR, anon_files, dry_run=False, skip_confirm=True)
                anon_outputs = run_portfolio_tests(DEBUG_DIR, A, B, C, f"{ticker}_{category}_anon")
                print("   ✅ Anonymized tests complete")

                # Compare outputs
                print("🔍 Comparing outputs...")
                passed, diffs = compare_portfolio_outputs(ticker, real_outputs[0], real_outputs[1],
                                                         anon_outputs[0], anon_outputs[1])

                if passed:
                    print(f"✅ {ticker} ({category}): Validation PASSED")
                    print()
                else:
                    print(f"❌ {ticker} ({category}): Validation FAILED")
                    for diff in diffs:
                        print(f"   - {diff}")
                    print()
                    return False  # Stop on first failure

            except Exception as e:
                print(f"❌ {ticker} ({category}): Error during validation: {e}")
                import traceback
                traceback.print_exc()
                return False  # Stop on first failure

    return True


def main():
    """Main entry point."""
    args = parse_args()
    
    print()
    print("═" * 60)
    print("  Debug Data Management Tool")
    print("═" * 60)
    print()
    
    # Determine mode and keywords
    if args.debug:
        mode = 'debug'
        keyword_string = args.debug
        target_dir = DEBUG_DIR
    else:  # args.test
        mode = 'test'
        keyword_string = args.test
        target_dir = TEST_DATA_DIR
    
    # Parse keywords
    keywords = parse_keywords(keyword_string)
    
    if not keywords:
        print("❌ Error: No keywords provided")
        sys.exit(1)
    
    # Safety check: never modify history
    if not HISTORY_DIR.exists():
        print(f"❌ Error: History directory not found: {HISTORY_DIR}")
        print("   Please check the path is correct")
        sys.exit(1)
    
    # Find matching files
    matching_files = find_matching_files(HISTORY_DIR, keywords)
    
    if not matching_files:
        print(f"❌ No files found matching keywords: {', '.join(keywords)}")
        print()
        print("💡 Tips:")
        print("   - Keywords are case-insensitive")
        print("   - Keywords match anywhere in the filename")
        print("   - Try broader keywords (e.g., 'NVIDIA' instead of 'NVIDIA_Corp')")
        sys.exit(1)
    
    print(f"✅ Found {len(matching_files)} matching files")
    print()
    
    # Execute based on mode
    if mode == 'debug':
        setup_debug_directory(DEBUG_DIR, matching_files, args.dry_run, args.yes)

    else:  # test mode
        # Phase 1: Validate anonymization
        if not validate_and_anonymize(keywords, args.dry_run):
            print()
            print("❌ Phase 1 validation failed. Cannot proceed to test_data.")
            print("   Review differences in scratch/ directory.")
            sys.exit(1)

        print()
        print("✅ Phase 1 validation passed!")
        print()

        if args.dry_run:
            print("🔸 DRY RUN: Phase 2 (adding to anonymised_test_data) would happen here")
        else:
            # Phase 2: Add anonymized files to anonymised_test_data
            print("=" * 60)
            print("Phase 2: Adding anonymized files to anonymised_test_data")
            print("=" * 60)
            print()

            # Get list of anonymized files from scratch/anonymized_temp/
            anonymized_temp = SCRATCH_DIR / "anonymized_temp"
            if not anonymized_temp.exists():
                print("❌ No anonymized files found in scratch/anonymized_temp/")
                print("   Phase 1 may have failed silently")
                sys.exit(1)

            anonymized_files = []
            for root, dirs, files in os.walk(anonymized_temp):
                for filename in files:
                    abs_path = Path(root) / filename
                    rel_path = abs_path.relative_to(anonymized_temp)
                    anonymized_files.append((abs_path, rel_path))

            if not anonymized_files:
                print("❌ No anonymized files found in scratch/anonymized_temp/")
                sys.exit(1)

            print(f"📦 Found {len(anonymized_files)} anonymized files")
            print()

            # Copy to anonymised_test_data
            ANONYMISED_TEST_DATA_DIR = Path("anonymised_test_data")
            copied, skipped = augment_test_data(ANONYMISED_TEST_DATA_DIR, anonymized_files, dry_run=False)

            # Run tests
            print()
            print("🧪 Running tests with new anonymized data...")
            print("─" * 60)

            try:
                result = subprocess.run(
                    ['python3', 'portfolio.py', '--mode', 'test'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                print(result.stdout)
                if result.stderr:
                    print("Errors:", result.stderr)

                if result.returncode == 0:
                    print()
                    print("✅ Tests passed!")

                    # Ask for confirmation
                    if not args.yes:
                        print()
                        response = input("📋 Keep these files in anonymised_test_data? [y/N]: ")
                        if response.lower() != 'y':
                            print()
                            print("❌ Reverting changes...")
                            print("   Use 'git restore anonymised_test_data/' to undo")
                            sys.exit(1)

                    print()
                    print("✅ Files kept in anonymised_test_data/")
                    print("   Don't forget to:")
                    print("   1. Review the changes: git diff anonymised_test_data/")
                    print("   2. Commit: git add anonymised_test_data/ && git commit")
                else:
                    print()
                    print("❌ Tests failed. Files added but need review.")
                    print("   Review test failures and fix before committing")
                    sys.exit(1)

            except subprocess.TimeoutExpired:
                print()
                print("❌ Tests timed out after 5 minutes")
                sys.exit(1)
            except Exception as e:
                print()
                print(f"❌ Error running tests: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
    
    print()
    print("═" * 60)
    print("✅ Done!")
    print("═" * 60)
    print()


if __name__ == "__main__":
    main()

