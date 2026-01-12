#!/usr/bin/env python3
"""
Convert a SHA-256 hex string to IPFS CIDv0.

Input: 64-character SHA-256 hexadecimal string
Output: IPFS CIDv0 (Qm... format)

Process:
1. Prepend "1220" to the hex string (12 = SHA2-256, 20 = 32 bytes length)
2. Convert hex string to bytes
3. Base58BTC encode to get CIDv0
"""

import sys
import binascii

try:
    import base58
except ImportError:
    print("Error: base58 library not installed.")
    print("Install with: pip install base58")
    sys.exit(1)


def hex_to_cidv0(hex_string: str) -> str:
    """
    Convert a SHA-256 hex string to IPFS CIDv0.
    
    Args:
        hex_string: 64-character SHA-256 hexadecimal string
                   (or 67-character string with prefix, will extract last 64 chars)
        
    Returns:
        IPFS CIDv0 string (Qm... format)
    """
    # Remove ALL whitespace (spaces, newlines, tabs, carriage returns, etc.)
    # This ensures no hidden characters interfere
    hex_string = ''.join(c for c in hex_string if c not in ' \n\r\t\v\f')
    
    # Validate hex characters
    if not all(c in '0123456789abcdefABCDEF' for c in hex_string):
        raise ValueError("Input must be a valid hexadecimal string")
    
    # Normalize to lowercase
    hex_string = hex_string.lower()
    
    # Handle different input lengths
    if len(hex_string) == 67:
        # If 67 chars, assume format is "XXX" + 64-char hash, extract last 64
        hex_string = hex_string[-64:]
    elif len(hex_string) == 64:
        # Perfect, use as-is
        pass
    else:
        raise ValueError(f"Input must be 64 or 67 characters after removing whitespace (got {len(hex_string)})")
    
    # Step 1: Prepend "1220" (SHA2-256 codec + 32 byte length)
    # 12 = SHA2-256 multihash code
    # 20 = 32 bytes (0x20 in hex)
    combined_hex = "1220" + hex_string
    
    # Step 2: Convert hex string to bytes
    try:
        combined_bytes = binascii.unhexlify(combined_hex)
    except binascii.Error as e:
        raise ValueError(f"Invalid hex string: {e}")
    
    # Step 3: Base58BTC encode to get CIDv0
    cid = base58.b58encode(combined_bytes).decode('ascii')
    
    return cid


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python hex_to_cid.py <hex_string>")
        print("Example: python hex_to_cid.py 0037b16551c32070469ac310343f99ae2779ccbe6be106115f7cdfcfd3d0b859e65")
        sys.exit(1)
    
    # Remove all whitespace from input
    hex_input = ''.join(sys.argv[1].split())
    
    try:
        cid = hex_to_cidv0(hex_input)
        print(cid)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

