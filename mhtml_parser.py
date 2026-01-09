import re
from datetime import datetime
from typing import List, Dict, Any
import logging
from bs4 import BeautifulSoup
from ticker_mapping import SPECIAL_EXCHANGE_SUFFIX_MAP

logger = logging.getLogger(__name__)

def parse_stock_transaction_mhtml(filename: str) -> List[Dict[str, Any]]:
    """
    Parse an MHTML document containing stock transactions.
    
    Args:
        filename: Path to the MHTML file
        
    Returns:
        List of dictionaries containing stock transaction data
    """
    logger.info(f"Parsing MHTML file: {filename}")
    
    # Read the MHTML file
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract the HTML content from MHTML
    html_match = re.search(r'Content-Type: text/html.*?\n\n(.*?)(?=\n--\w+)', content, re.DOTALL)
    if not html_match:
        logger.error("Could not find HTML content in MHTML file")
        return []
    
    html_content = html_match.group(1)
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the main transaction table
    table = soup.find('table')
    if not table:
        logger.error("Could not find transaction table in HTML")
        return []
    
    # Log table headers for reference
    headers = [th.text.strip() for th in table.find_all('tr')[0].find_all('th')]
    # logger.debug(f"Table headers: {headers}")
    
    # Dictionary to aggregate transactions by date and description
    transactions = {}
    
    # Process each row in the table
    for row_idx, row in enumerate(table.find_all('tr')[1:], 1):  # Skip header row
        cols = row.find_all('td')
        if len(cols) < 13:  # Ensure we have all expected columns
            logger.warning(f"Row {row_idx} has insufficient columns: {len(cols)}")
            continue
            
        try:
            # Log raw content of each column
            logger.debug(f"\nProcessing row {row_idx}:")
            for i, col in enumerate(cols):
                logger.debug(f"Column {i} ({headers[i] if i < len(headers) else 'unknown'}): '{col.text.strip()}'")
            
            # Extract data from columns
            date_str = cols[0].text.strip()  # Date
            description = cols[2].text.strip()  # Description
            trans_type = cols[5].text.strip().lower()  # Transaction Type
            ticker = cols[6].text.strip()  # Symbol
            
            # Parse quantity with validation
            quantity_str = cols[8].text.strip().replace(',', '')  # Quantity
            logger.debug(f"Raw quantity string: '{quantity_str}'")
            # Allow negative quantities for sell transactions
            clean_quantity_str = quantity_str.replace('.', '').replace('-', '')
            if not clean_quantity_str.isdigit():
                logger.warning(f"Skipping row {row_idx} with invalid quantity: '{quantity_str}'")
                continue
            quantity = float(quantity_str)
            
            price_str = cols[10].text.strip()  # Price
            net_amount_str = cols[11].text.strip().replace(',', '').replace('£', '').lstrip('-')  # Net Amount, strip leading '-'
            exchange_rate_str = cols[12].text.strip().replace(',', '')  # Exchange Rate
            
            # Parse date
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')  # Updated date format
            except ValueError:
                logger.warning(f"Could not parse date in row {row_idx}: '{date_str}'")
                continue
                
            # Parse price and currency
            price_match = re.match(r'([\d,]+\.?\d*)\s+([A-Z]{3})', price_str)
            if not price_match:
                logger.warning(f"Could not parse price string in row {row_idx}: '{price_str}'")
                continue
                
            price = float(price_match.group(1).replace(',', ''))
            currency = price_match.group(2)
            
            # Validate and parse net amount
            if not net_amount_str.replace('.', '').isdigit():
                logger.warning(f"Skipping row {row_idx} with invalid net amount: '{net_amount_str}'")
                continue
            net_amount = float(net_amount_str)
            
            # Validate and parse exchange rate
            if not exchange_rate_str.replace('.', '').isdigit():
                logger.warning(f"Skipping row {row_idx} with invalid exchange rate: '{exchange_rate_str}'")
                continue
            exchange_rate = float(exchange_rate_str)
            
            # Add exchange suffix to ticker
            if ticker in SPECIAL_EXCHANGE_SUFFIX_MAP:
                ticker = f"{ticker}{SPECIAL_EXCHANGE_SUFFIX_MAP[ticker]}"
                logger.debug(f"Added exchange suffix to ticker: '{ticker}'")
            else:
                logger.debug(f"No exchange suffix mapping found for ticker in row {row_idx}: '{ticker}'")
            
            logger.debug(f"Quantity: {quantity}, Net amount: {net_amount}, Price: {price}, Currency: {currency}, Exchange rate: {exchange_rate}")
            
            # Create transaction key
            key = (date, description)
            
            if key not in transactions:
                # Initialize new transaction
                # Convert transaction type to standard format ('purchase' or 'sale')
                transaction_type = 'purchase' if trans_type == 'buy' else 'sale'
                
                transactions[key] = {
                    'transaction_date': date,
                    'ticker': ticker,
                    'num_shares': quantity,
                    'price': price,
                    'currency': currency,
                    'exchange_rate': exchange_rate,
                    'total_amount': net_amount,
                    'stock_name': description,
                    'transaction_type': transaction_type
                }
                logger.debug(f"Created new transaction for {description} on {date} (type: {transaction_type})")
            else:
                # Aggregate with existing transaction
                existing = transactions[key]
                existing_type = existing.get('transaction_type', 'unknown')
                current_type = 'purchase' if trans_type == 'buy' else 'sale'
                
                # Validate that transaction types match
                if existing_type != current_type:
                    logger.warning(f"Transaction type mismatch for {description} on {date}: existing={existing_type}, current={current_type}. Skipping aggregation.")
                    continue
                
                if trans_type == 'buy':
                    existing['num_shares'] += quantity
                    existing['total_amount'] += net_amount
                else:  # sell
                    # Handle negative quantities from IBKR files
                    if quantity < 0:
                        existing['num_shares'] += quantity  # quantity is already negative, so this subtracts
                    else:
                        existing['num_shares'] -= quantity  # quantity is positive, so subtract it
                    existing['total_amount'] += net_amount
                logger.debug(f"Aggregated transaction for {description} on {date}; num_shares now {existing['num_shares']}, total_amount now {existing['total_amount']}")
                    
        except Exception as e:
            logger.warning(f"Error processing row {row_idx}: {str(e)}")
            continue
    
    # Convert to list and filter out any transactions with zero shares
    result = [t for t in transactions.values() if t['num_shares'] != 0]
    
    logger.info(f"Found {len(result)} stock transactions")
    return result 