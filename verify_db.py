#!/usr/bin/env python3
"""Quick verification script to check DB content matches expected format"""
import sqlite3

db_path = "cid_tokens.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check token 1 specifically
cursor.execute(
    "SELECT cid, content, token_level, token_number FROM cid_tokens WHERE token_level=3 AND token_number=1"
)
row = cursor.fetchone()

if row:
    cid, content, level, num = row
    print(f"Token Level {level}, Number {num}:")
    print(f"  CID: {cid}")
    print(f"  Content: {content}")
    print(f"  Content length: {len(content)}")
    print(f"  Expected format: 003 + 64-char hash")
    print(f"  Content starts with level: {content[:3]}")
    print(f"  Hash part: {content[3:]}")
    print(f"  Hash length: {len(content[3:])}")
else:
    print("Token not found in DB")

conn.close()
