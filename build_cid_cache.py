#!/usr/bin/env python3
"""Populate cid_tokens.db with CID→content rows.

For each (level, token_number):
  - content = f"{level:03d}{sha256(str(token_number))}"
  - cid = ipfs add --only-hash (using local ipfs binary and IPFS_PATH)
  - store in cid_tokens.db

Run in chunks using --level and --start/--end to avoid huge single runs.
"""

import argparse
import os
import subprocess
from pathlib import Path

from precalculate_hashes import TOKEN_LIMITS, calculate_hash, create_token_content
from cid_cache_db import init_db, upsert_token


def load_ipfs_path(config_file: str = "ipfs_config.txt") -> str:
    """Load IPFS_PATH from config file or environment variable."""
    # First try environment variable
    ipfs_path = os.environ.get("IPFS_PATH")
    if ipfs_path and os.path.exists(ipfs_path):
        return ipfs_path
    
    # Try config file
    config_path = Path(config_file)
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    if line.startswith('IPFS_PATH='):
                        ipfs_path = line.split('=', 1)[1].strip()
                        if ipfs_path and os.path.exists(ipfs_path):
                            return ipfs_path
    
    # If not found, raise error
    raise FileNotFoundError(
        f"IPFS_PATH not configured. Please set it in {config_file} or as environment variable.\n"
        f"Example: IPFS_PATH=/home/cherryrubix/wallets/node002/node002/.ipfs"
    )


def ipfs_only_hash(content: str, ipfs_bin: str = "ipfs", ipfs_path: str = None) -> str:
    """Replicate: echo -n "CONTENT" | ipfs add --pin=false --only-hash -Q"""
    env = os.environ.copy()
    if ipfs_path:
        env['IPFS_PATH'] = ipfs_path

    proc = subprocess.Popen(
        [ipfs_bin, "add", "--pin=false", "--only-hash", "-Q"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    stdout, stderr = proc.communicate(input=content)
    if proc.returncode != 0:
        raise RuntimeError(f"ipfs add failed: {stderr.strip()}")
    return stdout.strip()


def populate_level(
    level: int,
    start: int,
    end: int,
    ipfs_bin: str = "ipfs",
    ipfs_path: str = None,
) -> None:
    """Populate cid_tokens for a single level and token_number range [start, end]."""
    max_tokens = TOKEN_LIMITS[level]
    if end > max_tokens:
        end = max_tokens

    print(f"Processing level {level}, tokens {start}..{end} (max {max_tokens})")

    init_db()

    for token_number in range(start, end + 1):
        # Compute hash and content
        hash_hex = calculate_hash(token_number)
        content = create_token_content(level, hash_hex)

        # Get CID via ipfs add --only-hash
        try:
            cid = ipfs_only_hash(content, ipfs_bin=ipfs_bin, ipfs_path=ipfs_path)
        except Exception as e:
            print(f"  ERROR level {level} token {token_number}: {e}")
            continue

        # Store in DB
        upsert_token(cid, content, token_level=level, token_number=token_number)

        if token_number % 1000 == 0:
            print(f"  ... up to token {token_number}, last CID {cid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CID→content cache DB")
    parser.add_argument("--level", type=int, required=True, help="Token level (1-4)")
    parser.add_argument("--start", type=int, required=True, help="Start token number (inclusive)")
    parser.add_argument("--end", type=int, required=True, help="End token number (inclusive)")
    parser.add_argument("--ipfs-bin", type=str, default="ipfs", help="Path to ipfs binary (default: ipfs)")
    parser.add_argument("--config", type=str, default="ipfs_config.txt", help="Path to IPFS config file (default: ipfs_config.txt)")

    args = parser.parse_args()

    if args.level not in TOKEN_LIMITS:
        raise SystemExit(f"Invalid level {args.level}, must be 1-4")

    # Load IPFS_PATH from config file
    try:
        ipfs_path = load_ipfs_path(args.config)
        print(f"Using IPFS_PATH: {ipfs_path}")
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    populate_level(args.level, args.start, args.end, ipfs_bin=args.ipfs_bin, ipfs_path=ipfs_path)


if __name__ == "__main__":
    main()

