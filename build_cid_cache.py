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

from precalculate_hashes import TOKEN_LIMITS, calculate_hash, create_token_content
from cid_cache_db import init_db, upsert_token


def ipfs_only_hash(content: str, ipfs_bin: str = "ipfs") -> str:
    """Replicate: echo -n "CONTENT" | ipfs add --pin=false --only-hash -Q"""
    env = os.environ.copy()

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
            cid = ipfs_only_hash(content, ipfs_bin=ipfs_bin)
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

    args = parser.parse_args()

    if args.level not in TOKEN_LIMITS:
        raise SystemExit(f"Invalid level {args.level}, must be 1-4")

    populate_level(args.level, args.start, args.end, ipfs_bin=args.ipfs_bin)


if __name__ == "__main__":
    main()

