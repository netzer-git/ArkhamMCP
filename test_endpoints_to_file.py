import asyncio
import httpx
import json
import sys
from datetime import datetime

# Output file for results
results_file = "test_results.txt"

# Base URL for the server
BASE_URL = "http://localhost:8000"

async def test_endpoint(url, description, params=None):
    """Test a specific endpoint and write results to file"""
    with open(results_file, "a") as f:
        f.write(f"\n\n--- Testing {description} ---\n")
        f.write(f"URL: {url}\n")
        if params:
            f.write(f"Params: {params}\n")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if params:
                    resp = await client.get(url, params=params)
                else:
                    resp = await client.get(url)
                
                f.write(f"Status Code: {resp.status_code}\n")
                
                if resp.status_code == 200:
                    # For JSON responses
                    try:
                        data = resp.json()
                        if isinstance(data, list):
                            f.write(f"Response: List with {len(data)} items\n")
                            if data and len(data) > 0:
                                sample = json.dumps(data[0], indent=2)
                                f.write(f"Sample item:\n{sample[:500]}...\n")
                        else:
                            sample = json.dumps(data, indent=2)
                            f.write(f"Response:\n{sample[:500]}...\n")
                    except json.JSONDecodeError:
                        # For HTML or text responses
                        f.write(f"Response (non-JSON):\n{resp.text[:500]}...\n")
                else:
                    f.write(f"Error response: {resp.text}\n")
                
                return resp.status_code == 200
        except Exception as e:
            f.write(f"Exception occurred: {str(e)}\n")
            return False

async def main():
    # Initialize results file
    with open(results_file, "w") as f:
        f.write(f"Arkham Horror MCP Server Test Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*50 + "\n")
    
    # Test 1: Root endpoint
    await test_endpoint(f"{BASE_URL}/", "Root endpoint")
    
    # Test 2: Scenarios list
    scenarios_ok = await test_endpoint(f"{BASE_URL}/scenarios", "Scenarios list")
    
    # If scenarios endpoint worked, get a sample ID for detail test
    sample_id = None
    if scenarios_ok:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE_URL}/scenarios")
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        sample_id = data[0].get('id')
        except:
            pass
    
    # Test 3: Scenario detail (if we have an ID)
    if sample_id:
        await test_endpoint(f"{BASE_URL}/scenarios/{sample_id}", f"Scenario detail for {sample_id}")
    
    # Test 4: Cards endpoint
    await test_endpoint(f"{BASE_URL}/cards", "Cards list")
    
    # Test 5: Basic scenario search
    await test_endpoint(f"{BASE_URL}/search", "Basic scenario search", {"type": "scenario"})
    
    # Test 6: Fuzzy scenario search
    await test_endpoint(f"{BASE_URL}/search", "Fuzzy scenario search", 
                        {"type": "scenario", "name": "arkham", "fuzzy": "true"})
    
    # Test 7: Player count filtered search
    await test_endpoint(f"{BASE_URL}/search", "Player count filtered search", 
                        {"type": "scenario", "min_players": "2", "max_players": "4"})
    
    # Test 8: Card search
    await test_endpoint(f"{BASE_URL}/search", "Card search", 
                        {"type": "card", "name": "shotgun"})
    
    # Test 9: Investigator search with faction
    await test_endpoint(f"{BASE_URL}/search", "Investigator search with faction", 
                        {"type": "investigator", "faction": "guardian"})
    
    with open(results_file, "a") as f:
        f.write("\n\nTesting completed!\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print(f"Tests completed. Results written to {results_file}")
    except KeyboardInterrupt:
        print("Testing interrupted by user.")
    except Exception as e:
        print(f"Error running tests: {e}")
        with open(results_file, "a") as f:
            f.write(f"\nError running tests: {e}\n")
