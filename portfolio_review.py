import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from logger import logger
import re
from pdf_parser import parse_stock_transaction_pdf, parse_subdivision_pdf, parse_conversion_pdf, parse_merger_pdf, extract_stock_name
from mhtml_parser import parse_stock_transaction_mhtml
from csv_parser import parse_stock_transaction_csv
from yaml_parser import parse_stock_transaction_yaml

@dataclass
class StockTransaction:
    """Represents an individual buy/sell transaction for a stock."""
    date: datetime
    transaction_type: str  # 'BUY', 'SELL', 'STOCK_CONVERSION', or 'TRANSFER'
    quantity: int
    price_per_share: float
    total_amount: float
    new_quantity: Optional[int] = None  # For stock conversions, the new number of shares after conversion
    new_ticker: Optional[str] = None  # For stock conversions, the new ticker symbol (if changed)
    new_currency: Optional[str] = None  # For stock conversions, the new currency (if changed)
    
    def get_date(self) -> datetime:
        """Get the transaction date."""
        return self.date
    
    def get_transaction_type(self) -> str:
        """Get the transaction type (BUY, SELL, STOCK_CONVERSION, or TRANSFER)."""
        return self.transaction_type
    
    def get_quantity(self) -> int:
        """Get the number of shares."""
        return self.quantity
    
    def get_price_per_share(self) -> float:
        """Get the price per share."""
        return self.price_per_share
    
    def get_total_amount(self) -> float:
        """Get the total transaction amount."""
        return self.total_amount
    
    def get_new_quantity(self) -> Optional[int]:
        """Get the new number of shares after conversion (for STOCK_CONVERSION transactions)."""
        return self.new_quantity
    
    def get_new_ticker(self) -> Optional[str]:
        """Get the new ticker symbol after conversion (for STOCK_CONVERSION transactions)."""
        return self.new_ticker
    
    def get_new_currency(self) -> Optional[str]:
        """Get the new currency after conversion (for STOCK_CONVERSION transactions)."""
        return self.new_currency

@dataclass
class StockNote:
    """Represents a stock note with its metadata."""
    file_path: str
    category: str  # 'new', 'retained', or 'sold'
    subcategory: Optional[str]  # For new stocks, this is the category (e.g., 'pharma')
    review_date: Optional[datetime]  # For retained stocks, this is the DDMMYY from the directory name
    stock_name: Optional[str] = None
    shares: Optional[int] = None
    post_split_shares: Optional[int] = None
    ticker: Optional[str] = None
    transaction_date: Optional[datetime] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    exchange_rate: Optional[float] = None
    dealing_charge: Optional[float] = None
    fx_charge: Optional[float] = None
    total_charges: Optional[float] = None
    settlement_date: Optional[datetime] = None
    total_amount_adjusted: bool = False  # Flag to indicate if total_amount has been adjusted for partial sales
    transactions: Optional[List[StockTransaction]] = None  # List of individual buy/sell transactions
    tag: Optional[str] = None  # Tag assigned based on directory structure (first transaction only)
    stock_code_in_pdf: Optional[bool] = None  # Track if STOCK CODE was present in original PDF (for anonymization)

    def __post_init__(self):
        """Extract stock name, shares, and ticker from the file path."""
        if not self.stock_name:
            self.stock_name = extract_stock_name(os.path.basename(self.file_path))
        if not self.shares:
            self.shares = self._extract_shares(os.path.basename(self.file_path))
        if not self.ticker:
            self.ticker = self._extract_ticker(os.path.basename(self.file_path))

    def _extract_shares(self, filename: str) -> Optional[int]:
        """Extract number of shares from filename."""
        # Look for patterns like "X shares" in the filename
        match = re.search(r'(\d+)\s*shares?', filename, re.IGNORECASE)
        return int(match.group(1)) if match else None

class PortfolioReview:
    def __init__(self, base_dir: Path, mode: str = 'full-history',
                 include_categories: List[str] = None,
                 include_tags: List[str] = None,
                 exclude_tags: List[str] = None,
                 include_years: List[int] = None,
                 include_raw_pdf_info: bool = False):
        """Initialize the portfolio review processor.

        Args:
            base_dir: Base directory containing stock notes
            mode: Processing mode ('full-history', 'periodic-review', 'tax-report')
            include_categories: List of categories to include (e.g., ['isa', 'taxable'])
            include_tags: List of tag phrases to include (mutually exclusive with exclude_tags)
            exclude_tags: List of tag phrases to exclude (mutually exclusive with include_tags)
            include_years: List of years to include
            include_raw_pdf_info: If True, include raw PDF info (e.g., stock_code_in_pdf) in StockNote
        """
        self.base_dir = Path(base_dir)
        self.mode = mode
        self.include_raw_pdf_info = include_raw_pdf_info
        
        # Store filter parameters
        self.include_categories = include_categories
        self.include_tags = include_tags
        self.exclude_tags = exclude_tags
        self.include_years = include_years
        
        # Ticker mapping for handling stock conversions that change ticker symbols
        # Maps final ticker -> original ticker for transitive lookups
        self.ticker_mapping: Dict[str, str] = {}
        
        # Initialize stock_notes structure for full history mode
        self.stock_notes: Dict[str, List[StockNote]] = {
            'isa': [],
            'taxable': [],
            'pension': []
        }
        
        # Scan directory to populate stock_notes
        self.scan_directory(base_dir)
    
    def ticker_to_key(self, ticker: str) -> str:
        """
        Convert a ticker symbol to the original key used for storing the stock.
        Handles transitive mapping for stock conversions that change ticker symbols.
        
        Args:
            ticker: The ticker symbol to look up
            
        Returns:
            The original ticker symbol used as the key
        """
        # Walk the mapping transitively to find the original ticker
        current_ticker = ticker
        visited = set()  # Prevent infinite loops
        
        while current_ticker in self.ticker_mapping:
            if current_ticker in visited:
                logger.warning(f"Circular ticker mapping detected for {ticker}")
                break
            visited.add(current_ticker)
            current_ticker = self.ticker_mapping[current_ticker]
        
        return current_ticker
    
    def _should_include_file(self, account_type: str, year: str, tag: Optional[str]) -> bool:
        """
        Determine if a file should be included based on filter criteria.
        
        Args:
            account_type: The account type (e.g., 'isa', 'taxable', 'pension')
            year: The year from the directory structure
            tag: The tag from the directory structure (may be None)
            
        Returns:
            True if the file should be included, False otherwise
        """
        # Category filter
        if self.include_categories and account_type not in self.include_categories:
            return False
        
        # Year filter
        if self.include_years and int(year) not in self.include_years:
            return False
        
        # Tag filters (only check if tag is not None)
        if tag:
            if self.include_tags:
                # Include only if tag contains any of the phrases
                if not any(phrase.lower() in tag.lower() for phrase in self.include_tags):
                    return False
            if self.exclude_tags:
                # Exclude if tag contains any of the phrases
                if any(phrase.lower() in tag.lower() for phrase in self.exclude_tags):
                    return False
        
        return True
    
    def _detect_bed_and_isa_transactions(self, transactions: List[StockTransaction]) -> List[StockTransaction]:
        """
        Detect and replace bed-and-ISA buy/sell pairs with TRANSFER transactions.
        
        Bed-and-ISA criteria:
        1. Buy and sell of the same stock on the same day
        2. 0.9 < bought_units/sold_units <= 1.0
        
        Args:
            transactions: List of transactions for a stock
            
        Returns:
            List of transactions with bed-and-ISA pairs replaced by TRANSFER transactions
        """
        if len(transactions) < 2:
            return transactions
        
        # Group transactions by date
        transactions_by_date = {}
        for txn in transactions:
            # Ensure we have a datetime object
            if isinstance(txn.date, str):
                try:
                    txn_date = datetime.strptime(txn.date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Could not parse date string: {txn.date}, using current date")
                    txn_date = datetime.now()
            else:
                txn_date = txn.date
            
            date_key = txn_date.date()  # Use date only, not time
            if date_key not in transactions_by_date:
                transactions_by_date[date_key] = []
            transactions_by_date[date_key].append(txn)
        
        processed_transactions = []
        
        for date, day_transactions in transactions_by_date.items():
            # Separate buy and sell transactions for this date
            buy_transactions = [txn for txn in day_transactions if txn.transaction_type == 'BUY']
            sell_transactions = [txn for txn in day_transactions if txn.transaction_type == 'SELL']
            
            # Add non-buy/sell transactions (like STOCK_CONVERSION) directly to processed
            other_transactions = [txn for txn in day_transactions if txn.transaction_type not in ['BUY', 'SELL']]
            processed_transactions.extend(other_transactions)
            
            # Try to match buy/sell pairs for bed-and-ISA detection
            matched_pairs = []
            unmatched_buys = buy_transactions.copy()
            unmatched_sells = sell_transactions.copy()
            
            for buy_txn in buy_transactions:
                if buy_txn in unmatched_buys:  # Not already matched
                    # Check if the total of all unmatched sells matches this buy (bed-and-ISA)
                    total_available_sells = sum(sell.quantity for sell in unmatched_sells)
                    
                    # Check if total sells match the buy quantity (within bed-and-ISA tolerance)
                    if abs(total_available_sells - buy_txn.quantity) <= 1:  # Allow 1 unit difference for rounding
                        # This is a bed-and-ISA - all sells match this buy
                        matching_sells = unmatched_sells.copy()
                        matched_pairs.append((buy_txn, matching_sells))
                        unmatched_buys.remove(buy_txn)
                        for sell_txn in matching_sells:
                            unmatched_sells.remove(sell_txn)
                        logger.info(f"Detected bed-and-ISA transaction: {buy_txn.quantity} bought, {total_available_sells} sold in {len(matching_sells)} batches on {date}")
            
            # Create TRANSFER transactions for matched pairs
            for buy_txn, sell_transactions in matched_pairs:
                # Calculate net effect
                total_sell_quantity = sum(sell.quantity for sell in sell_transactions)
                total_sell_amount = sum(sell.total_amount for sell in sell_transactions)
                net_units = buy_txn.quantity - total_sell_quantity  # Usually 0 or -1
                net_amount = total_sell_amount - buy_txn.total_amount  # Usually small positive
                
                # Create TRANSFER transaction
                transfer_txn = StockTransaction(
                    date=buy_txn.date,  # Use buy date
                    transaction_type='TRANSFER',
                    quantity=net_units,  # Net units (usually 0 or -1)
                    price_per_share=0.0,  # Transfers don't have meaningful price
                    total_amount=net_amount  # Net cash flow
                )
                processed_transactions.append(transfer_txn)
                logger.info(f"Created TRANSFER transaction: {net_units} units, £{net_amount:.2f} net")
            
            # Add unmatched transactions
            processed_transactions.extend(unmatched_buys)
            processed_transactions.extend(unmatched_sells)
        
        # Sort by date to maintain chronological order
        processed_transactions.sort(key=lambda txn: txn.date)
        
        logger.info(f"Bed-and-ISA processing: {len(transactions)} -> {len(processed_transactions)} transactions")
        return processed_transactions
    
    def _insert_transaction_chronologically(self, transactions: List[StockTransaction], new_transaction: StockTransaction) -> None:
        """Insert a transaction in chronological order (earliest first)."""
        if not transactions:
            transactions.append(new_transaction)
            return
        
        # Ensure new_transaction.date is a datetime object
        new_date = new_transaction.date
        if isinstance(new_date, str):
            try:
                new_date = datetime.strptime(new_date, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Could not parse date string: {new_date}, using current date")
                new_date = datetime.now()
        
        # Find the correct insertion point
        for i, existing_transaction in enumerate(transactions):
            existing_date = existing_transaction.date
            if isinstance(existing_date, str):
                try:
                    existing_date = datetime.strptime(existing_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Could not parse existing date string: {existing_date}, using current date")
                    existing_date = datetime.now()
            
            if new_date < existing_date:
                transactions.insert(i, new_transaction)
                return
        
        # If we get here, the new transaction is the latest
        transactions.append(new_transaction)

    def scan_directory(self, directory: str) -> None:
        """Scan directory for full history mode - single pass collecting all transactions chronologically."""
        if not os.path.exists(directory):
            logger.warning(f"Directory {directory} does not exist")
            return

        # Dictionary to track stocks by ticker for quick lookup
        stocks_by_ticker: Dict[str, StockNote] = {}
        
        
        # Collect all files with their paths
        # Separate YAML files (conversions) to process after other transactions
        all_files = []
        yaml_files = []
        
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                # Determine account type, year, and tag from directory structure
                account_type, year, tag = self._extract_account_type_and_year(file_path)
                if account_type and year:
                    # Apply filters (if any)
                    if not self._should_include_file(account_type, year, tag):
                        logger.debug(f"Skipping file {file_path} - excluded by filters")
                        continue
                    
                    # Separate YAML files for second pass
                    if file.endswith('.yaml') or file.endswith('.yml'):
                        yaml_files.append((file_path, account_type, year, tag, file))
                    else:
                        all_files.append((file_path, account_type, year, tag, file))
                else:
                    logger.debug(f"Skipping file {file_path} - could not determine account type or year")
        
        # Sort files by year to ensure chronological processing
        all_files.sort(key=lambda x: x[2])  # Sort by year (index 2)
        yaml_files.sort(key=lambda x: x[2])  # Sort YAML files by year too
        
        # Process files in chronological order
        for file_path, account_type, year, tag, file in all_files:
            try:
                if file.endswith('.pdf'):
                    if 'BOUGHT' in file.upper() or 'SOLD' in file.upper():
                        # Parse stock transaction PDF
                        data = parse_stock_transaction_pdf(file_path)
                        if data:
                            self._process_stock_transaction(data, file_path, account_type, year, tag, stocks_by_ticker)
                    elif 'subdivision' in file.lower():
                        # Parse subdivision PDF
                        data = parse_subdivision_pdf(file_path)
                        if data:
                            self._process_stock_split(data, file_path, account_type, year, stocks_by_ticker)
                    elif 'conversion' in file.lower():
                        # Parse conversion PDF
                        data = parse_conversion_pdf(file_path)
                        if data:
                            self._process_stock_split(data, file_path, account_type, year, stocks_by_ticker)
                    elif 'merger' in file.lower():
                        # Parse merger PDF
                        data = parse_merger_pdf(file_path)
                        if data:
                            self._process_stock_merger(data, file_path, account_type, year, stocks_by_ticker)
                elif file.endswith('.mhtml'):
                    # Parse MHTML file
                    try:
                        transactions = parse_stock_transaction_mhtml(file_path)
                        for data in transactions:
                            self._process_stock_transaction(data, file_path, account_type, year, tag, stocks_by_ticker)
                    except Exception as e:
                        logger.error(f"Error processing {file}: {str(e)}")
                elif file.endswith('.csv'):
                    # Parse CSV file
                    try:
                        transactions = parse_stock_transaction_csv(file_path)
                        for data in transactions:
                            self._process_stock_transaction(data, file_path, account_type, year, tag, stocks_by_ticker)
                    except Exception as e:
                        logger.error(f"Error processing {file}: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing {file}: {str(e)}")
        
        # Process YAML files in second pass (after all stocks have been created)
        # This ensures conversions can find their target stocks
        if yaml_files:
            logger.info(f"Processing {len(yaml_files)} YAML manual transaction files...")
        
        for file_path, account_type, year, tag, file in yaml_files:
            try:
                transactions = parse_stock_transaction_yaml(file_path)
                for data in transactions:
                    # Route based on transaction type
                    if data.get('transaction_type') == 'conversion':
                        self._process_stock_split(data, file_path, account_type, year, stocks_by_ticker)
                    else:
                        self._process_stock_transaction(data, file_path, account_type, year, tag, stocks_by_ticker)
            except Exception as e:
                logger.error(f"Error processing {file}: {str(e)}")

        # Detect bed-and-ISA transactions across categories
        self._detect_cross_category_bed_and_isa(stocks_by_ticker)
        
        # Merge StockNotes where ticker maps to another ticker (e.g., after stock conversions)
        # This ensures all transactions for a stock are in the same StockNote, using the original ticker as the key
        stocks_to_merge = []
        for stock_key, stock_note in stocks_by_ticker.items():
            ticker, category = stock_key
            # Check if this ticker maps to another ticker
            original_ticker = self.ticker_to_key(ticker)
            if original_ticker != ticker:
                # This ticker maps to another ticker - merge into the original ticker's StockNote
                original_stock_key = (original_ticker, category)
                if original_stock_key in stocks_by_ticker:
                    stocks_to_merge.append((stock_key, original_stock_key))
                else:
                    # Original ticker doesn't exist yet - this shouldn't happen, but log a warning
                    logger.warning(f"Stock {ticker} maps to {original_ticker}, but {original_ticker} StockNote doesn't exist in {category}")
        
        # Perform merges
        for mapped_stock_key, original_stock_key in stocks_to_merge:
            mapped_ticker, category = mapped_stock_key
            original_ticker, _ = original_stock_key
            
            mapped_stock_note = stocks_by_ticker[mapped_stock_key]
            original_stock_note = stocks_by_ticker[original_stock_key]
            
            # Merge transactions from mapped ticker into original ticker's StockNote
            if mapped_stock_note.transactions:
                # Add all transactions from mapped ticker to original ticker
                for txn in mapped_stock_note.transactions:
                    self._insert_transaction_chronologically(original_stock_note.transactions, txn)
                
                logger.info(f"Merged {len(mapped_stock_note.transactions)} transactions from {mapped_ticker} into {original_ticker} in {category}")
            
            # Remove the mapped ticker's StockNote
            del stocks_by_ticker[mapped_stock_key]
        
        # Validate that each stock's first transaction establishes cost basis
        # (filtering may have excluded initial purchases)
        # Valid first transactions: BUY (purchase), TRANSFER (bed-and-ISA), STOCK_CONVERSION (hand-coded conversion)
        valid_first_transactions = {'BUY', 'TRANSFER', 'STOCK_CONVERSION'}
        stocks_to_remove = []
        for stock_key, stock_note in stocks_by_ticker.items():
            ticker, category = stock_key
            if not stock_note.transactions:
                logger.warning(f"Stock {ticker} has no transactions after filtering - excluding entirely")
                stocks_to_remove.append(stock_key)
            elif stock_note.transactions[0].transaction_type not in valid_first_transactions:
                # Check if this ticker maps to another ticker via ticker_mapping
                # If so, check the original ticker's first transaction instead
                original_ticker = self.ticker_to_key(ticker)
                if original_ticker != ticker:
                    # This ticker maps to another ticker - check the original ticker's first transaction
                    original_stock_key = (original_ticker, category)
                    if original_stock_key in stocks_by_ticker:
                        original_stock_note = stocks_by_ticker[original_stock_key]
                        if original_stock_note.transactions and original_stock_note.transactions[0].transaction_type in valid_first_transactions:
                            # Original ticker has a valid first transaction, so this ticker is also valid
                            logger.debug(f"Stock {ticker} first transaction is {stock_note.transactions[0].transaction_type}, but maps to {original_ticker} which has valid first transaction - keeping")
                            continue
                
                logger.warning(f"Stock {ticker} first transaction is {stock_note.transactions[0].transaction_type}, not BUY/TRANSFER/STOCK_CONVERSION - excluding entirely")
                stocks_to_remove.append(stock_key)
        
        for stock_key in stocks_to_remove:
            del stocks_by_ticker[stock_key]
        
        # Add all collected stocks to the appropriate category
        for stock_note in stocks_by_ticker.values():
            self.stock_notes[stock_note.category].append(stock_note)
            logger.info(f"Added {stock_note.stock_name} ({stock_note.ticker}) to {stock_note.category} with {len(stock_note.transactions)} transactions")

    def _detect_cross_category_bed_and_isa(self, stocks_by_ticker: Dict[Tuple[str, str], StockNote]) -> None:
        """Detect bed-and-ISA transactions across different account categories.
        
        Bed-and-ISA typically involves:
        - Selling from Taxable account
        - Buying same amount in ISA account
        - On the same day
        
        Args:
            stocks_by_ticker: Dictionary mapping (ticker, category) to StockNote
        """
        # Group stocks by base ticker
        ticker_groups = {}
        for (ticker, category), note in stocks_by_ticker.items():
            if ticker not in ticker_groups:
                ticker_groups[ticker] = {}
            ticker_groups[ticker][category] = note
        
        # Process each ticker that appears in multiple categories
        for ticker, category_notes in ticker_groups.items():
            if len(category_notes) < 2:
                continue  # Need at least 2 categories for bed-and-ISA
            
            # Collect all transactions across all categories with their source category
            all_transactions = []
            for category, note in category_notes.items():
                for txn in note.transactions:
                    all_transactions.append((txn, category))
            
            # Group by date
            transactions_by_date = {}
            for txn, category in all_transactions:
                txn_date = txn.date if isinstance(txn.date, datetime) else datetime.strptime(txn.date, '%Y-%m-%d')
                date_key = txn_date.date()
                if date_key not in transactions_by_date:
                    transactions_by_date[date_key] = []
                transactions_by_date[date_key].append((txn, category))
            
            # Check each date for cross-category bed-and-ISA
            for date, day_txns in transactions_by_date.items():
                buys = [(txn, cat) for txn, cat in day_txns if txn.transaction_type == 'BUY']
                sells = [(txn, cat) for txn, cat in day_txns if txn.transaction_type == 'SELL']
                
                # Look for buy in one category and sell in another
                for buy_txn, buy_cat in buys:
                    for sell_txn, sell_cat in sells:
                        if buy_cat != sell_cat:  # Different categories
                            # Check if quantities match (bed-and-ISA criteria)
                            if abs(buy_txn.quantity - sell_txn.quantity) <= 1:
                                # This is a bed-and-ISA!
                                logger.info(f"Detected cross-category bed-and-ISA for {ticker} on {date}: "
                                           f"{sell_txn.quantity} sold from {sell_cat}, {buy_txn.quantity} bought in {buy_cat}")
                                
                                # Calculate cost basis for the shares being transferred
                                sell_note = category_notes[sell_cat]
                                buy_note = category_notes[buy_cat]
                                
                                # Get average cost per share in sell category up to this date
                                avg_cost = self._calculate_average_cost_basis(sell_note.transactions, sell_txn.date)
                                
                                # Total cost basis for all shares sold
                                total_cost_basis_sold = avg_cost * sell_txn.quantity
                                
                                # Cost basis for shares transferred to ISA (proportional)
                                transferred_cost_basis = total_cost_basis_sold * (buy_txn.quantity / sell_txn.quantity)
                                
                                logger.info(f"  Average cost in {sell_cat}: £{avg_cost:.2f}/share")
                                logger.info(f"  Total cost basis for {sell_txn.quantity} shares: £{total_cost_basis_sold:.2f}")
                                logger.info(f"  Transferred cost basis for {buy_txn.quantity} shares: £{transferred_cost_basis:.2f}")
                                
                                # Replace BUY in ISA with TRANSFER (increases invested by cost basis)
                                buy_note.transactions.remove(buy_txn)
                                transfer_to_isa = StockTransaction(
                                    date=buy_txn.date,
                                    transaction_type='TRANSFER',
                                    quantity=buy_txn.quantity,  # Positive = receiving shares
                                    price_per_share=transferred_cost_basis / buy_txn.quantity,
                                    total_amount=transferred_cost_basis  # Positive = increase invested
                                )
                                buy_note.transactions.append(transfer_to_isa)
                                
                                # Replace SELL in Taxable with TRANSFER to reduce invested by cost basis
                                # For bed-and-ISA, the "sale" in taxable is really a transfer, not a true sale
                                # The real "received" happens when shares are eventually sold from ISA
                                sell_note.transactions.remove(sell_txn)
                                transfer_from_taxable = StockTransaction(
                                    date=sell_txn.date,
                                    transaction_type='TRANSFER',
                                    quantity=-sell_txn.quantity,  # Negative = sending shares
                                    price_per_share=total_cost_basis_sold / sell_txn.quantity,
                                    total_amount=-total_cost_basis_sold  # Negative = reduce invested
                                )
                                sell_note.transactions.append(transfer_from_taxable)
                                
                                logger.info(f"Replaced BUY in {buy_cat} with TRANSFER: +{buy_txn.quantity} shares, +£{transferred_cost_basis:.2f} invested")
                                logger.info(f"Replaced SELL in {sell_cat} with TRANSFER: -{sell_txn.quantity} shares, -£{total_cost_basis_sold:.2f} invested")

    def _calculate_average_cost_basis(self, transactions: List[StockTransaction], as_of_date: datetime) -> float:
        """Calculate average cost per share based on all BUY transactions before a given date.
        
        Args:
            transactions: List of transactions for this stock
            as_of_date: Calculate cost basis as of this date
            
        Returns:
            Average cost per share
        """
        total_invested = 0.0
        total_shares = 0
        
        for txn in transactions:
            # Only consider transactions before the as_of_date
            txn_date = txn.date if isinstance(txn.date, datetime) else datetime.strptime(txn.date, '%Y-%m-%d')
            # Ensure we're comparing date objects
            txn_date_only = txn_date.date() if isinstance(txn_date, datetime) else txn_date
            as_of_date_only = as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date
            if txn_date_only >= as_of_date_only:
                                            continue
                                            
            if txn.transaction_type == 'BUY':
                total_invested += txn.total_amount
                total_shares += txn.quantity
            elif txn.transaction_type == 'STOCK_CONVERSION':
                # Adjust shares for conversions but not cost
                if txn.new_quantity:
                    # This is a ratio conversion
                    total_shares = int(total_shares * txn.new_quantity)
        
        if total_shares > 0:
            return total_invested / total_shares
        else:
            logger.warning(f"No shares held before {as_of_date}, using 0 cost basis")
            return 0.0

    def _extract_account_type_and_year(self, file_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract account type (ISA/taxable/pension), year, and tag from file path.
        
        Expected structure: <root>/[ISA|Taxable|Pension]/yyyy/(<tag>/)<files>
        """
        path_parts = file_path.split(os.sep)
        
        account_type = None
        year = None
        tag = None
        
        # Find ISA/taxable/pension directory
        for i, part in enumerate(path_parts):
            if part.lower() in ['isa', 'taxable', 'pension']:
                account_type = part.lower()
                
                # Look for year directory after ISA/taxable/pension
                if i + 1 < len(path_parts):
                    year_part = path_parts[i + 1]
                    if year_part.isdigit() and len(year_part) == 4:  # Year format YYYY
                        year = year_part
                        
                        # Check if there's a tag directory between year and files
                        if i + 2 < len(path_parts):
                            potential_tag = path_parts[i + 2]
                            # Check if this is a tag (not a file, and not another year)
                            if not potential_tag.endswith(('.pdf', '.mhtml', '.csv')) and not (potential_tag.isdigit() and len(potential_tag) == 4):
                                tag = potential_tag
                
                break
        
        return account_type, year, tag

    def _process_stock_transaction(self, data: dict, file_path: str, account_type: str, year: str, tag: Optional[str], stocks_by_ticker: Dict[Tuple[str, str], StockNote]) -> None:
        """Process a stock transaction (BUY or SELL) and add to the appropriate stock."""
        ticker = data.get('ticker')
        if not ticker:
            logger.error(f"No ticker found in transaction data for {file_path}")
            return
        
        # Use (ticker, account_type) tuple as key
        stock_key = (ticker, account_type)
        
        # Get or create stock note
        if stock_key not in stocks_by_ticker:
            stock_note_kwargs = {
                'file_path': file_path,
                'category': account_type,
                'subcategory': year,
                'review_date': None,
                'stock_name': data.get('stock_name'),
                'ticker': ticker,
                'currency': data.get('currency'),
                'transactions': [],
                'tag': tag  # Assign tag from first transaction
            }
            # Conditionally include raw PDF info
            if self.include_raw_pdf_info:
                stock_note_kwargs['stock_code_in_pdf'] = data.get('stock_code_in_pdf', False)

            stocks_by_ticker[stock_key] = StockNote(**stock_note_kwargs)
            logger.info(f"Created stock {ticker} in {account_type} with tag: {tag}")
        else:
            # Check if tag has changed (potential input error)
            existing_stock = stocks_by_ticker[stock_key]
            if existing_stock.tag != tag:
                logger.warning(f"Stock {ticker} in {account_type} tag changed from '{existing_stock.tag}' to '{tag}' - this may indicate an input error")
        
        stock_note = stocks_by_ticker[stock_key]
        
        # Create transaction
        # Use transaction_type from parsed data if available, otherwise infer from filename
        parsed_transaction_type = data.get('transaction_type')
        if parsed_transaction_type:
            transaction_type = 'BUY' if parsed_transaction_type == 'purchase' else 'SELL'
        else:
            transaction_type = 'BUY' if 'BOUGHT' in file_path.upper() else 'SELL'
        
        # Ensure date is a datetime object
        date_value = data.get('transaction_date') or data.get('settlement_date')
        if isinstance(date_value, str):
            try:
                date_value = datetime.strptime(date_value, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Could not parse date string: {date_value}, using current date")
                date_value = datetime.now()
        elif date_value is None:
            date_value = datetime.now()
        
        transaction = StockTransaction(
            date=date_value,
            transaction_type=transaction_type,
            quantity=data.get('num_shares', 0),
            price_per_share=data.get('price', 0.0),
            total_amount=data.get('total_amount', 0.0)
        )
        
        # Insert transaction chronologically
        self._insert_transaction_chronologically(stock_note.transactions, transaction)

    def _process_stock_split(self, data: dict, file_path: str, account_type: str, year: str, stocks_by_ticker: Dict[Tuple[str, str], StockNote]) -> None:
        """Process a stock conversion and add to the appropriate stock."""
        ticker = data.get('ticker')
        stock_name = data.get('stock_name')
        
        # Find all stocks with matching ticker or name across all categories (conversion applies to all)
        matching_stocks = []
        
        # Prefer matching by ticker (more robust), fall back to stock_name for conversion PDFs
        if ticker:
            # Match by ticker
            for stock_key, note in stocks_by_ticker.items():
                if stock_key[0] == ticker:  # stock_key is (ticker, category)
                    matching_stocks.append((stock_key, note))
        elif stock_name:
            # Fall back to matching by stock_name (for conversion PDFs that don't have ticker)
            for stock_key, note in stocks_by_ticker.items():
                if note.stock_name == stock_name:
                    matching_stocks.append((stock_key, note))
        else:
            logger.warning(f"No ticker or stock_name found in conversion data for {file_path}")
            return
        
        if not matching_stocks:
            identifier = ticker if ticker else stock_name
            logger.warning(f"No matching stock found for {identifier} in {file_path}")
            return
        
        # Create stock conversion transaction
        # For stock conversions, we'll use the old shares as quantity and new shares as new_quantity
        transaction = StockTransaction(
            date=data.get('transaction_date', datetime.now()),  # Use current date if not available
            transaction_type='STOCK_CONVERSION',
            quantity=data.get('old_shares', 0),  # Original number of shares
            price_per_share=0.0,  # Stock conversions don't have a price
            total_amount=0.0,  # Stock conversions don't have a monetary value
            new_quantity=data.get('new_shares', 0),  # New number of shares after conversion
            new_ticker=data.get('new_ticker'),  # New ticker symbol (if changed)
            new_currency=data.get('new_currency')  # New currency (if changed)
        )
        
        # Apply conversion to all matching stocks (across all categories)
        for stock_key, stock_note in matching_stocks:
            # Insert transaction chronologically
            self._insert_transaction_chronologically(stock_note.transactions, transaction)
            logger.info(f"Applied stock conversion to {stock_note.ticker} in {stock_note.category}")
        
        # If this conversion changes the ticker, update the ticker mapping (ticker-only, no category)
        if data.get('new_ticker') and matching_stocks:
            # Use first matching stock to get original ticker
            first_stock = matching_stocks[0][1]
            if data.get('new_ticker') != first_stock.ticker:
                new_ticker = data.get('new_ticker')
                original_ticker = self.ticker_to_key(first_stock.ticker)
                self.ticker_mapping[new_ticker] = original_ticker
                logger.info(f"Added ticker mapping: {new_ticker} -> {original_ticker}")

    def _process_stock_merger(self, data: dict, file_path: str, account_type: str, year: str, stocks_by_ticker: Dict[Tuple[str, str], StockNote]) -> None:
        """Process a stock merger and add as a sale transaction to the appropriate stock."""
        stock_name = data.get('stock_name')
        if not stock_name:
            logger.warning(f"No stock name found in merger data for {file_path}")
            return
        
        # Find all stocks with matching name across all categories (merger applies to all)
        matching_stocks = []
        for stock_key, note in stocks_by_ticker.items():
            if note.stock_name == stock_name:
                matching_stocks.append((stock_key, note))
        
        if not matching_stocks:
            logger.warning(f"No matching stock found for merger {stock_name} in {file_path}")
            return
        
        # Create merger transaction (effectively a sale)
        # For mergers, we treat it as a sale transaction where the shares are sold for cash
        transaction = StockTransaction(
            date=data.get('transaction_date', datetime.now()),  # Use merger date if available
            transaction_type='SELL',  # Treat merger as a sale
            quantity=data.get('num_shares', 0),  # Number of shares
            price_per_share=data.get('total_amount', 0.0) / data.get('num_shares', 1) if data.get('num_shares', 0) > 0 else 0.0,  # Price per share
            total_amount=data.get('total_amount', 0.0)  # Total cash proceeds
        )
        
        # Apply merger to all matching stocks (across all categories)
        for stock_key, stock_note in matching_stocks:
            # Insert transaction chronologically
            self._insert_transaction_chronologically(stock_note.transactions, transaction)
            logger.info(f"Added merger transaction for {stock_name} in {stock_note.category}: {data.get('num_shares', 0)} shares sold for £{data.get('total_amount', 0.0):.2f}")

    # Methods for full-history mode data access
    
    def get_all_tickers(self) -> List[Tuple[str, str]]:
        """Get all unique (ticker, category) combinations."""
        ticker_category_pairs = []
        for category_stocks in self.stock_notes.values():
            for stock in category_stocks:
                if stock.ticker:
                    ticker_category_pairs.append((stock.ticker, stock.category))
        return ticker_category_pairs
    
    def get_stock_currency(self, ticker: str, category: Optional[str] = None) -> Optional[str]:
        """Get currency for a specific stock, optionally filtered by category."""
        for cat, category_stocks in self.stock_notes.items():
            if category and cat != category:
                continue
            for stock in category_stocks:
                if stock.ticker == ticker:
                    return stock.currency
        return None
    
    def get_transaction_history(self, ticker: str, category: Optional[str] = None, skip_bed_and_isa: bool = False) -> List[StockTransaction]:
        """Get transaction history for a specific ticker, optionally filtered by category.
        
        Args:
            ticker: Stock ticker symbol
            category: Account category (isa/taxable/pension), if None returns first match
            skip_bed_and_isa: If True, skip bed-and-ISA processing (for tax reporting)
        """
        for cat, category_stocks in self.stock_notes.items():
            if category and cat != category:
                continue
            for stock in category_stocks:
                if stock.ticker == ticker:
                    raw_transactions = stock.transactions or []
                    if skip_bed_and_isa:
                        # Return raw transactions without bed-and-ISA processing
                        return raw_transactions
                    else:
                        # Apply bed-and-ISA processing to detect and replace buy/sell pairs within this category
                        processed_transactions = self._detect_bed_and_isa_transactions(raw_transactions)
                        return processed_transactions
        return []
    
    def get_stock_name(self, ticker: str, category: Optional[str] = None) -> Optional[str]:
        """Get stock name for a specific ticker, optionally filtered by category."""
        for cat, category_stocks in self.stock_notes.items():
            if category and cat != category:
                continue
            for stock in category_stocks:
                if stock.ticker == ticker:
                    return stock.stock_name
        return None
    
    def get_stock_account_type(self, ticker: str, category: Optional[str] = None) -> Optional[str]:
        """Get account type (ISA/taxable/pension) for a specific ticker, optionally filtered by category."""
        for cat, category_stocks in self.stock_notes.items():
            if category and cat != category:
                continue
            for stock in category_stocks:
                if stock.ticker == ticker:
                    return stock.category
        return None
    
    def get_stock_tag(self, ticker: str, category: Optional[str] = None) -> Optional[str]:
        """Get tag for a specific ticker, optionally filtered by category."""
        for cat, category_stocks in self.stock_notes.items():
            if category and cat != category:
                continue
            for stock in category_stocks:
                if stock.ticker == ticker:
                    return stock.tag
        return None

