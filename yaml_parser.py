#!/usr/bin/env python3
"""
Parse YAML transaction files for manual note entry.

Supports hand-crafted transaction notes in YAML format for cases where
original broker notes are missing or unavailable.
"""

import yaml
from typing import Dict, Any, List
from datetime import datetime
from logger import logger


def parse_stock_transaction_yaml(yaml_path: str) -> List[Dict[str, Any]]:
    """Parse a YAML transaction file.
    
    Args:
        yaml_path: Path to YAML file
        
    Returns:
        List of transaction dictionaries (usually one, but supports multiple)
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    logger.info(f"Processing YAML: {yaml_path}")
    
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to parse YAML file {yaml_path}: {e}")
        raise ValueError(f"Invalid YAML file: {e}")
    
    # Handle both single transaction and list of transactions
    if isinstance(data, list):
        transactions = data
    else:
        transactions = [data]
    
    parsed_transactions = []
    
    for txn in transactions:
        transaction_type = txn.get('transaction_type', '').upper()
        
        if transaction_type == 'STOCK_CONVERSION':
            parsed = _parse_stock_conversion(txn, yaml_path)
        elif transaction_type in ['BUY', 'SELL']:
            parsed = _parse_buy_sell(txn, yaml_path)
        elif transaction_type == 'TRANSFER':
            parsed = _parse_transfer(txn, yaml_path)
        else:
            logger.error(f"Unknown transaction_type '{transaction_type}' in {yaml_path}")
            raise ValueError(f"Invalid transaction_type: {transaction_type}")
        
        parsed_transactions.append(parsed)
        logger.info(f"Successfully parsed YAML transaction: {transaction_type} for {txn.get('ticker')}")
    
    return parsed_transactions


def _parse_stock_conversion(data: Dict[str, Any], yaml_path: str) -> Dict[str, Any]:
    """Parse a STOCK_CONVERSION transaction.
    
    Required fields: ticker, date, old_quantity, new_quantity
    Optional fields: new_ticker, new_currency, stock_name, description
    """
    # Validate required fields
    required = ['ticker', 'date', 'old_quantity', 'new_quantity']
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields in {yaml_path}: {missing}")
    
    # Parse date
    date = _parse_date(data['date'], yaml_path)
    
    # Build result matching the format expected by _process_stock_split
    result = {
        'transaction_type': 'conversion',
        'ticker': data['ticker'],
        'stock_name': data.get('stock_name', data['ticker']),
        'transaction_date': date,
        'old_shares': float(data['old_quantity']),  # Field name expected by _process_stock_split
        'new_shares': float(data['new_quantity']),  # Field name expected by _process_stock_split
        'new_ticker': data.get('new_ticker'),  # Optional
        'new_currency': data.get('new_currency'),  # Optional
        'description': data.get('description', 'Manual YAML entry'),
    }
    
    logger.debug(f"Parsed STOCK_CONVERSION: {result['ticker']} {result['old_shares']} -> {result['new_shares']} on {date.strftime('%Y-%m-%d')}")
    
    return result


def _parse_buy_sell(data: Dict[str, Any], yaml_path: str) -> Dict[str, Any]:
    """Parse a BUY or SELL transaction.
    
    Required fields: ticker, date, quantity, price_per_share, total_amount
    Optional fields: stock_name, currency, exchange_rate, dealing_charge, fx_charge, 
                    total_charges, settlement_date, description
    """
    transaction_type = data.get('transaction_type', '').upper()
    
    # Validate required fields
    required = ['ticker', 'date', 'quantity', 'price_per_share', 'total_amount']
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields in {yaml_path}: {missing}")
    
    # Parse date
    date = _parse_date(data['date'], yaml_path)
    
    # Parse optional settlement date
    settlement_date = None
    if 'settlement_date' in data:
        settlement_date = _parse_date(data['settlement_date'], yaml_path)
    
    # Build result matching PDF parser format
    result = {
        'transaction_type': 'purchase' if transaction_type == 'BUY' else 'disposal',
        'ticker': data['ticker'],
        'stock_name': data.get('stock_name', data['ticker']),
        'transaction_date': date,
        'num_shares': float(data['quantity']),
        'price': float(data['price_per_share']),
        'total_amount': float(data['total_amount']),
        'currency': data.get('currency', 'GBP'),
        'exchange_rate': data.get('exchange_rate'),
        'dealing_charge': data.get('dealing_charge'),
        'fx_charge': data.get('fx_charge'),
        'total_charges': data.get('total_charges'),
        'settlement_date': settlement_date,
    }
    
    logger.debug(f"Parsed {transaction_type}: {result['ticker']} {result['num_shares']} @ {result['price']} on {date.strftime('%Y-%m-%d')}")
    
    return result


def _parse_transfer(data: Dict[str, Any], yaml_path: str) -> Dict[str, Any]:
    """Parse a TRANSFER transaction (bed-and-ISA).
    
    Required fields: ticker, date, quantity, total_amount
    Optional fields: stock_name, price_per_share, description
    """
    # Validate required fields
    required = ['ticker', 'date', 'quantity', 'total_amount']
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields in {yaml_path}: {missing}")
    
    # Parse date
    date = _parse_date(data['date'], yaml_path)
    
    # Calculate price if not provided
    quantity = float(data['quantity'])
    total_amount = float(data['total_amount'])
    price = data.get('price_per_share', total_amount / quantity if quantity > 0 else 0)
    
    # Build result - TRANSFER is represented as a special purchase
    result = {
        'transaction_type': 'transfer',
        'ticker': data['ticker'],
        'stock_name': data.get('stock_name', data['ticker']),
        'transaction_date': date,
        'num_shares': quantity,
        'price': float(price),
        'total_amount': total_amount,
        'currency': data.get('currency', 'GBP'),
    }
    
    logger.debug(f"Parsed TRANSFER: {result['ticker']} {result['num_shares']} on {date.strftime('%Y-%m-%d')}")
    
    return result


def _parse_date(date_value: Any, yaml_path: str) -> datetime:
    """Parse a date value from YAML.
    
    Supports:
    - datetime objects (already parsed by YAML)
    - Strings in YYYY-MM-DD or DD/MM/YYYY format
    - date objects
    """
    if isinstance(date_value, datetime):
        return date_value
    elif hasattr(date_value, 'year'):  # date object
        return datetime.combine(date_value, datetime.min.time())
    elif isinstance(date_value, str):
        # Try YYYY-MM-DD format
        try:
            return datetime.strptime(date_value, '%Y-%m-%d')
        except ValueError:
            pass
        
        # Try DD/MM/YYYY format
        try:
            return datetime.strptime(date_value, '%d/%m/%Y')
        except ValueError:
            pass
        
        raise ValueError(f"Invalid date format '{date_value}' in {yaml_path}. Expected YYYY-MM-DD or DD/MM/YYYY")
    else:
        raise ValueError(f"Invalid date type in {yaml_path}: {type(date_value)}")

