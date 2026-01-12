#!/usr/bin/env python3
"""
Pre-calculate all token hashes and store them in a SQLite database.
This creates a lookup table for fast token number resolution from hashes.
"""

import sqlite3
import hashlib
import os
from pathlib import Path
from typing import Optional

# Try to import CID calculation library
try:
    from cid import make_cid
    CID_AVAILABLE = True
except ImportError:
    try:
        from py_cid import make_cid
        CID_AVAILABLE = True
    except ImportError:
        try:
            from multiformats import CID
            CID_AVAILABLE = True
        except ImportError:
            CID_AVAILABLE = False

# Token level limits
TOKEN_LIMITS = {
    1: 4300000,
    2: 2425000,
    3: 2303750,
    4: 2188563
}

DB_PATH = 'token_hashes.db'


def create_database(db_path: str):
    """Create the database and table structure"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table with hash as primary key for fast lookups
    # Also store CID for reverse lookups
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_hashes (
            hash TEXT PRIMARY KEY,
            token_level INTEGER NOT NULL,
            token_number INTEGER NOT NULL,
            cid TEXT,
            content TEXT
        )
    ''')
    
    # Create index on token_level and token_number for reverse lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_token_level_number 
        ON token_hashes(token_level, token_number)
    ''')
    
    # Create index on CID for reverse lookups (CID -> token details)
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_cid 
        ON token_hashes(cid)
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database created/verified: {db_path}")


def calculate_hash(token_number: int) -> str:
    """Calculate SHA-256 hash of token number as string"""
    token_str = str(token_number)
    hash_obj = hashlib.sha256(token_str.encode('utf-8'))
    return hash_obj.hexdigest()


def create_token_content(token_level: int, hash_hex: str) -> str:
    """Create token content string from level and hash"""
    return f"{token_level:03d}{hash_hex}"


def create_dag_pb_node(data: bytes) -> bytes:
    """
    Create a dag-pb protobuf node structure.
    NOTE: This implementation may not produce CIDs that exactly match IPFS.
    For exact matching, use 'ipfs add' command when available.
    
    For IPFS, a simple leaf node is:
    PBNode {
        Links: [] (empty, encoded as empty)
        Data: <content bytes>
    }
    
    Protobuf wire format for PBNode:
    - Field 1 (Links): repeated PBLink (empty in our case, so omitted)
    - Field 2 (Data): bytes (varint length + data)
    """
    # For a simple node with just data and no links:
    # Field 2 (Data) = 0x12 (field number 2, wire type 2 = length-delimited)
    # Then varint-encoded length, then the data
    
    # Protobuf encoding: field_number << 3 | wire_type
    # Field 2, wire type 2 (length-delimited) = 2 << 3 | 2 = 18 = 0x12
    data_length = len(data)
    
    # Encode length as varint
    varint_bytes = bytearray()
    temp_length = data_length
    while temp_length > 0x7f:
        varint_bytes.append((temp_length & 0x7f) | 0x80)
        temp_length >>= 7
    varint_bytes.append(temp_length & 0x7f)
    
    # Combine: field tag (0x12) + varint length + data
    node_bytes = bytearray([0x12]) + varint_bytes + data
    return bytes(node_bytes)


def hash_to_cidv0(hash_hex: str) -> Optional[str]:
    """
    Convert a SHA-256 hash (hex string) directly to IPFS CIDv0.
    This is the simple method: prepend 1220 and base58 encode.
    
    Args:
        hash_hex: 64-character SHA-256 hexadecimal string
        
    Returns:
        IPFS CIDv0 string (Qm... format)
    """
    try:
        import binascii
        import base58
        
        # Remove all whitespace
        hash_hex = ''.join(c for c in hash_hex if c not in ' \n\r\t\v\f')
        
        if len(hash_hex) != 64:
            return None
        
        # Normalize to lowercase
        hash_hex = hash_hex.lower()
        
        # Prepend "1220" (SHA2-256 codec + 32 byte length)
        combined_hex = "1220" + hash_hex
        
        # Convert to bytes and base58 encode
        combined_bytes = binascii.unhexlify(combined_hex)
        cid = base58.b58encode(combined_bytes).decode('ascii')
        
        return cid
    except Exception:
        return None


def calculate_ipfs_cid(content: str, use_ipfs_command: bool = True, use_go_helper: bool = False) -> Optional[str]:
    """
    Calculate IPFS CID for content.
    
    Tries methods in order:
    1. IPFS command ('ipfs add') - MOST ACCURATE, guaranteed to match IPFS exactly
    2. Go helper program (calculate_cid) - fallback, may not match exactly due to protobuf encoding differences
    3. Python library method - last resort, may not match exactly
    
    IMPORTANT: For accurate CIDs that match IPFS exactly, ensure 'ipfs add' command is available.
    The Go helper uses go-cid but may produce different CIDs due to dag-pb protobuf encoding differences.
    
    Args:
        content: The content string to calculate CID for (no trailing newline)
        use_ipfs_command: If True, try 'ipfs add' command first (RECOMMENDED)
        use_go_helper: If True, try Go helper program as fallback (experimental)
    """
    import subprocess
    import os
    
    # Try using IPFS command first (MOST ACCURATE - uses IPFS's actual implementation)
    # This is the recommended method as it guarantees exact matching with IPFS
    if use_ipfs_command:
        try:
            # Use binary mode to ensure exact content matching (no text encoding issues)
            process = subprocess.Popen(
                ['ipfs', 'add', '-Q'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate(input=content.encode('utf-8'), timeout=10)
            if process.returncode == 0:
                return stdout.decode('utf-8').strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass  # Fall through to Go helper or library method
    
    # Try Go helper program as fallback (experimental - may not match IPFS exactly)
    # NOTE: The Go helper uses go-cid but may produce different CIDs due to
    # differences in dag-pb protobuf encoding. Use 'ipfs add' for accurate results.
    if use_go_helper:
        go_helper_path = os.path.join(os.path.dirname(__file__), 'calculate_cid')
        if os.path.exists(go_helper_path):
            try:
                process = subprocess.Popen(
                    [go_helper_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10
                )
                stdout, stderr = process.communicate(input=content, timeout=10)
                if process.returncode == 0:
                    return stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                pass  # Fall through to library method
    
    # Library-based method (fallback, may not match IPFS exactly)
    try:
        # Convert content to bytes
        content_bytes = content.encode('utf-8')
        
        # Create dag-pb protobuf node structure
        dag_pb_node = create_dag_pb_node(content_bytes)
        
        # Calculate SHA-256 hash of the protobuf-encoded node
        node_hash = hashlib.sha256(dag_pb_node).digest()
        
        # Create CIDv0 with dag-pb codec
        # CIDv0 format: base58(Qm + 0x12 + 0x20 + hash)
        # Where 0x12 = dag-pb codec, 0x20 = SHA-256 multihash code
        try:
            from cid import make_cid
            # CIDv0 only supports 'dag-pb' codec
            cid = make_cid(0, 'dag-pb', node_hash)
            return str(cid)
        except ImportError:
            try:
                from py_cid import make_cid
                cid = make_cid(0, 'dag-pb', node_hash)
                return str(cid)
            except ImportError:
                try:
                    from multiformats import CID, multihash
                    # Create multihash first
                    mh = multihash.encode(node_hash, 'sha2-256')
                    # Create CIDv0 with dag-pb codec
                    cid = CID('base58btc', 0, 'dag-pb', mh)
                    return str(cid)
                except Exception:
                    return None
        except Exception as e:
            # Return None on any error (e.g., codec not supported)
            return None
    except Exception as e:
        # Return None on any error
        return None


def populate_database(db_path: str, batch_size: int = 10000):
    """Populate database with all token hashes"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if database already has data
    cursor.execute('SELECT COUNT(*) FROM token_hashes')
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        print(f"Database already contains {existing_count:,} entries.")
        response = input("Do you want to recreate it? (yes/no): ")
        if response.lower() == 'yes':
            cursor.execute('DELETE FROM token_hashes')
            conn.commit()
            print("Cleared existing data.")
        else:
            print("Keeping existing data. Exiting.")
            conn.close()
            return
    
    total = sum(TOKEN_LIMITS.values())
    print(f"\nPre-calculating {total:,} token hashes...")
    if CID_AVAILABLE:
        print("CID calculation: ENABLED (using Python library, no IPFS node needed)")
    else:
        print("CID calculation: DISABLED (install py-cid: pip install py-cid)")
    print("This may take a few minutes...\n")
    
    count = 0
    batch = []
    
    for level in range(1, 5):
        max_tokens = TOKEN_LIMITS[level]
        print(f"Processing level {level} ({max_tokens:,} tokens)...")
        
        for token_num in range(1, max_tokens + 1):
            hash_hex = calculate_hash(token_num)
            content = create_token_content(level, hash_hex)
            
            # Calculate CID - try simple hash-to-CID conversion first
            # This converts the hash directly to CIDv0 (prepend 1220 + base58)
            cid = hash_to_cidv0(hash_hex)
            
            # If that doesn't work, fall back to IPFS command or other methods
            if not cid:
                cid = calculate_ipfs_cid(content) if CID_AVAILABLE else None
            
            batch.append((hash_hex, level, token_num, cid, content))
            
            if len(batch) >= batch_size:
                cursor.executemany(
                    'INSERT OR REPLACE INTO token_hashes (hash, token_level, token_number, cid, content) VALUES (?, ?, ?, ?, ?)',
                    batch
                )
                conn.commit()
                count += len(batch)
                batch = []
                
                if count % 100000 == 0:
                    print(f"  Processed {count:,} / {total:,} tokens...")
        
        # Insert remaining batch items for this level
        if batch:
            cursor.executemany(
                'INSERT OR REPLACE INTO token_hashes (hash, token_level, token_number, cid, content) VALUES (?, ?, ?, ?, ?)',
                batch
            )
            conn.commit()
            count += len(batch)
            batch = []
    
    # Final batch
    if batch:
        cursor.executemany(
            'INSERT OR REPLACE INTO token_hashes (hash, token_level, token_number, cid, content) VALUES (?, ?, ?, ?, ?)',
            batch
        )
        conn.commit()
        count += len(batch)
    
    # Verify count
    cursor.execute('SELECT COUNT(*) FROM token_hashes')
    final_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"Pre-calculation complete!")
    print(f"Total entries in database: {final_count:,}")
    print(f"Database file: {os.path.abspath(db_path)}")
    print(f"{'='*60}")


def verify_database(db_path: str, test_hashes: list = None):
    """Verify database integrity with some test cases"""
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM token_hashes')
    count = cursor.fetchone()[0]
    print(f"\nDatabase contains {count:,} entries")
    
    # Test some known values
    if test_hashes:
        print("\nTesting known hash lookups:")
        for hash_hex, expected_level, expected_number in test_hashes:
            cursor.execute(
                'SELECT token_level, token_number FROM token_hashes WHERE hash = ?',
                (hash_hex,)
            )
            result = cursor.fetchone()
            if result:
                level, number = result
                status = "✓" if level == expected_level and number == expected_number else "✗"
                print(f"  {status} Hash {hash_hex[:16]}... -> Level {level}, Number {number} (expected: {expected_level}, {expected_number})")
            else:
                print(f"  ✗ Hash {hash_hex[:16]}... -> NOT FOUND")
    
    # Test the example from user: hash of "1662242" should be found
    test_hash = calculate_hash(1662242)
    cursor.execute(
        'SELECT token_level, token_number, cid FROM token_hashes WHERE hash = ?',
        (test_hash,)
    )
    result = cursor.fetchone()
    if result:
        level, number, cid = result
        print(f"\n  Test: Hash of '1662242' -> Level {level}, Number {number}")
        print(f"  Hash: {test_hash}")
        if cid:
            print(f"  CID: {cid}")
    
    # Test CID lookup if available
    cursor.execute('SELECT COUNT(*) FROM token_hashes WHERE cid IS NOT NULL')
    cid_count = cursor.fetchone()[0]
    if cid_count > 0:
        print(f"\n  Database contains {cid_count:,} entries with CIDs")
        # Test a CID lookup
        cursor.execute('SELECT token_level, token_number, hash FROM token_hashes WHERE cid IS NOT NULL LIMIT 1')
        test_result = cursor.fetchone()
        if test_result:
            test_level, test_num, test_hash = test_result
            cursor.execute('SELECT cid FROM token_hashes WHERE hash = ?', (test_hash,))
            test_cid = cursor.fetchone()[0]
            print(f"  Sample CID lookup: {test_cid[:20]}... -> Level {test_level}, Number {test_num}")
    else:
        print(f"\n  No CIDs in database (CID calculation was disabled or failed)")
    
    conn.close()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Pre-calculate token hashes and store in SQLite database'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=DB_PATH,
        help=f'Path to SQLite database (default: {DB_PATH})'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify database integrity instead of creating it'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force recreation of database (deletes existing data)'
    )
    
    args = parser.parse_args()
    
    if args.verify:
        verify_database(args.db_path)
        return
    
    if args.force and os.path.exists(args.db_path):
        print(f"Removing existing database: {args.db_path}")
        os.remove(args.db_path)
    
    # Create database
    create_database(args.db_path)
    
    # Populate database
    populate_database(args.db_path)
    
    # Verify
    print("\nVerifying database...")
    verify_database(args.db_path)


if __name__ == '__main__':
    main()

