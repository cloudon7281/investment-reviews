"""List-trades processor.

Filters all parsed transactions to those on or after a start date,
flattens them across all stocks and categories, and returns a single
chronologically-sorted DataFrame ready for display.

No financial calculations or market data fetching are performed here —
all required data is already present in the parsed StockTransaction objects.
"""

from datetime import datetime
import pandas as pd
from portfolio_review import PortfolioReview
from logger import logger

_TYPE_DISPLAY = {
    'BUY': 'Buy',
    'SELL': 'Sell',
    'TRANSFER': 'Transfer',
    'STOCK_CONVERSION': 'Conversion',
}


def process_list_trades(portfolio_review: PortfolioReview, start_date: datetime) -> pd.DataFrame:
    """Return all transactions on or after start_date as a sorted DataFrame.

    Args:
        portfolio_review: Parsed portfolio data.
        start_date: Inclusive lower bound; transactions before this date are excluded.

    Returns:
        DataFrame with columns: stock_name, ticker, date, transaction_type,
        quantity (str), value_gbp (float or None).
        Sorted ascending by date.  Empty DataFrame if no trades are in scope.
    """
    rows = []

    for category, stock_notes in portfolio_review.stock_notes.items():
        for stock_note in stock_notes:
            for txn in stock_note.transactions:
                if txn.date < start_date:
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
                    'date': txn.date,
                    'transaction_type': _TYPE_DISPLAY.get(txn.transaction_type, txn.transaction_type),
                    'quantity': quantity_str,
                    'value_gbp': value,
                })

    if not rows:
        logger.info(f"No trades found on or after {start_date.strftime('%Y-%m-%d')}")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values('date').reset_index(drop=True)
    logger.info(f"Found {len(df)} trades on or after {start_date.strftime('%Y-%m-%d')}")
    return df
