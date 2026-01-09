#!/bin/bash
# Setup script for Ubuntu server deployment
# Run this on the Ubuntu server after cloning the repository

set -e  # Exit on error

echo "=================================================="
echo "Portfolio Analysis - Ubuntu Server Setup"
echo "=================================================="
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
REQUIRED_VERSION="3.9"

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"; then
    echo "ERROR: Python 3.9 or later required. Found: Python $PYTHON_VERSION"
    exit 1
fi
echo "Found Python $PYTHON_VERSION ✓"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create directory structure
echo ""
echo "Creating directory structure..."
mkdir -p history
mkdir -p credentials
mkdir -p logs/daily_updates
mkdir -p scratch

# Set up virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Virtual environment created ✓"
else
    echo "Virtual environment already exists ✓"
fi

# Activate and install dependencies
echo ""
echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install -r requirements_server.txt --quiet
echo "Dependencies installed ✓"

# Create config template if it doesn't exist
if [ ! -f "config.yaml" ]; then
    echo ""
    echo "Creating config.yaml template..."
    cat > config.yaml << 'EOF'
google_sheets:
  credentials_path: ~/investment_reviews/credentials/google_sheets_service_account.json
  spreadsheet_id: REPLACE_WITH_YOUR_SPREADSHEET_ID
  worksheet_name: "Daily Values"

portfolio:
  base_dir: ~/investment_reviews/history
  temp_output: /tmp/daily_portfolio_report.numbers

logging:
  log_dir: ~/investment_reviews/logs/daily_updates
  retention_days: 30

notifications:
  email_on_error: ""  # Optional: your@email.com
EOF
    echo "Created config.yaml ✓"
    echo "⚠️  REMEMBER: Edit config.yaml with your Google Sheet ID!"
else
    echo "config.yaml already exists ✓"
fi

# Set proper permissions
echo ""
echo "Setting permissions..."
chmod 700 credentials 2>/dev/null || true
chmod 755 setup_ubuntu.sh
chmod 755 update_google_sheet.py 2>/dev/null || true
chmod 755 migrate_old_sheet.py 2>/dev/null || true

echo ""
echo "=================================================="
echo "✓ Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Place Google service account JSON in:"
echo "   ~/investment_reviews/credentials/google_sheets_service_account.json"
echo ""
echo "2. Edit config.yaml with your Google Sheet ID:"
echo "   nano config.yaml"
echo ""
echo "3. Set up data sync from Mac:"
echo "   See DEPLOYMENT.md for rsync setup"
echo ""
echo "4. Test the installation:"
echo "   source .venv/bin/activate"
echo "   python3 update_google_sheet.py --dry-run"
echo ""
