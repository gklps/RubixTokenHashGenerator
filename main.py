#!/usr/bin/env python3
"""
Rubix Token Hash Generator and IPFS Pinner
This tool processes tokens from SQLite databases, validates them, and pins them to IPFS.
"""

import os
import sys
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional, List

# Token level limits
TOKEN_LIMITS = {
    1: 4300000,
    2: 2425000,
    3: 2303750,
    4: 2188563
}


class HashLookupTable:
    """Database-backed lookup table for token hashes"""
    
    def __init__(self, db_path: str = 'token_hashes.db'):
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Hash lookup database not found: {db_path}\n"
                f"Please run 'python precalculate_hashes.py' first to create the database."
            )
        self._verify_database()
    
    def _verify_database(self):
        """Verify database exists and has data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM token_hashes')
            count = cursor.fetchone()[0]
            conn.close()
            if count == 0:
                raise ValueError(f"Database {self.db_path} is empty. Please run precalculate_hashes.py")
            print(f"Loaded hash lookup database: {count:,} entries")
        except sqlite3.OperationalError as e:
            raise ValueError(f"Database {self.db_path} is not valid: {e}")
    
    def lookup(self, hash_hex: str) -> Optional[Tuple[int, int]]:
        """Look up token level and number from hash using database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT token_level, token_number FROM token_hashes WHERE hash = ?',
                (hash_hex,)
            )
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return (result[0], result[1])
            return None
        except Exception as e:
            print(f"Error looking up hash in database: {e}")
            return None
    
    def lookup_by_cid(self, cid: str) -> Optional[Tuple[int, int, str]]:
        """Look up token level, number, and hash from CID using database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT token_level, token_number, hash FROM token_hashes WHERE cid = ?',
                (cid,)
            )
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return (result[0], result[1], result[2])
            return None
        except Exception as e:
            print(f"Error looking up CID in database: {e}")
            return None


class IPFSManager:
    """Manages IPFS operations"""
    
    def __init__(self, ipfs_path: str):
        self.ipfs_path = ipfs_path
        self.env = os.environ.copy()
        self.env['IPFS_PATH'] = ipfs_path
    
    def _run_ipfs(self, args: List[str]) -> Tuple[bool, str, str]:
        """Run IPFS command and return (success, stdout, stderr)"""
        try:
            result = subprocess.run(
                ['ipfs'] + args,
                env=self.env,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def fetch_content(self, cid: str) -> Optional[str]:
        """Fetch content from IPFS by CID"""
        success, stdout, stderr = self._run_ipfs(['cat', cid])
        if success:
            return stdout
        return None
    
    def add_content(self, content: str) -> Optional[str]:
        """Add content to IPFS and return the CID"""
        try:
            process = subprocess.Popen(
                ['ipfs', 'add', '-Q'],
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=content, timeout=30)
            if process.returncode == 0:
                return stdout.strip()
            return None
        except Exception as e:
            print(f"  Error adding content: {e}")
            return None
    
    def pin_add(self, cid: str) -> bool:
        """Pin a CID in IPFS"""
        success, stdout, stderr = self._run_ipfs(['pin', 'add', cid])
        if not success:
            # Check if already pinned
            success, stdout, stderr = self._run_ipfs(['pin', 'ls', cid])
            if success and cid in stdout:
                return True  # Already pinned
        return success
    
    def ensure_pinned(self, cid: str) -> bool:
        """Ensure a CID is pinned (add if not already pinned)"""
        # Check if already pinned
        success, stdout, stderr = self._run_ipfs(['pin', 'ls', cid])
        if success and cid in stdout:
            return True  # Already pinned
        
        # Pin it
        return self.pin_add(cid)


class TokenProcessor:
    """Processes tokens from database"""
    
    def __init__(self, hash_lookup: HashLookupTable):
        self.hash_lookup = hash_lookup
    
    def parse_token_content(self, content: str) -> Optional[Tuple[int, str, Optional[int]]]:
        """
        Parse token content string.
        Returns: (token_level, hash_hex, token_number) or None if invalid
        """
        if len(content) < 3:
            return None
        
        try:
            token_level_str = content[:3]
            hash_hex = content[3:]
            
            token_level = int(token_level_str)
            
            if token_level < 1 or token_level > 4:
                return None
            
            # Look up token number from hash
            token_info = self.hash_lookup.lookup(hash_hex)
            token_number = token_info[1] if token_info else None
            
            return (token_level, hash_hex, token_number)
        except ValueError:
            return None
    
    def validate_token(self, token_level: int, token_number: Optional[int]) -> Tuple[bool, Optional[int]]:
        """
        Validate token level and number.
        Returns: (is_valid, error_status_code)
        """
        if token_number is None:
            return False, 2302  # Hash not found in lookup table
        
        if token_level not in TOKEN_LIMITS:
            return False, 2302
        
        max_tokens = TOKEN_LIMITS[token_level]
        if token_number > max_tokens:
            return False, 2302
        
        return True, None


class DatabaseManager:
    """Manages database operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_tokens_with_status_zero(self) -> List[Tuple[str]]:
        """Get all token_id values where token_status = 0"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT token_id FROM TokensTable WHERE token_status = 0")
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            print(f"  Error querying database: {e}")
            return []
    
    def update_token_status(self, token_id: str, new_status: int) -> bool:
        """Update token_status for a token_id"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE TokensTable SET token_status = ? WHERE token_id = ?",
                (new_status, token_id)
            )
            conn.commit()
            updated = cursor.rowcount > 0
            conn.close()
            return updated
        except Exception as e:
            print(f"  Error updating token status: {e}")
            return False


def find_node_directories(wallets_path: str) -> List[Path]:
    """Find all node directories in the wallets path"""
    wallets = Path(wallets_path)
    if not wallets.exists():
        return []
    
    nodes = []
    for item in wallets.iterdir():
        if item.is_dir() and item.name.startswith('node') and item.name[4:].isdigit():
            # Check if it has the expected structure: nodeXXX/nodeXXX/.ipfs
            node_inner = item / item.name
            ipfs_dir = node_inner / '.ipfs'
            db_path = node_inner / 'Rubix' / 'rubix.db'
            
            if ipfs_dir.exists() and db_path.exists():
                nodes.append(item)
    
    return sorted(nodes)


def process_node(node_path: Path, hash_lookup: HashLookupTable, dry_run: bool = False):
    """Process a single node"""
    node_name = node_path.name
    print(f"\n{'='*60}")
    print(f"Processing node: {node_name}")
    print(f"{'='*60}")
    
    # Set up paths
    node_inner = node_path / node_name
    ipfs_path = str(node_inner / '.ipfs')
    db_path = str(node_inner / 'Rubix' / 'rubix.db')
    
    if not os.path.exists(ipfs_path):
        print(f"  ERROR: IPFS path not found: {ipfs_path}")
        return
    
    if not os.path.exists(db_path):
        print(f"  ERROR: Database not found: {db_path}")
        return
    
    # Initialize managers
    ipfs_manager = IPFSManager(ipfs_path)
    db_manager = DatabaseManager(db_path)
    token_processor = TokenProcessor(hash_lookup)
    
    # Get tokens with status 0
    print(f"  Querying database for tokens with status=0...")
    tokens = db_manager.get_tokens_with_status_zero()
    print(f"  Found {len(tokens)} tokens to process")
    
    if len(tokens) == 0:
        return
    
    # Process each token
    stats = {
        'processed': 0,
        'pinned': 0,
        'invalid': 0,
        'errors': 0
    }
    
    for (token_id,) in tokens:
        stats['processed'] += 1
        cid = token_id.strip()
        
        if stats['processed'] % 100 == 0:
            print(f"  Progress: {stats['processed']}/{len(tokens)} tokens processed...")
        
        # Fetch content from IPFS
        content = ipfs_manager.fetch_content(cid)
        
        if content is None:
            # Content not found in IPFS
            print(f"  WARNING: CID {cid} not found in IPFS")
            # Update status to indicate error
            if not dry_run:
                db_manager.update_token_status(cid, 2302)
            stats['errors'] += 1
            continue
        
        # Strip whitespace from content
        content = content.strip()
        
        # Parse content
        parsed = token_processor.parse_token_content(content)
        if parsed is None:
            print(f"  WARNING: Could not parse content for CID {cid}: {content[:50]}...")
            if not dry_run:
                db_manager.update_token_status(cid, 2302)
            stats['errors'] += 1
            continue
        
        token_level, hash_hex, token_number = parsed
        
        # Validate token
        is_valid, error_status = token_processor.validate_token(token_level, token_number)
        
        if not is_valid:
            print(f"  Invalid token: CID {cid}, level={token_level}, number={token_number}")
            if not dry_run:
                db_manager.update_token_status(cid, error_status or 2302)
            stats['invalid'] += 1
            continue
        
        # Verify content format matches expected and ensure it's in IPFS
        expected_content = f"{token_level:03d}{hash_hex}"
        if content != expected_content:
            print(f"  WARNING: Content format mismatch for CID {cid}, re-adding correct content...")
            # Re-add the correct content to ensure it exists
            new_cid = ipfs_manager.add_content(expected_content)
            if new_cid and new_cid != cid:
                print(f"  ERROR: CID mismatch! Expected {cid}, got {new_cid}")
                if not dry_run:
                    db_manager.update_token_status(cid, 2302)
                stats['errors'] += 1
                continue
        
        # Pin the CID
        if not dry_run:
            if ipfs_manager.ensure_pinned(cid):
                stats['pinned'] += 1
            else:
                print(f"  ERROR: Failed to pin CID {cid}")
                stats['errors'] += 1
        else:
            stats['pinned'] += 1
    
    # Print summary
    print(f"\n  Summary for {node_name}:")
    print(f"    Processed: {stats['processed']}")
    print(f"    Pinned: {stats['pinned']}")
    print(f"    Invalid: {stats['invalid']}")
    print(f"    Errors: {stats['errors']}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Rubix Token Hash Generator and IPFS Pinner'
    )
    parser.add_argument(
        '--wallets-path',
        type=str,
        default='/home/cherryrubix/wallets',
        help='Path to wallets directory (default: /home/cherryrubix/wallets)'
    )
    parser.add_argument(
        '--node',
        type=str,
        help='Process only a specific node (e.g., node002)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (do not make changes)'
    )
    parser.add_argument(
        '--hash-db',
        type=str,
        default='token_hashes.db',
        help='Path to token hashes database (default: token_hashes.db)'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    
    # Initialize hash lookup table from database
    print("Initializing...")
    try:
        hash_lookup = HashLookupTable(args.hash_db)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    # Find nodes
    if args.node:
        node_path = Path(args.wallets_path) / args.node
        if node_path.exists():
            nodes = [node_path]
        else:
            print(f"ERROR: Node {args.node} not found at {node_path}")
            sys.exit(1)
    else:
        nodes = find_node_directories(args.wallets_path)
        if not nodes:
            print(f"ERROR: No valid node directories found in {args.wallets_path}")
            sys.exit(1)
    
    print(f"\nFound {len(nodes)} node(s) to process")
    
    # Process each node
    for node_path in nodes:
        try:
            process_node(node_path, hash_lookup, dry_run=args.dry_run)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\nERROR processing {node_path.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "="*60)
    print("Processing complete!")
    print("="*60)


if __name__ == '__main__':
    main()

