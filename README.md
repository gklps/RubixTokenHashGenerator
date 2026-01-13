# Rubix Token Hash Generator and CID API

A comprehensive toolset for managing Rubix tokens with IPFS integration, including:
- Token hash pre-calculation and lookup
- IPFS CID generation and caching
- High-performance REST API for token lookups
- Batch processing capabilities

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Token Limits](#token-limits)
- [Usage Guide](#usage-guide)
  - [Building CID Cache Database](#building-cid-cache-database)
  - [Running the API Server](#running-the-api-server)
  - [API Endpoints](#api-endpoints)
- [Command Reference](#command-reference)
- [Architecture](#architecture)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)

## Features

### Core Functionality
- ✅ Pre-calculates hash lookup table and stores in SQLite database for fast lookups
- ✅ Generates IPFS CIDs for all tokens using exact `ipfs add` logic
- ✅ Processes tokens from multiple node directories
- ✅ Validates tokens against level limits
- ✅ Fetches token content from IPFS
- ✅ Pins valid tokens to IPFS
- ✅ Updates invalid tokens' status to 2302

### API Features
- ✅ High-performance REST API (handles 100k+ requests)
- ✅ Single token lookup endpoint
- ✅ Batch lookup endpoint (up to 10k CIDs per request)
- ✅ Thread-local database connections
- ✅ SQLite WAL mode for read concurrency
- ✅ In-memory LRU caching for hot CIDs
- ✅ Interactive API documentation (Swagger)
- ✅ Production-ready with Gunicorn

## Requirements

- **Python**: 3.8+
- **IPFS**: Installed and accessible via `ipfs` command
- **System**: Linux/Unix (tested on Ubuntu/Debian)
- **Access**: Node directories with structure:
  - `/wallets/nodeXXX/nodeXXX/.ipfs` (IPFS configuration)
  - `/wallets/nodeXXX/nodeXXX/Rubix/rubix.db` (SQLite database)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd RubixTokenHashGenerator
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure IPFS Path

Edit `ipfs_config.txt`:

```bash
nano ipfs_config.txt
```

Add your IPFS path:
```
IPFS_PATH=/home/cherryrubix/wallets/node002/node002/.ipfs
```

## Quick Start

### Step 1: Build CID Cache Database

This creates a database with all token CIDs and their content:

```bash
# Test with 100 tokens first
python build_cid_cache_optimized.py \
    --level 3 \
    --start 1 \
    --end 100 \
    --ipfs-bin ./ipfs

# Then build for all tokens (see full commands below)
```

### Step 2: Start API Server

```bash
./start_server.sh
```

The API will be available at `http://localhost:5000`

### Step 3: Test the API

```bash
# Single token lookup
curl "http://localhost:5000/token/QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH"

# Batch lookup
curl -X POST http://localhost:5000/tokens/batch \
  -H "Content-Type: application/json" \
  -d '{"cids": ["QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH"]}'
```

## Token Limits

- **Level 1**: 4,300,000 tokens
- **Level 2**: 2,425,000 tokens
- **Level 3**: 2,303,750 tokens
- **Level 4**: 2,188,563 tokens

Tokens outside these limits will have their `token_status` updated to 2302.

## Usage Guide

### Building CID Cache Database

The CID cache database (`cid_tokens.db`) contains all token CIDs and their content. This is a one-time setup that may take several hours for all tokens.

#### Quick Test (100 tokens)

```bash
python build_cid_cache_optimized.py \
    --level 3 \
    --start 1 \
    --end 100 \
    --ipfs-bin ./ipfs
```

#### Build All Tokens

Use the provided script or run manually:

```bash
# Level 1
python build_cid_cache_optimized.py --level 1 --start 1 --end 4300000 --ipfs-bin ./ipfs

# Level 2
python build_cid_cache_optimized.py --level 2 --start 1 --end 2425000 --ipfs-bin ./ipfs

# Level 3
python build_cid_cache_optimized.py --level 3 --start 1 --end 2303750 --ipfs-bin ./ipfs

# Level 4
python build_cid_cache_optimized.py --level 4 --start 1 --end 2188563 --ipfs-bin ./ipfs
```

#### Automated Build Script

Create `build_all_tokens.sh`:

```bash
#!/bin/bash
IPFS_BIN=./ipfs
CHUNK=100000

for level in 1 2 3 4; do
  case $level in
    1) MAX=4300000 ;;
    2) MAX=2425000 ;;
    3) MAX=2303750 ;;
    4) MAX=2188563 ;;
  esac
  
  START=1
  while [ "$START" -le "$MAX" ]; do
    END=$((START + CHUNK - 1))
    if [ "$END" -gt "$MAX" ]; then END=$MAX; fi
    
    python build_cid_cache_optimized.py \
      --level $level \
      --start $START \
      --end $END \
      --ipfs-bin $IPFS_BIN \
      --batch-size 5000
    
    START=$((END + 1))
  done
done
```

#### Performance Options

```bash
# Custom number of workers
python build_cid_cache_optimized.py \
    --level 3 \
    --start 1 \
    --end 100000 \
    --ipfs-bin ./ipfs \
    --workers 8 \
    --batch-size 5000
```

### Running the API Server

#### Development Mode

```bash
python cid_api.py
```

#### Production Mode (Recommended)

```bash
./start_server.sh
```

This script:
- Checks virtual environment
- Installs dependencies if needed
- Validates configuration
- Starts Gunicorn with optimized settings

#### Custom Port

```bash
PORT=8080 ./start_server.sh
```

#### Background Mode

```bash
nohup ./start_server.sh > api.log 2>&1 &
```

### API Endpoints

#### 1. Get Single Token

**Endpoint**: `GET /token/<cid>`

**Example**:
```bash
curl "http://localhost:5000/token/QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH"
```

**Response**:
```json
{
  "cid": "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH",
  "content": "003841d04a85612adb1ca95d86e08561eb1dcc9608899a57b59d57c565d796bb106",
  "token_level": 3,
  "token_number": 1423543
}
```

#### 2. Batch Lookup

**Endpoint**: `POST /tokens/batch`

**Example**:
```bash
curl -X POST http://localhost:5000/tokens/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cids": [
      "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH",
      "QmasEKK2g6rBEW3yHFMMF4JSeTUHEoSGoQc1CLkD84f9HN"
    ]
  }'
```

**Response**:
```json
{
  "results": {
    "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH": {
      "cid": "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH",
      "content": "003841d04a85612adb1ca95d86e08561eb1dcc9608899a57b59d57c565d796bb106",
      "token_level": 3,
      "token_number": 1423543
    }
  },
  "not_found": [],
  "total_requested": 2,
  "total_found": 1,
  "total_not_found": 1
}
```

**Python Example**:
```python
import requests

cids = ["QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH"]
response = requests.post(
    "http://localhost:5000/tokens/batch",
    json={"cids": cids}
)
data = response.json()
print(data["results"])
```

#### 3. Health Check

**Endpoint**: `GET /health`

```bash
curl "http://localhost:5000/health"
```

#### 4. API Documentation

**Endpoint**: `GET /api-docs`

Visit `http://localhost:5000/api-docs` in your browser for interactive Swagger documentation.

## Command Reference

### Build CID Cache

```bash
python build_cid_cache_optimized.py [OPTIONS]

Options:
  --level LEVEL          Token level (1-4) [required]
  --start START          Start token number [required]
  --end END              End token number [required]
  --ipfs-bin PATH        Path to ipfs binary (default: ipfs)
  --config PATH          IPFS config file (default: ipfs_config.txt)
  --workers N            Number of parallel workers (default: CPU count - 1)
  --batch-size N         DB write batch size (default: 5000)
```

### Start API Server

```bash
./start_server.sh
# or
python cid_api.py
# or (production)
gunicorn -c gunicorn_config.py cid_api:app
```

### Pre-calculate Hashes (Legacy)

```bash
python precalculate_hashes.py
```

### Process Tokens (Legacy)

```bash
python main.py --wallets-path /path/to/wallets [OPTIONS]

Options:
  --wallets-path PATH    Path to wallets directory [required]
  --node NODE            Process specific node only
  --hash-db PATH         Path to hash database
  --dry-run              Don't make changes
```

## Architecture

### Database Schema

**cid_tokens.db**:
```sql
CREATE TABLE cid_tokens (
    cid TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    token_level INTEGER,
    token_number INTEGER
);
```

**token_hashes.db** (legacy):
```sql
CREATE TABLE token_hashes (
    hash TEXT PRIMARY KEY,
    token_level INTEGER,
    token_number INTEGER,
    cid TEXT,
    content TEXT
);
```

### Token Content Format

Token content in IPFS is a hex string:
- **First 3 characters**: token level (e.g., "003")
- **Remaining characters**: SHA-256 hash of token number (64 hex chars)

Example: `003f4a5ac9cd7498503f8ab1b5f4f62454703e3cfef47886861d776819d3be9fdbb`
- Level: 3
- Hash: `f4a5ac9cd7498503f8ab1b5f4f62454703e3cfef47886861d776819d3be9fdbb`
- Token number: 1662242 (derived from hash lookup)

### Performance Optimizations

1. **Multiprocessing**: Parallel CID computation using all CPU cores
2. **Producer-Consumer Pattern**: Single database writer process
3. **SQLite WAL Mode**: Better read concurrency
4. **Batch Database Writes**: 5000 records per transaction
5. **Thread-Local Connections**: One DB connection per worker thread
6. **LRU Cache**: In-memory caching for frequently accessed CIDs
7. **Batch API Endpoint**: Single query for up to 10k CIDs

## Performance

### CID Cache Building

- **Speed**: ~20-40 tokens/second per CPU core
- **Total Time**: ~5-8 days for all 11M tokens (8-core machine)
- **Optimization**: Uses multiprocessing and batch writes

### API Performance

- **Single Request**: < 1ms (cached) to ~5ms (uncached)
- **Batch Request (10k CIDs)**: ~100-500ms
- **Throughput**: 5,000-10,000 requests/second (with Gunicorn)
- **100k Requests**: ~10-20 seconds (using batch endpoint)

### Comparison

| Method | Requests | Time | Speedup |
|--------|----------|------|---------|
| Individual API calls | 100k | ~10-20s | 1x |
| Batch API (10k per batch) | 10 batches | ~1-2s | **10-20x** |

## Troubleshooting

### Database Not Found

```bash
# Check if database exists
ls -lh cid_tokens.db

# If missing, build it first
python build_cid_cache_optimized.py --level 3 --start 1 --end 100 --ipfs-bin ./ipfs
```

### IPFS Path Error

```bash
# Check config file
cat ipfs_config.txt

# Verify IPFS path exists
ls -la /home/cherryrubix/wallets/node002/node002/.ipfs
```

### Port Already in Use

```bash
# Check what's using the port
lsof -i :5000

# Use a different port
PORT=8080 ./start_server.sh
```

### Performance Issues

1. **Increase workers**: Edit `gunicorn_config.py`
2. **Increase batch size**: Use `--batch-size 10000`
3. **Check database size**: `du -h cid_tokens.db`
4. **Monitor resources**: `htop` or `top`

### API Errors

```bash
# Check API logs
tail -f api.log

# Test health endpoint
curl http://localhost:5000/health

# Check database connection
sqlite3 cid_tokens.db "SELECT COUNT(*) FROM cid_tokens;"
```

## Error Handling

- If a CID cannot be fetched from IPFS, the token status is updated to 2302
- If token content cannot be parsed, the token status is updated to 2302
- If token number is outside valid limits, the token status is updated to 2302
- All errors are logged and processing continues for remaining tokens
- API returns 404 for not found CIDs, 400 for invalid requests

## License

[Add your license here]

## Support

For issues and questions, please open an issue in the repository.
