#!/usr/bin/env python3
"""High-performance HTTP API: given a CID, return token content from SQLite cache.

Optimized for high throughput (100k+ requests):
- Thread-local DB connections
- SQLite WAL mode for read concurrency
- In-memory caching for hot CIDs
- Batch lookup endpoint for bulk requests
- Production-ready with Gunicorn

Endpoints:
  GET /token/<cid>
    - 200: {"cid": "...", "content": "...", "token_level": 3, "token_number": 1423543}
    - 404: {"error": "not_found"}
  
  POST /tokens/batch
    - Body: {"cids": ["Qm...", "Qm...", ...]}
    - 200: {"results": {"Qm...": {...}, ...}, "not_found": ["Qm...", ...]}
"""

from flask import Flask, jsonify, request
from functools import lru_cache
import os

# Optional Swagger documentation
try:
    from flasgger import Swagger
    SWAGGER_AVAILABLE = True
except ImportError:
    SWAGGER_AVAILABLE = False
    # Swagger is optional - API works without it

from cid_cache_db import get_content_by_cid, get_content_by_cids_batch, init_db

app = Flask(__name__)

# Add Swagger documentation if available
if SWAGGER_AVAILABLE:
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/apispec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/api-docs"
    }
    
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Rubix Token CID API",
            "description": "High-performance API for looking up token content by IPFS CID",
            "version": "1.0.0"
        },
        "basePath": "/",
    }
    
    swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Initialize DB on startup
init_db()

# In-memory cache for frequently accessed CIDs (LRU cache, max 10k entries)
# This helps with hot CIDs that are requested repeatedly
@lru_cache(maxsize=10000)
def _cached_get_content(cid: str):
    """Cached wrapper for get_content_by_cid. Returns tuple or None."""
    result = get_content_by_cid(cid)
    # Convert to hashable tuple for caching (None is hashable)
    if result:
        return tuple(result)  # Make it hashable
    return None


@app.get("/token/<cid>")
def get_token(cid: str):
    """
    Get token content by CID.
    ---
    tags:
      - Tokens
    parameters:
      - name: cid
        in: path
        type: string
        required: true
        description: IPFS CID (Qm... format)
        example: QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH
    responses:
      200:
        description: Token found
        schema:
          type: object
          properties:
            cid:
              type: string
            content:
              type: string
            token_level:
              type: integer
            token_number:
              type: integer
        example:
          cid: QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH
          content: "003841d04a85612adb1ca95d86e08561eb1dcc9608899a57b59d57c565d796bb106"
          token_level: 3
          token_number: 1423543
      404:
        description: Token not found
        schema:
          type: object
          properties:
            error:
              type: string
            cid:
              type: string
    """
    # Use cached lookup (LRU cache handles hot CIDs)
    row = _cached_get_content(cid)
    if not row:
        return jsonify({"error": "not_found", "cid": cid}), 404

    # Unpack tuple result
    content, token_level, token_number = row
    return jsonify(
        {
            "cid": cid,
            "content": content,
            "token_level": token_level,
            "token_number": token_number,
        }
    )


@app.post("/tokens/batch")
def get_tokens_batch():
    """
    Batch lookup for multiple CIDs.
    ---
    tags:
      - Tokens
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - cids
          properties:
            cids:
              type: array
              items:
                type: string
              description: Array of IPFS CIDs to lookup
              example: ["QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH", "QmasEKK2g6rBEW3yHFMMF4JSeTUHEoSGoQc1CLkD84f9HN"]
    responses:
      200:
        description: Batch lookup results
        schema:
          type: object
          properties:
            results:
              type: object
              description: Dictionary mapping CID to token info
            not_found:
              type: array
              items:
                type: string
              description: Array of CIDs that were not found
            total_requested:
              type: integer
            total_found:
              type: integer
            total_not_found:
              type: integer
      400:
        description: Bad request (invalid input)
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    if not data or "cids" not in data:
        return jsonify({"error": "Missing 'cids' field in request body"}), 400
    
    cids = data.get("cids", [])
    
    # Validate input
    if not isinstance(cids, list):
        return jsonify({"error": "'cids' must be an array"}), 400
    
    if len(cids) == 0:
        return jsonify({"results": {}, "not_found": []}), 200
    
    # Limit batch size to prevent abuse (adjust as needed)
    MAX_BATCH_SIZE = 10000
    if len(cids) > MAX_BATCH_SIZE:
        return jsonify({
            "error": f"Batch size exceeds maximum of {MAX_BATCH_SIZE}",
            "received": len(cids)
        }), 400
    
    # Remove duplicates while preserving order
    seen = set()
    unique_cids = []
    for cid in cids:
        if cid not in seen:
            seen.add(cid)
            unique_cids.append(cid)
    
    # Batch lookup (single database query)
    results_dict = get_content_by_cids_batch(unique_cids)
    
    # Format results
    results = {}
    not_found = []
    
    for cid in unique_cids:
        if cid in results_dict:
            content, token_level, token_number = results_dict[cid]
            results[cid] = {
                "cid": cid,
                "content": content,
                "token_level": token_level,
                "token_number": token_number,
            }
        else:
            not_found.append(cid)
    
    return jsonify({
        "results": results,
        "not_found": not_found,
        "total_requested": len(cids),
        "total_found": len(results),
        "total_not_found": len(not_found)
    }), 200


@app.get("/health")
def health():
    """
    Health check endpoint.
    ---
    tags:
      - System
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
    """
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # For development: single-threaded Flask server
    # For production: use Gunicorn (see instructions below)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

