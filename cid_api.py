#!/usr/bin/env python3
"""Simple HTTP API: given a CID, return token content from SQLite cache.

Endpoint:
  GET /token/<cid>
    - 200: {"cid": "...", "content": "...", "token_level": 3, "token_number": 1423543}
    - 404: {"error": "not_found"}
"""

from flask import Flask, jsonify

from cid_cache_db import get_content_by_cid, init_db

app = Flask(__name__)

# Initialize DB on startup
init_db()


@app.get("/token/<cid>")
def get_token(cid: str):
    row = get_content_by_cid(cid)
    if not row:
        return jsonify({"error": "not_found", "cid": cid}), 404

    content, token_level, token_number = row
    return jsonify(
        {
            "cid": cid,
            "content": content,
            "token_level": token_level,
            "token_number": token_number,
        }
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Run on localhost:5000 by default
    app.run(host="0.0.0.0", port=5000, debug=False)

