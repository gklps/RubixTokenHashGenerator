#!/bin/bash
# Production API server startup script

cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Check if Gunicorn is installed
if ! python -c "import gunicorn" 2>/dev/null; then
    echo "Installing Gunicorn..."
    pip install gunicorn
fi

# Start Gunicorn with production settings
echo "Starting CID API server with Gunicorn..."
echo "Workers: $(python -c 'import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)')"
echo "Access at: http://0.0.0.0:5000"

gunicorn -c gunicorn_config.py cid_api:app

