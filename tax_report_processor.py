"""Tax report processing.

This module handles tax year reporting, including calculation of
capital gains and losses from stock sales.
"""

from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from logger import logger
from portfolio_review import PortfolioReview
import transaction_processor


def calculate_tax_pnl(ticker: str, sell_transaction, all_transactions: List,
                     tax_year_start: datetime) -> Optional[Dict]:
    """Calculate P&L for a sell transaction using average cost basis.

    Args:
        ticker: Stock ticker
        sell_transaction: The SELL transaction
        all_transactions: All transactions for this stock
        tax_year_start: Start of tax year

    Returns:
        Dictionary with P&L data or None if calculation fails
    """
    logger.debug(f"Calculating tax P&L for {ticker} sell on {sell_transaction.date}")

    # Calculate pool state immediately before this sell (exclude the sell itself so
    # fully-sold positions don't produce units_held=0 and drop from the report)
    pre_sell_transactions = [t for t in all_transactions if t is not sell_transaction]
    results = transaction_processor.calculate_transactions_through_date(
        pre_sell_transactions,
        sell_transaction.date,
        include_investment_threshold=False
    )

    # Extract the Section 104 pool state just before the sell
    pool_units = results['units_held']
    pool_cost = results['pool_cost_basis']

    logger.debug(f"Tax P&L calculation for {ticker}:")
    logger.debug(f"  Pool units before sell: {pool_units}")
    logger.debug(f"  Pool cost basis before sell: £{pool_cost:.2f}")

    if pool_units <= 0:
        logger.warning(f"No units held for {ticker} before sell date")
        return None

    # Calculate average price from the current Section 104 pool
    average_price = pool_cost / pool_units

    # Calculate P&L
    units_sold = abs(sell_transaction.quantity)  # Ensure positive
    amount_received = sell_transaction.total_amount
    cost_basis = average_price * units_sold
    pnl = amount_received - cost_basis

    logger.debug(f"  Average price per unit: £{average_price:.2f}")
    logger.debug(f"  SELL transaction: {units_sold} units for £{amount_received:.2f}")
    logger.debug(f"  Cost basis: {units_sold} units @ £{average_price:.2f} = £{cost_basis:.2f}")
    logger.debug(f"  P&L calculation: £{amount_received:.2f} - £{cost_basis:.2f} = £{pnl:.2f}")

    return {
        'pool_cost_per_unit': average_price,
        'allowable_cost': cost_basis,
        'pnl': pnl
    }


def process_tax_report(portfolio_review: PortfolioReview, tax_year_start: datetime,
                       tax_year_end: datetime) -> Dict[str, pd.DataFrame]:
    """Process tax report for a specific tax year.

    Args:
        portfolio_review: Portfolio review instance
        tax_year_start: Start of tax year (6 April)
        tax_year_end: End of tax year (5 April)

    Returns:
        Dictionary with 'summary' and 'transactions' DataFrames
    """
    logger.info(f"Processing tax report for tax year {tax_year_start.date()} to {tax_year_end.date()}")

    # Get all tickers from taxable accounts only
    all_ticker_category_pairs = portfolio_review.get_all_tickers()
    taxable_tickers = []

    for ticker, category in all_ticker_category_pairs:
        if category == 'taxable':
            taxable_tickers.append((ticker, category))

    logger.info(f"Found {len(taxable_tickers)} taxable stocks for tax reporting")

    # Process each stock to find sell transactions in tax year
    tax_transactions = []
    in_scope_tickers = []  # (ticker, category) pairs that had sells in the tax year

    for ticker, category in taxable_tickers:
        logger.debug(f"Processing tax report for {ticker} in {category}")
        # Skip bed-and-ISA processing for tax reporting to get original transaction data
        transactions = portfolio_review.get_transaction_history(ticker, category, skip_bed_and_isa=True)
        logger.debug(f"Tax report: Found {len(transactions)} raw transactions for {ticker} (bed-and-ISA processing skipped)")

        # Find sell transactions in tax year
        ticker_had_sell = False
        for txn in transactions:
            if (txn.transaction_type == 'SELL' and
                tax_year_start <= txn.date <= tax_year_end):

                ticker_had_sell = True
                # Calculate P&L for this transaction
                pnl_data = calculate_tax_pnl(ticker, txn, transactions, tax_year_start)

                if pnl_data:
                    tax_transactions.append({
                        'ticker': ticker,
                        'company': portfolio_review.get_stock_name(ticker, category),
                        'transaction_date': txn.date,
                        'units_sold': txn.quantity,
                        'pool_cost_per_unit': pnl_data['pool_cost_per_unit'],
                        'allowable_cost': pnl_data['allowable_cost'],
                        'amount_received': txn.total_amount,
                        'pnl': pnl_data['pnl']
                    })
        if ticker_had_sell:
            in_scope_tickers.append((ticker, category))

    # Create DataFrame
    if tax_transactions:
        df = pd.DataFrame(tax_transactions)
        df = df.sort_values('transaction_date')
    else:
        df = pd.DataFrame(columns=['ticker', 'company', 'transaction_date', 'units_sold',
                                  'pool_cost_per_unit', 'allowable_cost', 'amount_received',
                                  'pnl'])

    logger.info(f"Found {len(tax_transactions)} taxable transactions")

    # Calculate summary data
    if not df.empty:
        total_transactions = len(df)
        total_pnl = df['pnl'].sum()
        net_gains_losses = total_pnl  # Could be positive (gains) or negative (losses)
    else:
        total_transactions = 0
        total_pnl = 0.0
        net_gains_losses = 0.0

    # Create summary DataFrame
    summary_df = pd.DataFrame([{
        'total_transactions': total_transactions,
        'total_pnl': (total_pnl, 'GBP'),
        'net_gains_losses': (net_gains_losses, 'GBP')
    }])

    return {
        'summary': summary_df,
        'transactions': df,
        'in_scope_tickers': in_scope_tickers
    }
