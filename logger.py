import logging
import os
from datetime import datetime
import glob
import re
from pathlib import Path
import warnings

# Suppress specific RuntimeWarnings from numbers_parser about rounding
warnings.filterwarnings('ignore', message='.*rounded to 15 significant digits', category=RuntimeWarning)
warnings.filterwarnings('ignore', message='.*rounded to \d+ significant digits', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning, module='numbers_parser')

def setup_logger(log_level: str = 'INFO') -> logging.Logger:
    """Set up logging configuration with timestamped log files and detailed format.
    
    Args:
        log_level: The logging level to use ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Clean up old log files, keeping only the 3 most recent
    log_files = glob.glob('logs/stock_log_*.log')
    if len(log_files) > 3:
        # Sort by modification time, newest first
        log_files.sort(key=os.path.getmtime, reverse=True)
        # Delete all but the 3 most recent
        for old_file in log_files[3:]:
            try:
                os.remove(old_file)
                # print(f"Removed old log file: {old_file}")
            except Exception as e:
                print(f"Error removing old log file {old_file}: {e}")
    
    # Generate new log filename with timestamp and sequence number
    timestamp = datetime.now().strftime('%y%m%d')
    
    # Find the highest sequence number for today's logs
    today_logs = glob.glob(f'logs/stock_log_{timestamp}_*.log')
    if today_logs:
        # Extract sequence numbers from filenames
        sequence_numbers = []
        for log_file in today_logs:
            match = re.search(r'stock_log_\d{6}_(\d{3})\.log', log_file)
            if match:
                sequence_numbers.append(int(match.group(1)))
        # Get the next sequence number
        sequence = max(sequence_numbers) + 1 if sequence_numbers else 1
    else:
        sequence = 1
        
    log_filename = f'logs/stock_log_{timestamp}_{sequence:03d}.log'
    
    # Get root logger and configure it
    logger = logging.getLogger()
    
    # Remove any existing handlers
    logger.handlers = []
    
    # Set log level for pdfplumber and its submodules to ERROR
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('pdfplumber').setLevel(logging.ERROR)
    logging.getLogger('numbers_parser').setLevel(logging.ERROR)
    logging.getLogger('yfinance').setLevel(logging.ERROR)
    
    # Create formatter with fixed-width fields
    formatter = logging.Formatter('%(asctime)s %(module)-20s %(funcName)-30s %(levelname)-8s %(message)s')
    
    # Configure file handler
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Set log level
    try:
        level = getattr(logging, log_level.upper())
        logger.setLevel(level)
    except (AttributeError, TypeError):
        print(f"Invalid log level: {log_level}. Using INFO level instead.")
        logger.setLevel(logging.INFO)
    
    logger.info(f"Logging initialized. Log file: {log_filename} (Level: {log_level.upper()})")
    return logger

# Export the logger instance
logger = logging.getLogger() 