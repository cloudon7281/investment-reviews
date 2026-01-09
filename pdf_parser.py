import pdfplumber
import re
from datetime import datetime
from logger import logger
from ticker_mapping import TICKER_MAPPING, EXCHANGE_SUFFIX_MAP, SPECIAL_EXCHANGE_SUFFIX_MAP, STOCK_RENAME_MAP
import os
from typing import Optional, Dict, List, Tuple


def get_exchange_suffix(isin: str, ticker: str) -> str:
    """Get the exchange suffix for a stock based on its ISIN and ticker."""
    # First check if this ticker has a special case mapping
    if ticker in SPECIAL_EXCHANGE_SUFFIX_MAP:
        suffix = SPECIAL_EXCHANGE_SUFFIX_MAP[ticker]
        logger.debug(f"Using special case exchange suffix for {ticker}: {suffix}")
        return suffix
    
    # Otherwise use the country code from ISIN
    if not isin or len(isin) < 2:
        logger.warning(f"Invalid ISIN: {isin}")
        return ''
    
    country_code = isin[:2].upper()
    suffix = EXCHANGE_SUFFIX_MAP.get(country_code)
    if suffix is None:
        logger.warning(f"No exchange suffix mapping for country code: {country_code}")
        return ''
    
    return suffix

def parse_uk_stock_details(lines: List[str], stock_name_index: int, result: Dict) -> None:
    """Parse UK stock details from the PDF lines."""
    if stock_name_index + 1 >= len(lines):
        return
        
    shares_line = lines[stock_name_index + 1]
    parts = shares_line.split()
    
    # Filter out non-numeric parts (like 'XD' for ex-dividend)
    numeric_parts = []
    for part in parts:
        # Remove commas and try to convert to float
        clean_part = part.replace(',', '')
        try:
            float(clean_part)
            numeric_parts.append(clean_part)
        except ValueError:
            # Skip non-numeric parts like 'XD'
            logger.debug(f"Skipping non-numeric part: {part}")
            continue
    
    if len(numeric_parts) >= 2:
        try:
            # First number is quantity
            result['num_shares'] = float(numeric_parts[0])
            logger.debug(f"Found number of shares: {result['num_shares']}")
            
            # Second number is price in pence
            result['price'] = float(numeric_parts[1]) / 100  # Convert pence to pounds
            result['currency'] = 'GBP'
            logger.debug(f"Found price in pence: {numeric_parts[1]}, converted to pounds: {result['price']}")
            
            # Third number is total amount if present
            if len(numeric_parts) >= 3:
                result['total_amount'] = float(numeric_parts[2])
                logger.debug(f"Found total amount: {result['total_amount']}")
        except ValueError as e:
            logger.warning(f"Failed to parse UK format numbers from line: {e}")

def parse_non_uk_stock_details(lines: List[str], stock_name_index: int, result: Dict) -> None:
    """Parse non-UK stock details from the PDF lines."""
    if stock_name_index + 1 >= len(lines):
        return
        
    shares_line = lines[stock_name_index + 1]
    try:
        # First line should have number of shares
        shares_match = re.search(r'([\d,]+)', shares_line)
        if shares_match:
            shares_str = shares_match.group(1).replace(',', '')
            result['num_shares'] = float(shares_str)
            logger.debug(f"Found number of shares: {result['num_shares']}")
        
        # Look for price in original currency in next few lines
        for i in range(stock_name_index + 2, min(stock_name_index + 5, len(lines))):
            price_match = re.search(r'Price \(([A-Z]{3})\)\s*([\d,]+\.?\d*)', lines[i])
            if price_match:
                currency = price_match.group(1)
                price_str = price_match.group(2).replace(',', '')
                result['price'] = float(price_str)
                result['currency'] = currency
                logger.debug(f"Found price in {currency}: {result['price']}")
                
                # Look for exchange rate in next line
                if i + 1 < len(lines):
                    rate_match = re.search(r'Exchange rate\s*([\d,]+\.?\d*)', lines[i + 1])
                    if rate_match:
                        rate_str = rate_match.group(1).replace(',', '')
                        result['exchange_rate'] = float(rate_str)
                        logger.debug(f"Found exchange rate: {result['exchange_rate']}")
                
                # Look for total amount in GBP
                if i + 2 < len(lines):
                    gbp_match = re.search(r'GBP\s*([\d,]+\.?\d*)', lines[i + 2])
                    if gbp_match:
                        amount_str = gbp_match.group(1).replace(',', '')
                        result['total_amount'] = float(amount_str)
                        logger.debug(f"Found total amount in GBP: {result['total_amount']}")
                break
    except ValueError as e:
        logger.warning(f"Failed to parse non-UK format numbers: {e}")

def parse_stock_transaction_pdf(pdf_path):
    """
    Parse a Hargreaves Lansdown stock transaction PDF (purchase or disposal) and extract key information.
    Returns a dictionary with the extracted information.
    """
    try:
        logger.info(f"Processing PDF: {pdf_path}")
        with pdfplumber.open(pdf_path) as pdf:
            # Read all pages
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            
            # Log the full extracted text for debugging
            logger.debug("\n--- FULL EXTRACTED TEXT ---\n")
            logger.debug(text)
            logger.debug("\n--- END OF EXTRACTED TEXT ---\n")
            
            # Split text into lines for easier parsing
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            # Determine if this is a purchase or disposal
            is_disposal = any('**SOLD**' in line for line in lines)
            logger.debug(f"Transaction type: {'disposal' if is_disposal else 'purchase'}")
            
            result = {
                'transaction_type': 'disposal' if is_disposal else 'purchase',
                'stock_name': None,
                'ticker': None,
                'isin': None,
                'currency': None,
                'transaction_date': None,
                'num_shares': None,
                'price': None,
                'total_amount': None,
                'exchange_rate': None,
                'price_in_pence': None,
                'dealing_charge': None,
                'fx_charge': None,
                'total_charges': None,
                'settlement_date': None,
                'stock_code_in_pdf': False  # Track if STOCK CODE was present in PDF
            }
            
            # Extract transaction date (first DD/MM/YYYY found)
            for line in lines:
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                if date_match:
                    try:
                        result['transaction_date'] = datetime.strptime(date_match.group(1), '%d/%m/%Y')
                        logger.debug(f"Found transaction date: {result['transaction_date']}")
                        break
                    except ValueError as e:
                        logger.warning(f"Failed to parse transaction date: {e}")
            
            # Extract ticker and ISIN line
            isin_ticker_line = None
            for i, line in enumerate(lines):
                # Handle case where ticker is on same line as ISIN
                if re.search(r'[A-Z]{2}[A-Z0-9]{10}\s+STOCK CODE:\s*(\w+)', line):
                    isin_ticker_line = i
                    # Extract ISIN and ticker
                    isin_match = re.search(r'([A-Z]{2}[A-Z0-9]{10})', line)
                    ticker_match = re.search(r'STOCK CODE:\s*(\w+)', line)
                    if isin_match and ticker_match:
                        isin = isin_match.group(1)
                        result['isin'] = isin
                        result['ticker'] = ticker_match.group(1)
                        result['stock_code_in_pdf'] = True  # STOCK CODE was present in PDF
                        # If the ticker is in the STOCK_RENAME_MAP, rename it
                        if result['ticker'] in STOCK_RENAME_MAP:
                            result['ticker'] = STOCK_RENAME_MAP[result['ticker']]
                            logger.debug(f"Found stock name in STOCK_RENAME_MAP: {result['ticker']}")
                        # Add exchange suffix based on ISIN and ticker
                        suffix = get_exchange_suffix(isin, result['ticker'])
                        result['ticker'] = f"{result['ticker']}{suffix}"
                        logger.debug(f"Found ISIN: {isin}, ticker: {result['ticker']} (added suffix: {suffix})")
                    break
                # Handle case where ISIN is on its own line followed by ticker
                elif re.search(r'[A-Z]{2}[A-Z0-9]{10}$', line) and i + 1 < len(lines):
                    isin_ticker_line = i
                    # Extract ISIN
                    isin_match = re.search(r'([A-Z]{2}[A-Z0-9]{10})', line)
                    if isin_match:
                        isin = isin_match.group(1)
                        result['isin'] = isin
                        # Look for ticker in next line
                        next_line = lines[i + 1].strip()
                        #if next_line:
                        #    result['ticker'] = next_line
                        #    # Add exchange suffix based on ISIN and ticker
                        #    suffix = get_exchange_suffix(isin, result['ticker'])
                        #    result['ticker'] = f"{result['ticker']}{suffix}"
                        #    logger.debug(f"Found ISIN: {isin}, ticker: {result['ticker']} (added suffix: {suffix})")
                    break
            
            # Extract stock name (line after ISIN/ticker line)
            if isin_ticker_line is not None and isin_ticker_line + 1 < len(lines):
                result['stock_name'] = lines[isin_ticker_line + 1]
                logger.debug(f"Found stock name: {result['stock_name']}")
                
                # If we couldn't find the ticker in the PDF, try to get it from the mapping
                if not result['ticker'] and result['stock_name'] in TICKER_MAPPING:
                    result['ticker'] = TICKER_MAPPING[result['stock_name']]
                    logger.debug(f"Found ticker from mapping: {result['ticker']}")
            else:
                # If we couldn't find the stock name after ISIN/ticker line, look for it after any line containing a US ISIN
                for i, line in enumerate(lines):
                    if re.search(r'[A-Z]{2}[A-Z0-9]{10}', line) and i + 1 < len(lines):
                        result['stock_name'] = lines[i + 1]
                        logger.debug(f"Found stock name after ISIN: {result['stock_name']}")
                        # If we couldn't find the ticker in the PDF, try to get it from the mapping
                        if not result['ticker'] and result['stock_name'] in TICKER_MAPPING:
                            result['ticker'] = TICKER_MAPPING[result['stock_name']]
                            logger.debug(f"Found ticker from mapping: {result['ticker']}")
                        break
            
            # Extract number of shares and price information based on country
            if result['stock_name'] and result['isin']:
                stock_name_index = lines.index(result['stock_name'])
                country_code = result['isin'][:2].upper()
                
                if country_code in ['GB', 'LU']:
                    parse_uk_stock_details(lines, stock_name_index, result)
                elif country_code == 'IE':
                    # Hack for IE: try both UK and non-UK parsing, pick the one that works
                    uk_result = {}
                    non_uk_result = {}
                    
                    parse_uk_stock_details(lines, stock_name_index, uk_result)
                    parse_non_uk_stock_details(lines, stock_name_index, non_uk_result)
                    
                    # Pick the result that has price information
                    if uk_result.get('price') is not None:
                        logger.debug(f"Using UK parsing result for IE stock: {uk_result}")
                        result.update(uk_result)
                    elif non_uk_result.get('price') is not None:
                        logger.debug(f"Using non-UK parsing result for IE stock: {non_uk_result}")
                        result.update(non_uk_result)
                    else:
                        logger.warning(f"Neither UK nor non-UK parsing worked for IE stock. UK result: {uk_result}, Non-UK result: {non_uk_result}")
                else:
                    parse_non_uk_stock_details(lines, stock_name_index, result)
            
            # Extract dealing charge
            for line in lines:
                dealing_match = re.search(r'Dealing charge\s*([\d.]+)', line)
                if dealing_match:
                    try:
                        result['dealing_charge'] = float(dealing_match.group(1))
                        logger.debug(f"Found dealing charge: {result['dealing_charge']}")
                    except ValueError as e:
                        logger.warning(f"Failed to parse dealing charge: {e}")
                
                fx_match = re.search(r'FX Charge\s*([\d.]+)', line)
                if fx_match:
                    try:
                        result['fx_charge'] = float(fx_match.group(1))
                        logger.debug(f"Found FX charge: {result['fx_charge']}")
                    except ValueError as e:
                        logger.warning(f"Failed to parse FX charge: {e}")
                
                total_charges_match = re.search(r'Total Charges\s*([\d.]+)', line)
                if total_charges_match:
                    try:
                        result['total_charges'] = float(total_charges_match.group(1))
                        logger.debug(f"Found total charges: {result['total_charges']}")
                    except ValueError as e:
                        logger.warning(f"Failed to parse total charges: {e}")
                
                # Look for settlement date
                settlement_match = re.search(r'Settlement Date:\s*(\d{2}/\d{2}/\d{4})', line)
                if settlement_match:
                    try:
                        result['settlement_date'] = datetime.strptime(settlement_match.group(1), '%d/%m/%Y').strftime('%Y-%m-%d')
                        logger.debug(f"Found settlement date: {result['settlement_date']}")
                    except ValueError as e:
                        logger.warning(f"Failed to parse settlement date: {e}")
            
            logger.info(f"Successfully parsed PDF: {pdf_path}")
            return result
            
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {str(e)}")
        return None

def parse_subdivision_pdf(pdf_path: str) -> Optional[Dict]:
    """
    Parse a stock subdivision PDF to extract the stock name and share numbers.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing:
        - stock_name: Name of the stock
        - old_shares: Number of shares before subdivision
        - new_shares: Number of shares after subdivision
    """
    try:
        logger.info(f"Processing subdivision PDF: {pdf_path}")
        
        # Extract text from PDF using pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            
            # Log the full extracted text for debugging
            logger.debug("\n--- FULL EXTRACTED TEXT ---\n")
            logger.debug(text)
            logger.debug("\n--- END OF EXTRACTED TEXT ---\n")
            
        if not text:
            logger.error(f"Could not extract text from {pdf_path}")
            return None
            
        # Look for the specific patterns in the text
        original_pattern = r"Original holding of (.*?) shares: (\d+) shares"
        new_pattern = r"New (.*?) shares you have received \(in place of your original holding\): (\d+) shares"
        
        original_match = re.search(original_pattern, text)
        new_match = re.search(new_pattern, text)
        
        if original_match and new_match:
            stock_name = original_match.group(1).strip()
            old_shares = int(original_match.group(2))
            new_shares = int(new_match.group(2))
            
            # Verify stock names match
            if stock_name != new_match.group(1).strip():
                logger.warning(f"Stock name mismatch in subdivision PDF: {stock_name} vs {new_match.group(1).strip()}")
            
            # Extract transaction date - try multiple patterns
            transaction_date = None
            
            # Pattern 1: "was updated on 4 April 2025" (account update date - preferred)
            date_pattern1 = r"was updated on (\d+ \w+ \d{4})"
            date_match1 = re.search(date_pattern1, text)
            if date_match1:
                try:
                    transaction_date = datetime.strptime(date_match1.group(1), '%d %B %Y')
                    logger.debug(f"Found account update date: {transaction_date.strftime('%Y-%m-%d')}")
                except ValueError:
                    pass
            
            # Pattern 2: "Subdivision DD MMM YYYY" in header (letter date - fallback)
            if not transaction_date:
                date_pattern2 = r"Subdivision (\d+ \w+ \d{4})"
                date_match2 = re.search(date_pattern2, text)
                if date_match2:
                    try:
                        transaction_date = datetime.strptime(date_match2.group(1), '%d %b %Y')
                        logger.debug(f"Found subdivision letter date: {transaction_date.strftime('%Y-%m-%d')}")
                    except ValueError:
                        pass
            
            if not transaction_date:
                logger.warning(f"Could not extract transaction date from subdivision PDF: {pdf_path}")
            
            logger.info(f"Found share split for {stock_name}: {old_shares} -> {new_shares}" + 
                       (f" on {transaction_date.strftime('%Y-%m-%d')}" if transaction_date else ""))
            
            result = {
                'stock_name': stock_name,
                'old_shares': old_shares,
                'new_shares': new_shares
            }
            if transaction_date:
                result['transaction_date'] = transaction_date
            
            return result
        
        logger.error(f"Could not find share split information in {pdf_path}")
        logger.debug("Text content that was searched:")
        logger.debug(text)
        return None
        
    except Exception as e:
        logger.error(f"Error parsing subdivision PDF {pdf_path}: {str(e)}")
        logger.exception("Full traceback:")
        return None

def parse_conversion_pdf(pdf_path: str) -> Optional[Dict]:
    """
    Parse a unit class conversion PDF to extract the fund name and unit numbers.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing:
        - stock_name: Name of the fund
        - old_shares: Number of units before conversion
        - new_shares: Number of units after conversion
    """
    try:
        logger.info(f"Processing conversion PDF: {pdf_path}")
        
        # Extract text from PDF using pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            
            # Log the full extracted text for debugging
            logger.debug("\n--- FULL EXTRACTED TEXT ---\n")
            logger.debug(text)
            logger.debug("\n--- END OF EXTRACTED TEXT ---\n")
            
        if not text:
            logger.error(f"Could not extract text from {pdf_path}")
            return None
            
        # Look for the specific patterns in the text
        # Pattern for original units: Handle both formats
        # JP Morgan: "Number of JPMorgan Emerging MarketsClass B - Accumulation (GBP) units 472.701 units originally held:"
        # Rathbone: "Number of Rathbone Ethical BondClass I - Accumulation (GBP) units originally 16241.020 units held:"
        original_pattern = r"Number of (.*?) units.*?(?:originally )?([\d,]+\.?\d*) units.*?held"
        # Pattern for new units: Handle both formats  
        # JP Morgan: "Number of new JPMorgan Emerging MarketsClass C - Accumulation (GBP) 161.87 units units credited"
        # Rathbone: "Number of new Rathbone Ethical BondClass S - Accumulation (GBP) units 32790.400 units credited"
        new_pattern = r"Number of new (.*?) ([\d,]+\.?\d*) units.*?credited"
        
        original_match = re.search(original_pattern, text, re.DOTALL)
        new_match = re.search(new_pattern, text, re.DOTALL)
        
        if original_match and new_match:
            stock_name = original_match.group(1).strip()
            old_shares = float(original_match.group(2).replace(',', ''))
            new_shares = float(new_match.group(2).replace(',', ''))
            
            # For conversions, the fund names might be different (different classes)
            # Extract the base fund name (before the class specification)
            base_fund_name = stock_name.split('Class')[0].strip() if 'Class' in stock_name else stock_name
            new_base_fund_name = new_match.group(1).strip().split('Class')[0].strip() if 'Class' in new_match.group(1).strip() else new_match.group(1).strip()
            
            # Verify base fund names match (they should be the same fund, different classes)
            if base_fund_name != new_base_fund_name:
                logger.warning(f"Base fund name mismatch in conversion PDF: {base_fund_name} vs {new_base_fund_name}")
            
            # Extract transaction date from the text
            # Look for patterns like "updated on 20 March 2025" or similar date patterns
            transaction_date = None
            date_patterns = [
                r'updated on (\d{1,2}) (\w+) (\d{4})',
                r'(\d{1,2}) (\w+) (\d{4})',
                r'(\d{1,2})/(\d{1,2})/(\d{4})',
                r'(\d{4})-(\d{1,2})-(\d{1,2})'
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, text, re.IGNORECASE)
                if date_match:
                    try:
                        if 'updated on' in pattern:
                            # Handle "updated on 20 March 2025" format
                            day, month_name, year = date_match.groups()
                            month_map = {
                                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                                'september': 9, 'october': 10, 'november': 11, 'december': 12
                            }
                            month = month_map.get(month_name.lower())
                            if month:
                                transaction_date = datetime(int(year), month, int(day))
                                break
                        elif '/' in pattern:
                            # Handle DD/MM/YYYY format
                            day, month, year = date_match.groups()
                            transaction_date = datetime(int(year), int(month), int(day))
                            break
                        elif '-' in pattern:
                            # Handle YYYY-MM-DD format
                            year, month, day = date_match.groups()
                            transaction_date = datetime(int(year), int(month), int(day))
                            break
                    except (ValueError, TypeError):
                        continue
            
            logger.info(f"Found unit conversion for {base_fund_name}: {old_shares} -> {new_shares} on {transaction_date}")
            
            result = {
                'stock_name': base_fund_name,  # Use the base fund name
                'old_shares': old_shares,
                'new_shares': new_shares
            }
            
            if transaction_date:
                result['transaction_date'] = transaction_date
            
            return result
        
        logger.error(f"Could not find conversion information in {pdf_path}")
        logger.debug("Text content that was searched:")
        logger.debug(text)
        return None
        
    except Exception as e:
        logger.error(f"Error parsing conversion PDF {pdf_path}: {str(e)}")
        logger.exception("Full traceback:")
        return None

def extract_stock_name(filename: str) -> Optional[str]:
    """Extract stock name from filename."""
    # Remove file extension and common prefixes/suffixes
    name = os.path.splitext(filename)[0]
    name = name.replace('BOUGHT', '').replace('subdivision', '').replace('conversion', '').strip()
    # Remove any remaining special characters
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    return name.strip() if name else None


def parse_merger_pdf(pdf_path: str) -> Optional[Dict]:
    """
    Parse a merger PDF to extract the stock name, number of shares, and cash proceeds.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing:
        - stock_name: Name of the stock
        - num_shares: Number of shares
        - total_amount: Cash proceeds received
        - transaction_date: Date of the merger
    """
    try:
        logger.info(f"Processing merger PDF: {pdf_path}")
        
        # Extract text from PDF using pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        logger.debug(f"\n--- FULL EXTRACTED TEXT ---\n{text}\n--- END OF EXTRACTED TEXT ---\n")
        
        lines = text.split('\n')
        result = {}
        
        # Extract stock name from the header (e.g., "Everbridge Inc - Merger 18 Jul 2024")
        for line in lines:
            if ' - Merger ' in line:
                # Extract stock name (everything before " - Merger")
                stock_name = line.split(' - Merger')[0].strip()
                result['stock_name'] = stock_name
                
                # Extract date (everything after "Merger ")
                date_part = line.split(' - Merger ')[1].strip()
                try:
                    # Parse date like "18 Jul 2024"
                    from datetime import datetime
                    transaction_date = datetime.strptime(date_part, '%d %b %Y')
                    result['transaction_date'] = transaction_date
                except ValueError:
                    logger.warning(f"Could not parse date: {date_part}")
                break
        
        # Extract number of shares and cash proceeds
        for i, line in enumerate(lines):
            # Look for lines like "Original holding of Everbridge Inc shares, now removed from your account: 77 shares"
            if 'shares, now removed from your account:' in line:
                # Extract number of shares
                parts = line.split(':')
                if len(parts) > 1:
                    shares_part = parts[1].strip()
                    # Extract number from "77 shares"
                    shares_match = re.search(r'(\d+)', shares_part)
                    if shares_match:
                        result['num_shares'] = int(shares_match.group(1))
            
            # Look for lines like "Resulting proceeds credited to your Stocks & Shares ISA: £ 2,081.20"
            elif 'Resulting proceeds credited to your Stocks & Shares ISA:' in line:
                # Extract cash amount
                parts = line.split(':')
                if len(parts) > 1:
                    amount_part = parts[1].strip()
                    # Extract amount from "£ 2,081.20"
                    amount_match = re.search(r'£\s*([\d,]+\.?\d*)', amount_part)
                    if amount_match:
                        # Remove commas and convert to float
                        amount_str = amount_match.group(1).replace(',', '')
                        result['total_amount'] = float(amount_str)
        
        # Validate that we found the required information
        if 'stock_name' not in result:
            logger.warning(f"Could not extract stock name from merger PDF: {pdf_path}")
            return None
        
        if 'num_shares' not in result:
            logger.warning(f"Could not extract number of shares from merger PDF: {pdf_path}")
            return None
        
        if 'total_amount' not in result:
            logger.warning(f"Could not extract cash proceeds from merger PDF: {pdf_path}")
            return None
        
        logger.info(f"Successfully parsed merger PDF: {pdf_path}")
        logger.info(f"  Stock: {result['stock_name']}")
        logger.info(f"  Shares: {result['num_shares']}")
        logger.info(f"  Proceeds: £{result['total_amount']:.2f}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error parsing merger PDF {pdf_path}: {str(e)}")
        return None

