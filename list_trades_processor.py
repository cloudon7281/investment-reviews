"""List-trades processor.

Filters all parsed transactions to those within an optional date range and,
optionally, to a set of stocks; flattens them across all stocks and categories
and returns a single sorted DataFrame ready for display.

No financial calculations or market data fetching are performed here —
all required data is already present in the parsed StockTransaction objects.
"""

from datetime import datetime
from typing import List, Optional
import pandas as pd
from portfolio_review import PortfolioReview
from logger import logger

_TYPE_DISPLAY = {
    'BUY': 'Buy',
    'SELL': 'Sell',
    'TRANSFER': 'Transfer',
    'STOCK_CONVERSION': 'Conversion',
}

_ACCOUNT_DISPLAY = {
    'isa': 'ISA',
    'taxable': 'Taxable',
    'pension': 'Pension',
}


def _matches_stocks(stock_name: str, ticker: str, stocks: List[str]) -> bool:
    """True if any term is a case-insensitive substring of the stock's name or ticker."""
    name, ticker = stock_name.lower(), ticker.lower()
    return any(term.lower() in name or term.lower() in ticker for term in stocks)


def process_list_trades(portfolio_review: PortfolioReview,
                        start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None,
                        stocks: Optional[List[str]] = None) -> pd.DataFrame:
    """Return the transactions in scope as a sorted DataFrame.

    Args:
        portfolio_review: Parsed portfolio data.
        start_date: Inclusive lower bound, or None for no lower bound.
        end_date: Inclusive upper bound, or None for no upper bound.
        stocks: Terms to match against each stock's name or ticker, ignoring
            case; a stock is included if any term matches.  None includes all.

    Returns:
        DataFrame with columns: stock_name, ticker, account, date,
        transaction_type, quantity (str), value_gbp (float or None).
        Sorted by date, or by stock name then date when stocks is given.
        Empty DataFrame if no trades are in scope.
    """
    rows = []

    for category, stock_notes in portfolio_review.stock_notes.items():
        for stock_note in stock_notes:
            if stocks and not _matches_stocks(stock_note.stock_name, stock_note.ticker, stocks):
                continue

            for txn in stock_note.transactions:
                if start_date and txn.date < start_date:
                    continue
                if end_date and txn.date > end_date:
                    continue

                if txn.transaction_type == 'STOCK_CONVERSION':
                    quantity_str = f"{txn.quantity} → {txn.new_quantity}"
                    value = None
                else:
                    quantity_str = str(txn.quantity)
                    value = txn.total_amount

                rows.append({
                    'stock_name': stock_note.stock_name,
                    'ticker': stock_note.ticker,
                    'account': _ACCOUNT_DISPLAY.get(category, category),
                    'date': txn.date,
                    'transaction_type': _TYPE_DISPLAY.get(txn.transaction_type, txn.transaction_type),
                    'quantity': quantity_str,
                    'value_gbp': value,
                })

    if not rows:
        logger.info("No trades found in scope")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if stocks:
        # Group each stock's trades together.  Ticker breaks a tie between two stocks
        # that share a name; the stable sort keeps same-day trades in parse order.
        df['sort_name'] = df['stock_name'].str.lower()
        df = df.sort_values(['sort_name', 'ticker', 'date'], kind='stable').drop(columns='sort_name')
    else:
        df = df.sort_values('date')
    df = df.reset_index(drop=True)
    logger.info(f"Found {len(df)} trades in scope")
    return df
