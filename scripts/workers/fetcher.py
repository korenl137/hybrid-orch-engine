import httpx
import json
import sys
import os
from typing import List, Dict

def fetch_content(urls: List[str]) -> List[Dict[str, str]]:
    results = []
    # Using a session for connection pooling
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for url in urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                # Basic cleaning of HTML tags (simplified for now)
                content = response.text.replace("<", " ").replace(">", " ").replace("\n", " ")
                results.append({
                    "source_url": url,
                    "raw_content": content[:5000],  # Limit length to prevent context overflow
                    "title": "Fetched Content"
                })
            except Exception as e:
                results.append({
                    "source_url": url,
                    "raw_content": f"Error fetching: {str(e)}",
                    "title": "Error"
                })
    return results

if __name__ == "__main__":
    # Expecting a JSON list of URLs as input from stdin or argument
    input_data = sys.argv[1] if len(sys.argv) > 1 else ""
    if input_data:
        urls = json.loads(input_data)
        results = fetch_content(urls)
        print(json.dumps(results, indent=2))
    else:
        print(json.dumps([], indent=2))
