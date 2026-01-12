#!/usr/bin/env python3
"""Optimized version: Populate cid_tokens.db with CID→content rows.

Key optimizations:
1. Producer-consumer pattern: Workers compute CIDs, single writer process handles DB
2. SQLite WAL mode for better concurrency
3. Larger batch sizes for database writes
4. Better error handling and progress tracking

For each (level, token_number):
  - content = f"{level:03d}{sha256(str(token_number))}"
  - cid = ipfs add --only-hash (using local ipfs binary and IPFS_PATH)
  - store in cid_tokens.db
"""

import argparse
import os
import subprocess
import sqlite3
import time
from pathlib import Path
from multiprocessing import Pool, Queue, Process, cpu_count
from queue import Empty

from precalculate_hashes import TOKEN_LIMITS, calculate_hash, create_token_content
from cid_cache_db import init_db, DB_PATH


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


def ipfs_only_hash(content: str, ipfs_bin: str = "ipfs", ipfs_path: str = None) -> tuple:
    """
    Replicate: echo -n "CONTENT" | ipfs add --pin=false --only-hash -Q
    Returns: (content, cid) or (content, None) on error
    """
    env = os.environ.copy()
    if ipfs_path:
        env['IPFS_PATH'] = ipfs_path

    try:
        proc = subprocess.Popen(
            [ipfs_bin, "add", "--pin=false", "--only-hash", "-Q"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        stdout, stderr = proc.communicate(input=content, timeout=10)
        if proc.returncode != 0:
            return (content, None)
        return (content, stdout.strip())
    except Exception:
        return (content, None)


def compute_token_cid(args):
    """Compute CID for a single token. Used by multiprocessing Pool."""
    level, token_number, ipfs_bin, ipfs_path = args
    
    # Compute hash and content
    hash_hex = calculate_hash(token_number)
    content = create_token_content(level, hash_hex)
    
    # Get CID via ipfs add --only-hash
    _, cid = ipfs_only_hash(content, ipfs_bin=ipfs_bin, ipfs_path=ipfs_path)
    
    if cid:
        return (cid, content, level, token_number)
    return None


def db_writer_process(queue: Queue, db_path: str, batch_size: int = 5000):
    """
    Single database writer process that batches writes for maximum performance.
    Uses WAL mode for better concurrency.
    """
    # Enable WAL mode for better concurrent access
    conn = sqlite3.connect(db_path, timeout=300.0)  # 5 minute timeout
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL, still safe
    cur.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cur.execute("PRAGMA temp_store=MEMORY")
    conn.commit()
    
    batch = []
    total_written = 0
    last_report = time.time()
    
    while True:
        try:
            # Get item from queue (with timeout to allow periodic flushing)
            try:
                item = queue.get(timeout=1.0)
            except Empty:
                # Flush batch if we have items and queue is empty
                if batch:
                    _write_batch(conn, cur, batch)
                    total_written += len(batch)
                    batch = []
                continue
            
            # Check for sentinel value (end of processing)
            if item is None:
                # Flush remaining batch
                if batch:
                    _write_batch(conn, cur, batch)
                    total_written += len(batch)
                break
            
            batch.append(item)
            
            # Write batch when it reaches batch_size
            if len(batch) >= batch_size:
                _write_batch(conn, cur, batch)
                total_written += len(batch)
                batch = []
                
                # Progress report every 5 seconds
                now = time.time()
                if now - last_report >= 5.0:
                    print(f"  DB: {total_written:,} records written")
                    last_report = now
        
        except Exception as e:
            print(f"  DB Writer Error: {e}")
            # Continue processing
    
    conn.close()
    print(f"  DB Writer finished: {total_written:,} total records written")


def _write_batch(conn, cur, batch):
    """Write a batch of records to the database."""
    if not batch:
        return
    
    cur.executemany(
        """
        INSERT INTO cid_tokens (cid, content, token_level, token_number)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cid) DO UPDATE SET
            content=excluded.content,
            token_level=excluded.token_level,
            token_number=excluded.token_number
        """,
        batch
    )
    conn.commit()


def populate_level(
    level: int,
    start: int,
    end: int,
    ipfs_bin: str = "ipfs",
    ipfs_path: str = None,
    num_workers: int = None,
    batch_size: int = 5000,
) -> None:
    """
    Populate cid_tokens for a single level and token_number range [start, end].
    Uses producer-consumer pattern: workers compute CIDs, single writer handles DB.
    """
    max_tokens = TOKEN_LIMITS[level]
    if end > max_tokens:
        end = max_tokens

    if num_workers is None:
        num_workers = max(1, cpu_count() - 1)  # Leave one core free

    print(f"Processing level {level}, tokens {start}..{end} (max {max_tokens})")
    print(f"Using {num_workers} parallel workers, DB batch size: {batch_size}")

    # Initialize database
    init_db()
    
    # Enable WAL mode on main connection too
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()

    # Create queue for producer-consumer pattern
    queue = Queue(maxsize=10000)  # Buffer up to 10k items
    
    # Start database writer process
    writer = Process(target=db_writer_process, args=(queue, DB_PATH, batch_size))
    writer.start()

    # Prepare arguments for multiprocessing
    token_numbers = list(range(start, end + 1))
    args_list = [(level, tn, ipfs_bin, ipfs_path) for tn in token_numbers]

    total = len(token_numbers)
    processed = 0
    errors = 0
    start_time = time.time()

    try:
        with Pool(processes=num_workers) as pool:
            # Process in chunks to show progress
            chunk_size = max(1000, batch_size)
            
            for chunk_start in range(0, total, chunk_size):
                chunk_end = min(chunk_start + chunk_size, total)
                chunk_args = args_list[chunk_start:chunk_end]
                
                # Compute CIDs in parallel
                results = pool.map(compute_token_cid, chunk_args)
                
                # Send valid results to writer queue
                for result in results:
                    if result is not None:
                        queue.put(result)
                    else:
                        errors += 1
                
                processed += len(chunk_args)
                
                # Progress update
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                pct = (processed / total) * 100
                eta = (total - processed) / rate if rate > 0 else 0
                
                print(f"  Progress: {processed:,}/{total:,} ({pct:.1f}%) | "
                      f"Rate: {rate:.0f}/sec | ETA: {eta/60:.1f} min | Errors: {errors}")
    
    finally:
        # Signal writer to finish
        queue.put(None)
        writer.join()
    
    elapsed = time.time() - start_time
    print(f"Completed level {level}: {processed:,} tokens in {elapsed/60:.1f} min "
          f"({processed/elapsed:.0f}/sec), {errors} errors")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CID→content cache DB (optimized)")
    parser.add_argument("--level", type=int, required=True, help="Token level (1-4)")
    parser.add_argument("--start", type=int, required=True, help="Start token number (inclusive)")
    parser.add_argument("--end", type=int, required=True, help="End token number (inclusive)")
    parser.add_argument("--ipfs-bin", type=str, default="ipfs", help="Path to ipfs binary (default: ipfs)")
    parser.add_argument("--config", type=str, default="ipfs_config.txt", help="Path to IPFS config file (default: ipfs_config.txt)")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers (default: CPU count - 1)")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for DB writes (default: 5000)")

    args = parser.parse_args()

    if args.level not in TOKEN_LIMITS:
        raise SystemExit(f"Invalid level {args.level}, must be 1-4")

    # Load IPFS_PATH from config file
    try:
        ipfs_path = load_ipfs_path(args.config)
        print(f"Using IPFS_PATH: {ipfs_path}")
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    populate_level(
        args.level, 
        args.start, 
        args.end, 
        ipfs_bin=args.ipfs_bin, 
        ipfs_path=ipfs_path,
        num_workers=args.workers,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()

