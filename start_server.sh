#!/bin/bash
# Production API server startup script with proper error handling

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Rubix Token CID API Server ===${NC}\n"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
    echo -e "${GREEN}Virtual environment created.${NC}"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Check and install dependencies
echo "Checking dependencies..."
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip install -q -r requirements.txt
fi

# Check if Gunicorn is installed
if ! python -c "import gunicorn" 2>/dev/null; then
    echo -e "${YELLOW}Installing Gunicorn...${NC}"
    pip install -q gunicorn
fi

# Check if database exists
if [ ! -f "cid_tokens.db" ]; then
    echo -e "${YELLOW}Warning: cid_tokens.db not found.${NC}"
    echo -e "${YELLOW}You may need to run build_cid_cache.py first to populate the database.${NC}"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if config file exists
if [ ! -f "ipfs_config.txt" ]; then
    echo -e "${YELLOW}Warning: ipfs_config.txt not found.${NC}"
    echo -e "${YELLOW}Creating default config file...${NC}"
    cat > ipfs_config.txt << EOF
# IPFS Configuration
# Set the IPFS_PATH to your .ipfs directory
# Example: /home/cherryrubix/wallets/node002/node002/.ipfs

IPFS_PATH=
EOF
    echo -e "${GREEN}Created ipfs_config.txt. Please edit it with your IPFS_PATH.${NC}"
    exit 1
fi

# Get number of workers
WORKERS=$(python -c 'import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)')

# Get port from environment or use default
PORT=${PORT:-5000}

echo -e "${GREEN}Configuration:${NC}"
echo "  Workers: $WORKERS"
echo "  Port: $PORT"
echo "  Database: cid_tokens.db"
echo ""

# Check if port is already in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${RED}Error: Port $PORT is already in use.${NC}"
    echo "Please stop the existing server or set a different PORT environment variable."
    exit 1
fi

# Start server
echo -e "${GREEN}Starting CID API server...${NC}"
echo -e "${GREEN}Access at: http://0.0.0.0:$PORT${NC}"
echo -e "${GREEN}Press Ctrl+C to stop${NC}\n"

# Run with Gunicorn
exec gunicorn -c gunicorn_config.py cid_api:app

