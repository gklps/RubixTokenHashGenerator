# Rubix Token Hash Generator and IPFS Pinner

This tool processes tokens from SQLite databases, validates them against token level limits, and pins them to IPFS.

## Features

- Pre-calculates hash lookup table and stores in SQLite database for fast lookups
- Processes tokens from multiple node directories
- Validates tokens against level limits
- Fetches token content from IPFS
- Pins valid tokens to IPFS
- Updates invalid tokens' status to 2302
- Handles errors gracefully

## Requirements

- Python 3.6+
- IPFS installed and accessible via `ipfs` command
- Access to node directories with structure:
  - `/wallets/nodeXXX/nodeXXX/.ipfs` (IPFS configuration)
  - `/wallets/nodeXXX/nodeXXX/Rubix/rubix.db` (SQLite database)

## Token Limits

- Level 1: 4,300,000 tokens
- Level 2: 2,425,000 tokens
- Level 3: 2,303,750 tokens
- Level 4: 2,188,563 tokens

Tokens outside these limits will have their `token_status` updated to 2302.

## Setup

### Step 1: Pre-calculate hash database

First, you need to create the hash lookup database. This only needs to be done once:

```bash
python precalculate_hashes.py
```

This will create `token_hashes.db` with all ~11 million token hash entries. This may take a few minutes.

**CID Calculation:**
- The script will try to calculate IPFS CIDs for each token
- **Recommended**: Ensure IPFS is installed and available (`ipfs` command) for accurate CID calculation
- **Alternative**: A Go helper program (`calculate_cid`) can be built using `./build_go_helper.sh` (requires Go installed)
- The `ipfs add` command is used first (most accurate), then falls back to the Go helper or Python library

To verify the database:
```bash
python precalculate_hashes.py --verify
```

To force recreation:
```bash
python precalculate_hashes.py --force
```

### Step 2: Process tokens

Once the database is created, you can process tokens:

#### Basic usage (process all nodes)
```bash
python main.py --wallets-path /home/cherryrubix/wallets
```

#### Process a specific node
```bash
python main.py --wallets-path /home/cherryrubix/wallets --node node002
```

#### Dry run (no changes)
```bash
python main.py --wallets-path /home/cherryrubix/wallets --dry-run
```

#### Use custom hash database path
```bash
python main.py --wallets-path /home/cherryrubix/wallets --hash-db /path/to/token_hashes.db
```

## How it works

1. **Pre-calculation** (one-time setup): The `precalculate_hashes.py` script calculates SHA-256 hashes for all valid token numbers (levels 1-4) and stores them in a SQLite database (`token_hashes.db`) for fast lookups.

2. **Node discovery**: The main script finds all node directories in the wallets path

3. **For each node**:
   - Sets `IPFS_PATH` environment variable to the node's `.ipfs` directory
   - Queries database for tokens with `token_status = 0`
   - For each token:
     - Fetches content from IPFS using the CID
     - Parses content to extract token level and hash
     - Looks up token number from hash using the pre-calculated database
     - Validates token number is within level limits
     - Pins the CID if valid
     - Updates status to 2302 if invalid

The database approach is much more memory-efficient than keeping ~11 million entries in RAM, and provides fast O(1) hash lookups.

## Token Content Format

Token content in IPFS is a hex string:
- First 3 characters: token level (e.g., "003")
- Remaining characters: SHA-256 hash of token number (e.g., "f4a5ac9cd7498503f8ab1b5f4f62454703e3cfef47886861d776819d3be9fdbb")

Example: `003f4a5ac9cd7498503f8ab1b5f4f62454703e3cfef47886861d776819d3be9fdbb`
- Level: 3
- Hash: f4a5ac9cd7498503f8ab1b5f4f62454703e3cfef47886861d776819d3be9fdbb
- Token number: 1662242 (derived from hash lookup)

## Error Handling

- If a CID cannot be fetched from IPFS, the token status is updated to 2302
- If token content cannot be parsed, the token status is updated to 2302
- If token number is outside valid limits, the token status is updated to 2302
- All errors are logged and processing continues for remaining tokens

