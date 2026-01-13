#!/usr/bin/env python3
"""Test script for batch API endpoint."""

import requests
import json
import time

API_URL = "http://localhost:5000"

def test_batch_api():
    """Test the batch lookup endpoint."""
    
    # Example CIDs (replace with real ones from your DB)
    cids = [
        "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH",
        "QmasEKK2g6rBEW3yHFMMF4JSeTUHEoSGoQc1CLkD84f9HN",
        "QmU45auDK9F2686WzrJ4LRUqP34YagBEjsEJFtvc4UFEL7",
        "QmInvalidCID123456789",  # This one won't be found
    ]
    
    print(f"Testing batch lookup with {len(cids)} CIDs...")
    
    # Prepare request
    payload = {"cids": cids}
    
    # Make batch request
    start_time = time.time()
    response = requests.post(
        f"{API_URL}/tokens/batch",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    elapsed = time.time() - start_time
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Time: {elapsed:.3f} seconds")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResults:")
        print(f"  Total Requested: {data['total_requested']}")
        print(f"  Total Found: {data['total_found']}")
        print(f"  Total Not Found: {data['total_not_found']}")
        
        print(f"\nFound CIDs:")
        for cid, info in data['results'].items():
            print(f"  {cid}:")
            print(f"    Content: {info['content'][:50]}...")
            print(f"    Level: {info['token_level']}, Number: {info['token_number']}")
        
        if data['not_found']:
            print(f"\nNot Found CIDs:")
            for cid in data['not_found']:
                print(f"  {cid}")
    else:
        print(f"Error: {response.text}")


def test_performance():
    """Test performance with larger batch."""
    
    # Get some CIDs from your database first
    # For this example, we'll use a smaller batch
    cids = [
        "QmfYNyAyGD8xHE9XgctX8WnfJ627edkM2EkAcijEutoJmH",
    ] * 100  # 100 requests for the same CID
    
    print(f"\nPerformance test: {len(cids)} CIDs...")
    
    payload = {"cids": cids}
    
    start_time = time.time()
    response = requests.post(
        f"{API_URL}/tokens/batch",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        data = response.json()
        print(f"Processed {len(cids)} CIDs in {elapsed:.3f} seconds")
        print(f"Rate: {len(cids)/elapsed:.0f} CIDs/second")


if __name__ == "__main__":
    print("=== Batch API Test ===\n")
    
    # Test basic functionality
    test_batch_api()
    
    # Test performance
    # test_performance()

