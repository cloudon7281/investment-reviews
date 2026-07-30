# Global definitions for reporting on the portfolio

# Format dictionaries for Numbers output
CURRENCY_FORMAT = {'type': 'currency', 'currency': 'GBP', 'decimal_places': 2}
CURRENCY_FORMAT_NO_DECIMALS = {'type': 'currency', 'currency': 'GBP', 'decimal_places': 0}
PERCENTAGE_FORMAT = {'type': 'percentage', 'decimal_places': 1}
DATE_FORMAT = {'type': 'date'}

# Define threshold constants
STOP_LOSS_THRESHOLD = [
    {'threshold': 0.8, 'style': 'red'},
    {'threshold': 0.9, 'style': 'amber'},
    {'threshold': None, 'style': None}
]

STOCKS_PROFIT_TAKING_THRESHOLD = [
    {'threshold': -0.2, 'style': 'red'},
    {'threshold': -0.1, 'style': 'amber'},
    {'threshold': 2.0, 'style': None},
    {'threshold': None, 'style': 'green'}
]

FUNDS_PROFIT_TAKING_THRESHOLD = [
    {'threshold': -0.1, 'style': 'red'},
    {'threshold': 0, 'style': 'amber'},
    {'threshold': None, 'style': None}
]

STOCKS_BETA_THRESHOLD = [
    {'threshold': 1, 'style': 'red'},
    {'threshold': 1.5, 'style': 'amber'},
    {'threshold': None, 'style': None}
]

STOCKS_VOLATILITY_THRESHOLD = [
    {'threshold': 0.25, 'style': 'red'},
    {'threshold': 0.35, 'style': 'amber'},
    {'threshold': None, 'style': None}
]

FUNDS_VOLATILITY_THRESHOLD = [
    {'threshold': 0.2, 'style': None},
    {'threshold': 0.35, 'style': 'amber'},
    {'threshold': None, 'style': 'red'}
]

TIME_HELD_THRESHOLD = [
    {'threshold': 365, 'style': None},
    {'threshold': 730, 'style': 'amber'},
    {'threshold': None, 'style': 'red'}
]

# Define column configurations for each report type
COLUMN_CONFIGS = {
    'full_history': {
        'headers': ['Tag', 'Company', 'Ticker', 'Category', 'Total Invested', 'Total Received', 'Units Held', 'Current Value', 'P&L', 'Unrealized Profit', 'Simple ROI', 'MWRR', 'Current price', '90d High', '% of High', 'Volatility', 'First Transaction', 'Last Transaction'],
        'columns': ['tag', 'stock_name', 'ticker', 'account_type', 'total_invested', 'total_received', 'units_held', 'current_value', 'total_pnl', 'unrealized_profit', 'simple_roi', 'mwrr', 'current_price', 'recent_high', 'current_price_pct_of_high', 'volatility', 'first_transaction_date', 'final_transaction_date'],
        'column_formats': [
            None,  # Tag - text
            None,  # Company - text
            None,  # Ticker - text
            None,  # Category - text
            CURRENCY_FORMAT_NO_DECIMALS,  # Total Invested
            CURRENCY_FORMAT_NO_DECIMALS,  # Total Received
            None,  # Units Held - integer (no special formatting)
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            CURRENCY_FORMAT_NO_DECIMALS,  # Unrealized Profit
            PERCENTAGE_FORMAT,  # Simple ROI
            PERCENTAGE_FORMAT,  # MWRR
            CURRENCY_FORMAT,  # Current price
            CURRENCY_FORMAT,  # 90d High
            PERCENTAGE_FORMAT,  # % of High
            PERCENTAGE_FORMAT,  # Volatility
            DATE_FORMAT,  # First Transaction - date formatting
            DATE_FORMAT,  # Last Transaction - date formatting
        ],
        'column_thresholds': [
            None,  # Tag
            None,  # Company
            None,  # Ticker
            None,  # Category
            None,  # Total Invested
            None,  # Total Received
            None,  # Units Held
            None,  # Current Value
            None,  # P&L
            None,  # Unrealized Profit
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Simple ROI
            STOCKS_PROFIT_TAKING_THRESHOLD,  # MWRR
            None,  # Current price
            None,  # 90d High
            STOP_LOSS_THRESHOLD,  # % of High
            STOCKS_VOLATILITY_THRESHOLD,  # Volatility
            DATE_FORMAT,  # First Transaction - date formatting
            DATE_FORMAT,  # Last Transaction - date formatting
        ]
    },
    'periodic_review_summary': {
        'headers': ['Category', 'Count', 'Start Value', 'Current Value', 'P&L', 'ROI'],
        'columns': ['category', 'count', 'start_value', 'current_value', 'pnl', 'roi'],
        'column_formats': [
            None,  # Category - text
            None,  # Count - integer (no special formatting)
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # ROI
        ],
        'column_thresholds': [
            None,  # Category
            None,  # Count
            None,  # Start Value
            None,  # Current Value
            None,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # ROI
        ]
    },
    'periodic_review_detail': {
        'headers': ['Tag', 'Company', 'Ticker', 'Units Held', 'Start Value', 'Current Value', 'P&L', 'Simple ROI', 'Current Price', '90d High', '% of High', 'Volatility', 'Days Held'],
        'columns': ['tag', 'company_name', 'ticker', 'units_held', 'start_value', 'current_value', 'pnl', 'simple_roi', 'current_price', 'recent_high', 'current_price_pct_of_high', 'volatility', 'period_days'],
        'column_formats': [
            None,  # Tag - text
            None,  # Company - text
            None,  # Ticker - text
            None,  # Units Held - integer (no special formatting)
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # Simple ROI
            CURRENCY_FORMAT,  # Current Price
            CURRENCY_FORMAT,  # 90d High
            PERCENTAGE_FORMAT,  # % of High
            PERCENTAGE_FORMAT,  # Volatility
            None,  # Days Held - integer (no special formatting)
        ],
        'column_thresholds': [
            None,  # Tag
            None,  # Company
            None,  # Ticker
            None,  # Units Held
            None,  # Start Value
            None,  # Current Value
            STOCKS_PROFIT_TAKING_THRESHOLD,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Simple ROI
            None,  # Current Price
            None,  # 90d High
            STOP_LOSS_THRESHOLD,  # % of High
            STOCKS_VOLATILITY_THRESHOLD,  # Volatility
            TIME_HELD_THRESHOLD,  # Days Held
        ]
    },
    'periodic_review_detail_holding': {
        'headers': ['Tag', 'Company', 'Ticker', 'Units Held', 'Start Value', 'Current Value', 'P&L', 'Simple ROI', 'MWRR', 'Current Price', '90d High', '% of High', 'Volatility', 'Days Held', 'Progress to 2x', '# Doublings'],
        'columns': ['tag', 'company_name', 'ticker', 'units_held', 'start_value', 'current_value', 'pnl', 'simple_roi', 'mwrr', 'current_price', 'recent_high', 'current_price_pct_of_high', 'volatility', 'period_days', 'progress_to_doubling', 'doubling_count'],
        'column_formats': [
            None,  # Tag - text
            None,  # Company - text
            None,  # Ticker - text
            None,  # Units Held - integer
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # Simple ROI
            PERCENTAGE_FORMAT,  # MWRR
            CURRENCY_FORMAT,  # Current Price
            CURRENCY_FORMAT,  # 90d High
            PERCENTAGE_FORMAT,  # % of High
            PERCENTAGE_FORMAT,  # Volatility
            None,  # Days Held - integer
            None,  # Progress to 2x - pre-formatted string ("1.7x" or "—")
            None,  # # Doublings - integer
        ],
        'column_thresholds': [
            None,  # Tag
            None,  # Company
            None,  # Ticker
            None,  # Units Held
            None,  # Start Value
            None,  # Current Value
            STOCKS_PROFIT_TAKING_THRESHOLD,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Simple ROI
            STOCKS_PROFIT_TAKING_THRESHOLD,  # MWRR
            None,  # Current Price
            None,  # 90d High
            STOP_LOSS_THRESHOLD,  # % of High
            STOCKS_VOLATILITY_THRESHOLD,  # Volatility
            TIME_HELD_THRESHOLD,  # Days Held
            None,  # Progress to 2x
            None,  # # Doublings
        ]
    },
    'tax_report': {
        'headers': [ "Company", "Ticker", "Disposal Date", "Units Sold", "Pool Cost / Unit", "Allowable Cost", "Proceeds", "Gain / (Loss)"],
        'columns': [ "company", "ticker", "transaction_date", "units_sold", "pool_cost_per_unit", "allowable_cost", "amount_received", "pnl"],
        'column_formats': [
            None,  # Company - text
            None,  # Ticker - text
            DATE_FORMAT,  # Disposal Date - date formatting
            None,  # Units Sold - integer (no special formatting)
            CURRENCY_FORMAT,  # Pool Cost / Unit
            CURRENCY_FORMAT_NO_DECIMALS,  # Allowable Cost
            CURRENCY_FORMAT_NO_DECIMALS,  # Proceeds
            CURRENCY_FORMAT_NO_DECIMALS,  # Gain / (Loss)
        ],
        'column_thresholds': [
            None, None, None, None, None, None, None, None
        ]
    },
    'tax_report_summary': {
        'headers': ['Tax Year', 'Total Taxable Transactions', 'Net Capital Gains/Losses'],
        'columns': ['tax_year', 'total_transactions', 'net_gains_losses'],
        'column_formats': [
            None,  # Tax Year - text
            None,  # Total Taxable Transactions - integer
            CURRENCY_FORMAT_NO_DECIMALS,  # Net Capital Gains/Losses - currency
        ],
        'column_thresholds': [
            None,  # Tax Year
            None,  # Total Taxable Transactions
            None,  # Net Capital Gains/Losses
        ]
    },
    'tag_summary': {
        'headers': ['Tag', 'Total Invested', 'Total Received', 'Current Value', 'Total P&L', 'Unrealized Profit', 'ROI', 'MWRR', 'First Transaction', 'Last Transaction'],
        'columns': ['tag', 'total_invested', 'total_received', 'current_value', 'total_pnl', 'unrealized_profit', 'roi', 'mwrr', 'first_transaction_date', 'final_transaction_date'],
        'column_formats': [
            None,  # Tag - text
            CURRENCY_FORMAT_NO_DECIMALS,  # Total Invested
            CURRENCY_FORMAT_NO_DECIMALS,  # Total Received
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Total P&L
            CURRENCY_FORMAT_NO_DECIMALS,  # Unrealized Profit
            PERCENTAGE_FORMAT,  # ROI
            PERCENTAGE_FORMAT,  # MWRR
            DATE_FORMAT,  # First Transaction - date formatting
            DATE_FORMAT,  # Last Transaction - date formatting
        ],
        'column_thresholds': [
            None,  # Tag
            None,  # Total Invested
            None,  # Total Received
            None,  # Current Value
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Total P&L
            None,  # Unrealized Profit
            STOCKS_PROFIT_TAKING_THRESHOLD,  # ROI
            STOCKS_PROFIT_TAKING_THRESHOLD,  # MWRR
            None,  # First Transaction
            None,  # Last Transaction
        ]
    },
    'annual_review_summary': {
        'headers': ['Group', 'Start Value', 'Bought', 'Sold', 'Current Value', 'P&L', 'MWRR'],
        'columns': ['group', 'start_value', 'bought_since', 'sold_since', 'current_value', 'pnl', 'mwrr'],
        'column_formats': [
            None,  # Group - text
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Bought
            CURRENCY_FORMAT_NO_DECIMALS,  # Sold
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # MWRR
        ],
        'column_thresholds': [
            None,  # Group
            None,  # Start Value
            None,  # Bought
            None,  # Sold
            None,  # Current Value
            None,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # MWRR
        ]
    },
    'periodic_review_benchmark': {
        'headers': ['Tag', 'Ticker', 'Index / ETF', 'Start Value (£1k)', 'Current Value', 'P&L', 'ROI'],
        'columns': ['tag', 'ticker', 'company_name', 'start_value', 'current_value', 'pnl', 'simple_roi'],
        'column_formats': [
            None,                        # Tag - text
            None,                        # Ticker - text
            None,                        # Index / ETF - text
            CURRENCY_FORMAT_NO_DECIMALS, # Start Value
            CURRENCY_FORMAT_NO_DECIMALS, # Current Value
            CURRENCY_FORMAT_NO_DECIMALS, # P&L
            PERCENTAGE_FORMAT,           # ROI
        ],
        'column_thresholds': [
            None,                            # Tag
            None,                            # Ticker
            None,                            # Index / ETF
            None,                            # Start Value
            None,                            # Current Value
            STOCKS_PROFIT_TAKING_THRESHOLD,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # ROI
        ]
    },
    'thesis_summary': {
        'headers': ['Thesis', 'Candidate Basket', 'Held Basket', 'Held vs. Candidates', 'Positive Candidates', 'Total Candidates', 'Breadth'],
        'columns': ['thesis', 'candidate_return', 'held_return', 'held_vs_candidates', 'positive_candidates', 'valid_candidates', 'breadth'],
        'column_formats': [
            None,                # Thesis - text
            PERCENTAGE_FORMAT,   # Candidate Basket
            PERCENTAGE_FORMAT,   # Held Basket
            PERCENTAGE_FORMAT,   # Held vs. Candidates
            None,                # Positive Candidates - integer
            None,                # Total Candidates - integer
            PERCENTAGE_FORMAT,   # Breadth
        ],
        'column_thresholds': [
            None,                            # Thesis
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Candidate Basket
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Held Basket
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Held vs. Candidates
            None,                            # Positive Candidates
            None,                            # Total Candidates
            None,                            # Breadth
        ]
    },
    'thesis_candidate_detail': {
        'headers': ['Thesis', 'Company', 'Ticker', 'Held', 'Start Value (£1k)', 'Current Value', 'P&L', 'Simple ROI', 'Current Price', '90d High', '% of High', 'Volatility'],
        'columns': ['thesis', 'company_name', 'ticker', 'held', 'start_value', 'current_value', 'pnl', 'simple_roi', 'current_price', 'recent_high', 'current_price_pct_of_high', 'volatility'],
        'column_formats': [
            None,  # Thesis - text
            None,  # Company - text
            None,  # Ticker - text
            None,  # Held - text
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # Simple ROI
            CURRENCY_FORMAT,  # Current Price
            CURRENCY_FORMAT,  # 90d High
            PERCENTAGE_FORMAT,  # % of High
            PERCENTAGE_FORMAT,  # Volatility
        ],
        'column_thresholds': [
            None,  # Thesis
            None,  # Company
            None,  # Ticker
            None,  # Held
            None,  # Start Value
            None,  # Current Value
            STOCKS_PROFIT_TAKING_THRESHOLD,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # Simple ROI
            None,  # Current Price
            None,  # 90d High
            STOP_LOSS_THRESHOLD,  # % of High
            STOCKS_VOLATILITY_THRESHOLD,  # Volatility
        ]
    },
    'list_trades': {
        'headers': ['Company', 'Ticker', 'Date', 'Type', 'Units', 'Value (£)'],
        'columns': ['stock_name', 'ticker', 'date', 'transaction_type', 'quantity', 'value_gbp'],
        'column_formats': [
            None,          # Company - text
            None,          # Ticker - text
            DATE_FORMAT,   # Date
            None,          # Type - text
            None,          # Units - pre-formatted string
            CURRENCY_FORMAT_NO_DECIMALS,  # Value (£)
        ],
        'column_thresholds': [
            None,  # Company
            None,  # Ticker
            None,  # Date
            None,  # Type
            None,  # Units
            None,  # Value (£)
        ]
    },
    'annual_review_detail': {
        'headers': ['Tag', 'Company', 'Ticker', 'Category', 'First Txn', 'Start Price', 'Start Value', 'Bought', 'Sold', 'Current Value', 'P&L', 'MWRR', 'Current Price', '90d High', '% of High', 'Volatility'],
        'columns': ['tag', 'stock_name', 'ticker', 'account_type', 'first_transaction_date', 'start_price', 'start_value', 'bought_since', 'sold_since', 'current_value', 'pnl', 'mwrr', 'current_price', 'recent_high', 'current_price_pct_of_high', 'volatility'],
        'column_formats': [
            None,  # Tag - text
            None,  # Company - text
            None,  # Ticker - text
            None,  # Category - text
            DATE_FORMAT,  # First Txn
            CURRENCY_FORMAT,  # Start Price
            CURRENCY_FORMAT_NO_DECIMALS,  # Start Value
            CURRENCY_FORMAT_NO_DECIMALS,  # Bought
            CURRENCY_FORMAT_NO_DECIMALS,  # Sold
            CURRENCY_FORMAT_NO_DECIMALS,  # Current Value
            CURRENCY_FORMAT_NO_DECIMALS,  # P&L
            PERCENTAGE_FORMAT,  # MWRR
            CURRENCY_FORMAT,  # Current Price
            CURRENCY_FORMAT,  # 90d High
            PERCENTAGE_FORMAT,  # % of High
            PERCENTAGE_FORMAT,  # Volatility
        ],
        'column_thresholds': [
            None,  # Tag
            None,  # Company
            None,  # Ticker
            None,  # Category
            None,  # First Txn
            None,  # Start Price
            None,  # Start Value
            None,  # Bought
            None,  # Sold
            None,  # Current Value
            None,  # P&L
            STOCKS_PROFIT_TAKING_THRESHOLD,  # MWRR
            None,  # Current Price
            None,  # 90d High
            STOP_LOSS_THRESHOLD,  # % of High
            STOCKS_VOLATILITY_THRESHOLD,  # Volatility
        ]
    }
}
