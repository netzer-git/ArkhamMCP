from fastapi import FastAPI, Query, HTTPException
from starlette.responses import PlainTextResponse, HTMLResponse
import logging
from typing import Optional, List, Dict, Any
import re
from difflib import SequenceMatcher

import asyncio
import httpx
from bs4 import BeautifulSoup

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()
server = Server("arkham-horror-mcp")

# In-memory cache for scenarios
cached_scenarios: List[Dict[str, Any]] = []
cache_lock = asyncio.Lock()
SCENARIO_LIST_URL = "https://arkhamcentral.com/index.php/fan-created-content-arkham-horror-lcg/"
AH_LCG_URL = "https://arkhamdb.com/api/public/"

# Function to calculate similarity between two strings
def similarity(a, b):
    """Calculate string similarity ratio between 0 and 1"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

@app.get("/")
def root():
    return PlainTextResponse("Arkham Horror MCP server is running.")


async def get_cached_scenarios() -> list[dict]:
    """Gets scenarios from cache or fetches them if cache is empty."""
    async with cache_lock:
        if not cached_scenarios:
            logging.info("Cache empty, fetching scenarios from ArkhamCentral...")
            try:
                fetched = await fetch_arkham_scenarios_internal()
                # Simple validation: ensure basic structure
                if fetched and all('id' in s and 'title' in s and 'url' in s for s in fetched):
                    cached_scenarios.extend(fetched)
                    logging.info(f"Fetched and cached {len(cached_scenarios)} scenarios.")
                else:
                    logging.warning("Fetched data did not contain expected scenario structure. Cache remains empty.")
                    return [] # Return empty if fetch failed or data invalid
            except Exception as e:
                logging.exception("Failed to fetch scenarios")
                # Return empty list on failure
                return []
        else:
            logging.info(f"Returning {len(cached_scenarios)} scenarios from cache.")
        return cached_scenarios

async def fetch_arkham_scenarios_internal() -> list[dict]:
    """
    Internal function to fetch Arkham Horror scenarios from arkhamcentral.com.
    Attempts a more specific selector.
    Returns a list of dicts with 'id', 'title', 'description', and 'url'.
    """
    scenarios = []
    try:
        # Use a longer timeout as the page might be slow
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            logging.info(f"Fetching scenario list from {SCENARIO_LIST_URL}")
            resp = await client.get(SCENARIO_LIST_URL)
            resp.raise_for_status() # Raise HTTP errors (4xx, 5xx)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Target the main content area where scenario links are expected
            # This selector might need adjustment if the website structure changes.
            content_area = soup.select_one(".entry-content")
            if not content_area:
                logging.warning(f"Could not find '.entry-content' on {SCENARIO_LIST_URL}. Scraping might fail.")
                # Fallback to searching the whole body, though less reliable
                content_area = soup

            links_found = 0
            for link in content_area.find_all("a", href=True): # Ensure link has href
                href = link["href"]
                title = link.get_text(strip=True)

                # Filter links: must be on the same domain, have a title, and not be the list page itself
                # Also check if it looks like a scenario page path
                if href.startswith("https://arkhamcentral.com/index.php/") and title and href != SCENARIO_LIST_URL:
                    links_found += 1
                    # Basic check if path seems valid (avoids short/irrelevant links)
                    if len(href.split('/')) > 4:
                        # Generate a simple ID from the last part of the URL path (slug)
                        path_parts = [part for part in href.split("/") if part and part != 'index.php']
                        scenario_id = path_parts[-1] if path_parts else href # Use slug or full href as fallback ID
                        
                        # Extract any available metadata like player count, difficulty, etc.
                        metadata = {}
                        # Look for common patterns like "1-4 players" or "Easy/Standard"
                        player_count_match = re.search(r'(\d+)[-–](\d+)\s+players?', title, re.IGNORECASE)
                        if player_count_match:
                            metadata['min_players'] = int(player_count_match.group(1))
                            metadata['max_players'] = int(player_count_match.group(2))
                        
                        difficulty_match = re.search(r'(easy|standard|hard|expert)', title, re.IGNORECASE)
                        if difficulty_match:
                            metadata['difficulty'] = difficulty_match.group(1).lower()

                        scenarios.append({
                            "id": scenario_id,
                            "title": title,
                            "description": f"Fan-created Arkham Horror scenario: {title}",
                            "url": href,
                            "source": "arkhamcentral",
                            "metadata": metadata
                        })

            logging.info(f"Found {links_found} potential links in content area, extracted {len(scenarios)} scenarios.")

    except httpx.TimeoutException:
        logging.error(f"Timeout occurred while fetching scenarios from {SCENARIO_LIST_URL}")
        raise # Re-raise to indicate failure
    except httpx.RequestError as exc:
        logging.error(f"HTTP error occurred while fetching scenarios: {exc}")
        raise # Re-raise after logging
    except Exception as e:
        logging.exception(f"An unexpected error occurred during scenario fetching: {e}")
        raise # Re-raise after logging

    if not scenarios:
        # This is important feedback if scraping stops working
        logging.warning(f"No scenarios extracted from {SCENARIO_LIST_URL}. Check CSS selectors or page structure.")

    return scenarios

async def fetch_arkhamdb_cards(card_type=None) -> List[Dict[str, Any]]:
    """
    Fetch card information from ArkhamDB API.
    This provides access to official cards from the Arkham Horror LCG.
    """
    cards = []
    try:
        endpoint = "cards"
        url = f"{AH_LCG_URL}{endpoint}"
        
        if card_type:
            url = f"{url}?type_code={card_type}"
            
        logging.info(f"Fetching cards from ArkhamDB API: {url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
            data = resp.json()
            for card in data:
                cards.append({
                    "id": card.get("code", "unknown"),
                    "name": card.get("name", "Unknown Card"),
                    "type": card.get("type_name", "Unknown"),
                    "subtype": card.get("subtype_name", ""),
                    "faction": card.get("faction_name", "Neutral"),
                    "pack": card.get("pack_name", "Unknown"),
                    "text": card.get("text", ""),
                    "cost": card.get("cost", None),
                    "source": "arkhamdb"
                })
                
        logging.info(f"Fetched {len(cards)} cards from ArkhamDB")
        return cards
    except Exception as e:
        logging.exception(f"Error fetching cards from ArkhamDB: {e}")
        return []

async def fetch_scenario_detail(scenario_url: str) -> str:
    """
    Fetch the HTML content for a specific scenario from its direct URL.
    Attempts to extract the main content area.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            logging.info(f"Fetching scenario detail from {scenario_url}")
            resp = await client.get(scenario_url)
            resp.raise_for_status() # Raise HTTP errors
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to extract main content - '.entry-content' is common in WordPress themes
            # This selector is crucial and might need adjustment per scenario or site changes.
            main_content = soup.select_one(".entry-content")
            if main_content:
                logging.info(f"Successfully extracted '.entry-content' from {scenario_url}")
                
                # Extract additional metadata if available
                metadata = {}
                
                # Look for common patterns in the content that might indicate metadata
                text_content = main_content.get_text()
                
                # Extract player count if available
                player_count_match = re.search(r'(\d+)[-–](\d+)\s+players?', text_content, re.IGNORECASE)
                if player_count_match:
                    metadata['min_players'] = int(player_count_match.group(1))
                    metadata['max_players'] = int(player_count_match.group(2))
                
                # Extract difficulty if available
                difficulty_match = re.search(r'Difficulty:\s*(easy|standard|hard|expert)', text_content, re.IGNORECASE)
                if difficulty_match:
                    metadata['difficulty'] = difficulty_match.group(1).lower()
                
                # Extract playtime if available
                playtime_match = re.search(r'(\d+)[-–](\d+)\s+minutes', text_content, re.IGNORECASE)
                if playtime_match:
                    metadata['min_time'] = int(playtime_match.group(1))
                    metadata['max_time'] = int(playtime_match.group(2))
                
                # Add metadata as a comment at the top of the HTML for later extraction if needed
                metadata_html = f"<!-- Extracted Metadata: {str(metadata)} -->\n"
                
                # Return the HTML content of the selected element as a string with metadata
                return metadata_html + str(main_content)
            else:
                logging.warning(f"Could not find '.entry-content' on {scenario_url}. Returning full body HTML as fallback.")
                # Fallback to returning the whole body if specific content not found
                return resp.text
    except httpx.TimeoutException:
        logging.error(f"Timeout occurred while fetching scenario detail from {scenario_url}")
        # Return an error message embedded in HTML for clarity
        return f"<html><body><h1>Error</h1><p>Timeout occurred while fetching content from {scenario_url}.</p></body></html>"
    except httpx.RequestError as exc:
        logging.error(f"HTTP error occurred while fetching scenario detail from {scenario_url}: {exc}")
        # Return an error message embedded in HTML
        return f"<html><body><h1>Error</h1><p>Could not fetch content from {scenario_url}: {exc}</p></body></html>"
    except Exception as e:
        logging.exception(f"An unexpected error occurred fetching detail from {scenario_url}: {e}")
        # Return a generic error message embedded in HTML
        return f"<html><body><h1>Error</h1><p>An unexpected error occurred while fetching content.</p></body></html>"


# --- MCP Handlers ---

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available Arkham Horror scenarios from arkhamcentral.com as resources.
    Uses cached data.
    """
    scenarios = await get_cached_scenarios()
    resources = []
    for s in scenarios:
        try:
            # Ensure the URI is valid before creating the resource
            uri = AnyUrl(f"arkham://scenario/{s.get('id', 'unknown')}", scheme="arkham")
            resources.append(
                types.Resource(
                    uri=uri,
                    name=s.get('title', 'Unknown Title'),
                    description=s.get('description', 'No description available.'),
                    mimeType="text/html", # Content is HTML from the detail page
                )
            )
        except ValueError as e:
            logging.warning(f"Skipping scenario due to invalid URI data: {s}. Error: {e}")
    return resources


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific Arkham Horror scenario's content by its URI.
    Looks up the scenario URL from the cache and fetches the detail page.
    """
    logging.info(f"Handling read_resource request for URI: {uri}")
    if uri.scheme == "arkham" and uri.path and uri.path.startswith("/scenario/"):
        scenario_id = uri.path.split("/scenario/")[-1]
        if not scenario_id:
             logging.error(f"Invalid scenario ID extracted from URI: {uri}")
             raise ValueError(f"Invalid scenario ID in URI: {uri}")

        logging.info(f"Attempting to read resource for scenario ID: {scenario_id}")
        scenarios = await get_cached_scenarios()
        scenario_data = next((s for s in scenarios if s.get("id") == scenario_id), None)

        if scenario_data and "url" in scenario_data:
            logging.info(f"Found scenario {scenario_id} in cache. Fetching detail from {scenario_data['url']}")
            # Fetch the actual HTML content from the scenario's page
            html_content = await fetch_scenario_detail(scenario_data["url"])
            return html_content # Return the fetched HTML string
        else:
            logging.error(f"Scenario ID '{scenario_id}' not found in cache or missing URL.")
            # Raise a more specific error for MCP context if needed, ValueError is standard
            raise ValueError(f"Scenario with ID '{scenario_id}' not found or has no associated URL.")
    else:
        logging.warning(f"Unsupported URI received in read_resource: {uri}")
        raise ValueError(f"Unsupported URI scheme or path: {uri}")


# --- Demo Prompt/Tool Handlers (Keep as-is or adapt/remove) ---
# In-memory notes storage for prompt/tool demo
notes = {}

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """List available prompts (demo)."""
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """Generate a prompt (demo)."""
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""
    notes_text = "\n".join(f"- {n}: {c}" for n, c in notes.items()) if notes else "No notes available."

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n{notes_text}",
                ),
            )
        ],
    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools (demo)."""
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the note"},
                    "content": {"type": "string", "description": "Content of the note"},
                },
                "required": ["name", "content"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests (demo)."""
    if name != "add-note":
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments for add-note tool")

    note_name = arguments.get("name")
    content = arguments.get("content")

    if not note_name or not isinstance(note_name, str) or not content or not isinstance(content, str):
        raise ValueError("Invalid or missing 'name' or 'content' argument for add-note tool")

    # Update server state
    notes[note_name] = content
    logging.info(f"Added/Updated note: '{note_name}'")

    # Notify clients that resources might have changed (if notes were resources)
    # await server.request_context.session.send_resource_list_changed() # Uncomment if notes affect resources

    return [
        types.TextContent(
            type="text",
            text=f"Added note '{note_name}'.",
        )
    ]

# --- Main Execution & FastAPI Endpoints ---

async def main():
    # Pre-populate cache on startup (optional, can be done lazily on first request)
    logging.info("Attempting to pre-populate scenario cache on startup...")
    await get_cached_scenarios()
    logging.info("Startup cache population attempt complete.")

    # Run the MCP server using stdin/stdout streams
    logging.info("Starting MCP server via stdio...")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="arkham-horror-mcp",
                server_version="0.1.2", # Incremented version
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
    logging.info("MCP server finished.")


# --- FastAPI Endpoints (for testing/direct access) ---

@app.get("/scenarios", response_model=List[Dict[str, Any]])
async def get_scenarios_endpoint():
    """FastAPI endpoint to list cached Arkham Horror scenarios."""
    try:
        scenarios = await get_cached_scenarios()
        return scenarios
    except Exception as e:
        logging.exception("Error in /scenarios endpoint")
        # Use HTTPException for standard FastAPI error responses
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def get_scenario_detail_endpoint(scenario_id: str):
    """FastAPI endpoint to get scenario HTML content via ID lookup."""
    scenarios = await get_cached_scenarios()
    scenario_data = next((s for s in scenarios if s.get("id") == scenario_id), None)

    if scenario_data and "url" in scenario_data:
        try:
            html_content = await fetch_scenario_detail(scenario_data["url"])
            # Return HTML content directly with appropriate media type
            return HTMLResponse(content=html_content, status_code=200)
        except Exception as e:
            logging.exception(f"Error fetching detail for scenario ID {scenario_id} in endpoint")
            raise HTTPException(status_code=500, detail=f"Error fetching scenario detail: {e}")
    else:
        logging.warning(f"Scenario ID '{scenario_id}' not found in /scenarios/{scenario_id} endpoint.")
        raise HTTPException(status_code=404, detail=f"Scenario ID '{scenario_id}' not found")

@app.get("/cards", response_model=List[Dict[str, Any]])
async def get_cards_endpoint(
    type: Optional[str] = Query(None, description="Filter by card type (e.g., 'investigator', 'asset', 'event')")
):
    """
    FastAPI endpoint to fetch cards from ArkhamDB.
    Provides access to official Arkham Horror LCG cards.
    """
    try:
        cards = await fetch_arkhamdb_cards(type)
        if not cards:
            return []
        return cards
    except Exception as e:
        logging.exception("Error in /cards endpoint")
        raise HTTPException(status_code=500, detail=f"Error fetching cards: {e}")

@app.get("/search", response_model=List[Dict[str, Any]])
async def search_arkham_endpoint(
    type: str = Query(..., description="Type of object: scenario, card, investigator"),
    name: Optional[str] = Query(None, description="Name or partial name to search for"),
    min_players: Optional[int] = Query(None, description="Minimum number of players (scenarios only)"),
    max_players: Optional[int] = Query(None, description="Maximum number of players (scenarios only)"),
    difficulty: Optional[str] = Query(None, description="Difficulty level (scenarios only)"),
    fuzzy: Optional[bool] = Query(False, description="Enable fuzzy matching for name searches"),
    min_similarity: Optional[float] = Query(0.6, description="Minimum similarity score for fuzzy matching (0-1)"),
    faction: Optional[str] = Query(None, description="Card faction (cards only)")
):
    """
    Enhanced search endpoint for Arkham Horror LCG objects.
    Supports searching scenarios from ArkhamCentral and cards from ArkhamDB.
    Features filtering by various attributes and fuzzy matching.
    """
    results = []
    search_type = type.lower()  # Normalize type

    # Scenario search (from ArkhamCentral)
    if search_type == "scenario":
        scenarios = await get_cached_scenarios()
        filtered_scenarios = scenarios
        
        # Apply filters
        if name:
            if fuzzy:
                # Fuzzy matching based on string similarity
                name_matches = []
                for s in filtered_scenarios:
                    title = s.get("title", "").lower()
                    sim_score = similarity(name, title)
                    if sim_score >= min_similarity:
                        s["similarity"] = round(sim_score, 2)  # Add similarity score to results
                        name_matches.append(s)
                filtered_scenarios = name_matches
            else:
                # Standard substring search
                name_lower = name.lower()
                filtered_scenarios = [s for s in filtered_scenarios if name_lower in s.get("title", "").lower()]
        
        # Filter by player count if specified
        if min_players is not None:
            filtered_scenarios = [
                s for s in filtered_scenarios 
                if "metadata" in s and "min_players" in s["metadata"] and s["metadata"]["min_players"] >= min_players
            ]
        
        if max_players is not None:
            filtered_scenarios = [
                s for s in filtered_scenarios 
                if "metadata" in s and "max_players" in s["metadata"] and s["metadata"]["max_players"] <= max_players
            ]
        
        # Filter by difficulty if specified
        if difficulty:
            filtered_scenarios = [
                s for s in filtered_scenarios
                if "metadata" in s and "difficulty" in s["metadata"] and s["metadata"]["difficulty"].lower() == difficulty.lower()
            ]
        
        # Sort by similarity if fuzzy search was used
        if fuzzy and name:
            filtered_scenarios.sort(key=lambda s: s.get("similarity", 0), reverse=True)
            
        results = filtered_scenarios
        logging.info(f"Scenario search for '{name}' found {len(results)} results with applied filters.")
            
    # Card search (from ArkhamDB)
    elif search_type in ["card", "investigator"]:
        try:
            # For investigator type, use that as the card type filter
            card_type = "investigator" if search_type == "investigator" else None
            cards = await fetch_arkhamdb_cards(card_type)
            
            if not cards:
                return [{
                    "error": f"No {search_type} data available from ArkhamDB.",
                    "type": search_type,
                    "name_query": name
                }]
                
            filtered_cards = cards
            
            # Apply name filter if specified
            if name:
                if fuzzy:
                    # Fuzzy matching for card names
                    name_matches = []
                    for card in filtered_cards:
                        card_name = card.get("name", "")
                        sim_score = similarity(name, card_name)
                        if sim_score >= min_similarity:
                            card["similarity"] = round(sim_score, 2)
                            name_matches.append(card)
                    filtered_cards = name_matches
                else:
                    # Standard substring search
                    name_lower = name.lower()
                    filtered_cards = [c for c in filtered_cards if name_lower in c.get("name", "").lower()]
            
            # Apply faction filter if specified
            if faction:
                faction_lower = faction.lower()
                filtered_cards = [c for c in filtered_cards if faction_lower in c.get("faction", "").lower()]
                
            # Sort by similarity if fuzzy search was used
            if fuzzy and name:
                filtered_cards.sort(key=lambda c: c.get("similarity", 0), reverse=True)
                
            results = filtered_cards
            logging.info(f"Card search for '{name}' found {len(results)} results with applied filters.")
            
        except Exception as e:
            logging.exception(f"Error searching for {search_type}: {e}")
            results = [{
                "error": f"Error searching for {search_type}: {str(e)}",
                "type": search_type,
                "name_query": name
            }]
    else:
        logging.warning(f"Search attempted for unknown type: {type}")
        results = [{"error": f"Unknown search type: '{type}'. Supported types: 'scenario', 'card', 'investigator'."}]

    # Implement pagination for large result sets
    # This is a simple implementation that could be extended
    limit = 50  # Maximum results to return
    if len(results) > limit:
        results = results[:limit]
        logging.info(f"Search results truncated to {limit} items. Consider adding pagination parameters.")
    
    return results

# Add logic to run the main MCP server loop if the script is executed directly
# This is usually handled by the MCP runner, but can be useful for testing.
if __name__ == "__main__":
    # Note: Running FastAPI app and MCP server simultaneously might require
    # careful process management or running them separately.
    # This example focuses on the MCP part.
    # To run FastAPI: uvicorn src.arkham_horror_mcp.server:app --reload
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user.")