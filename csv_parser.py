import csv
import re
from datetime import datetime
from typing import List, Dict, Any
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ticker_mapping import UK_TICKERS_IN_POUNDS

logger = logging.getLogger(__name__)

def parse_stock_transaction_csv(filename: str) -> List[Dict[str, Any]]:
    """
    Parse a CSV file containing stock transactions.
    
    Args:
        filename: Path to the CSV file
        
    Returns:
        List of dictionaries containing stock transaction data
    """
    logger.info(f"Parsing CSV file: {filename}")
    
    transactions = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            # Read the file content to handle BOM and encoding issues
            content = f.read()
            
            # Remove multiple BOM characters if present
            while content.startswith('\ufeff'):
                content = content[1:]
            
            # Parse CSV
            csv_reader = csv.DictReader(content.splitlines())
            
            for row_idx, row in enumerate(csv_reader, start=1):
                try:
                    # Extract and clean data
                    date_str = row.get('Date', '').strip()
                    symbol = row.get('Symbol', '').strip()
                    name = row.get('Name', '').strip()
                    quantity_str = row.get('Quantity', '').strip()
                    price_str = row.get('Price', '').strip()
                    debit_str = row.get('Debit', '').strip()
                    credit_str = row.get('Credit', '').strip()
                    
                    # Skip empty rows
                    if not date_str or not symbol:
                        continue
                    
                    # Parse date (DD/MM/YYYY format)
                    try:
                        transaction_date = datetime.strptime(date_str, '%d/%m/%Y')
                    except ValueError:
                        logger.warning(f"Could not parse date in row {row_idx}: '{date_str}'")
                        continue
                    
                    # Parse quantity (can be fractional)
                    try:
                        quantity = float(quantity_str.replace(',', ''))
                    except ValueError:
                        logger.warning(f"Could not parse quantity in row {row_idx}: '{quantity_str}'")
                        continue
                    
                    # Parse price (remove £ symbol and commas)
                    try:
                        price = float(price_str.replace('£', '').replace(',', ''))
                        
                        # Convert UK stock prices from pence to pounds if needed
                        if symbol.endswith('.L') and symbol not in UK_TICKERS_IN_POUNDS:
                            price = price / 100
                            logger.debug(f"Converted UK stock price from pence to pounds for {symbol}: {price_str} -> £{price:.4f}")
                            
                    except ValueError:
                        logger.warning(f"Could not parse price in row {row_idx}: '{price_str}'")
                        continue
                    
                    # Determine transaction type based on Debit/Credit
                    # If there's a Debit amount and Credit is "n/a", it's a BUY
                    # If there's a Credit amount and Debit is "n/a", it's a SELL
                    if debit_str and debit_str != 'n/a' and (not credit_str or credit_str == 'n/a'):
                        transaction_type = 'purchase'
                        # Parse debit amount (remove £, quotes, and commas)
                        amount_str = debit_str.replace('£', '').replace('"', '').replace(',', '')
                        try:
                            total_amount = float(amount_str)
                        except ValueError:
                            logger.warning(f"Could not parse debit amount in row {row_idx}: '{debit_str}'")
                            continue
                    elif credit_str and credit_str != 'n/a' and (not debit_str or debit_str == 'n/a'):
                        transaction_type = 'disposal'
                        # Parse credit amount (remove £, quotes, and commas)
                        amount_str = credit_str.replace('£', '').replace('"', '').replace(',', '')
                        try:
                            total_amount = float(amount_str)
                        except ValueError:
                            logger.warning(f"Could not parse credit amount in row {row_idx}: '{credit_str}'")
                            continue
                    else:
                        logger.warning(f"Could not determine transaction type in row {row_idx}: Debit='{debit_str}', Credit='{credit_str}'")
                        continue
                    
                    # Create transaction data in the same format as PDF/MHTML parsers
                    transaction_data = {
                        'transaction_type': transaction_type,
                        'stock_name': name,
                        'ticker': symbol,
                        'currency': 'GBP',  # All amounts in CSV are in GBP
                        'transaction_date': transaction_date,
                        'num_shares': int(quantity),  # Convert to int for consistency with other parsers
                        'price': price,
                        'total_amount': total_amount,
                        'exchange_rate': 1.0,  # No exchange rate needed for GBP
                        'settlement_date': None  # Not provided in CSV
                    }
                    
                    transactions.append(transaction_data)
                    logger.debug(f"Parsed transaction {row_idx}: {transaction_type} {quantity} {symbol} @ £{price} = £{total_amount}")
                    
                except Exception as e:
                    logger.error(f"Error processing row {row_idx} in CSV file {filename}: {str(e)}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error reading CSV file {filename}: {str(e)}")
        return []
    
    logger.info(f"Successfully parsed {len(transactions)} transactions from CSV file: {filename}")
    return transactions
