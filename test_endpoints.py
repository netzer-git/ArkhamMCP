import asyncio
import httpx
import json
from typing import Dict, Any, List, Optional
import sys

BASE_URL = "http://localhost:8000"

async def test_root():
    """Test the root endpoint"""
    print("Testing root endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/")
            print(f"Status Code: {resp.status_code}")
            print(f"Content: {resp.text}")
            return resp.status_code == 200
    except Exception as e:
        print(f"Error testing root endpoint: {e}")
        return False

async def test_scenarios():
    """Test the scenarios endpoint"""
    print("\nTesting scenarios endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/scenarios")
            print(f"Status Code: {resp.status_code}")
            
            if resp.status_code == 200:
                scenarios = resp.json()
                print(f"Found {len(scenarios)} scenarios")
                # Print the first scenario as a sample
                if scenarios:
                    print(f"Sample scenario: {json.dumps(scenarios[0], indent=2)}")
                
                # Return the first scenario ID for later testing
                return True, scenarios[0]['id'] if scenarios else None
            else:
                print(f"Error: {resp.text}")
                return False, None
    except Exception as e:
        print(f"Error testing scenarios endpoint: {e}")
        return False, None

async def test_scenario_detail(scenario_id: str):
    """Test getting details for a specific scenario"""
    print(f"\nTesting scenario detail for {scenario_id}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/scenarios/{scenario_id}")
            print(f"Status Code: {resp.status_code}")
            
            if resp.status_code == 200:
                # For HTML content, print a snippet
                print(f"Content snippet: {resp.text[:200]}...")
                return True
            else:
                print(f"Error: {resp.text}")
                return False
    except Exception as e:
        print(f"Error testing scenario detail: {e}")
        return False

async def test_cards():
    """Test the cards endpoint"""
    print("\nTesting cards endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/cards")
            print(f"Status Code: {resp.status_code}")
            
            if resp.status_code == 200:
                cards = resp.json()
                print(f"Found {len(cards)} cards")
                # Print the first card as a sample
                if cards:
                    print(f"Sample card: {json.dumps(cards[0], indent=2)}")
                return True
            else:
                print(f"Error: {resp.text}")
                return False
    except Exception as e:
        print(f"Error testing cards endpoint: {e}")
        return False

async def test_search_scenarios():
    """Test searching for scenarios"""
    print("\nTesting scenario search...")
    try:
        async with httpx.AsyncClient() as client:
            # Basic search
            resp = await client.get(f"{BASE_URL}/search?type=scenario")
            print(f"Basic search status: {resp.status_code}")
            if resp.status_code == 200:
                results = resp.json()
                print(f"Found {len(results)} scenarios in basic search")
            
            # Fuzzy search
            resp = await client.get(f"{BASE_URL}/search?type=scenario&name=arkham&fuzzy=true")
            print(f"Fuzzy search status: {resp.status_code}")
            if resp.status_code == 200:
                results = resp.json()
                print(f"Found {len(results)} scenarios in fuzzy search for 'arkham'")
                
            # Filtered search by player count
            resp = await client.get(f"{BASE_URL}/search?type=scenario&min_players=2&max_players=4")
            print(f"Player count filter status: {resp.status_code}")
            if resp.status_code == 200:
                results = resp.json()
                print(f"Found {len(results)} scenarios for 2-4 players")
                
            return True
    except Exception as e:
        print(f"Error testing scenario search: {e}")
        return False

async def test_search_cards():
    """Test searching for cards"""
    print("\nTesting card search...")
    try:
        async with httpx.AsyncClient() as client:
            # Basic card search
            resp = await client.get(f"{BASE_URL}/search?type=card&name=shotgun")
            print(f"Card search status: {resp.status_code}")
            if resp.status_code == 200:
                results = resp.json()
                print(f"Found {len(results)} cards matching 'shotgun'")
                
            # Investigator search with faction
            resp = await client.get(f"{BASE_URL}/search?type=investigator&faction=guardian")
            print(f"Investigator search status: {resp.status_code}")
            if resp.status_code == 200:
                results = resp.json()
                print(f"Found {len(results)} guardian investigators")
                
            return True
    except Exception as e:
        print(f"Error testing card search: {e}")
        return False

async def main():
    print("Starting Arkham Horror MCP server tests...\n")
    
    # Test root endpoint
    root_ok = await test_root()
    if not root_ok:
        print("Root endpoint test failed. Server may not be running.")
        return
        
    # Test scenarios endpoint
    scenarios_ok, sample_id = await test_scenarios()
    if not scenarios_ok:
        print("Scenarios endpoint test failed.")
    
    # Test scenario detail if we have a sample ID
    if sample_id:
        await test_scenario_detail(sample_id)
    
    # Test cards endpoint
    await test_cards()
    
    # Test search functionality
    await test_search_scenarios()
    await test_search_cards()
    
    print("\nAll tests completed.")

if __name__ == "__main__":
    asyncio.run(main())
