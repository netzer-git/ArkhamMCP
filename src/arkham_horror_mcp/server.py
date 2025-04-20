from fastapi import FastAPI, Query
from starlette.responses import PlainTextResponse
import logging
from typing import Optional

app = FastAPI()

@app.get("/")
def root():
    return PlainTextResponse("Arkham Horror MCP server is running.")

import asyncio
import httpx
from bs4 import BeautifulSoup

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

server = Server("arkham-horror-mcp")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available Arkham Horror scenarios from arkhamcentral.com as resources.
    """
    scenarios = await fetch_arkham_scenarios()
    return [
        types.Resource(
            uri=AnyUrl(f"arkham://scenario/{s['id']}", scheme="arkham"),
            name=s['title'],
            description=s['description'],
            mimeType="text/html",
        )
        for s in scenarios
    ]

async def fetch_arkham_scenarios() -> list[dict]:
    """
    Fetch Arkham Horror scenarios from arkhamcentral.com.
    Returns a list of dicts with 'id', 'title', and 'description'.
    """
    url = "https://arkhamcentral.com/index.php/fan-created-content-arkham-horror-lcg/"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        scenarios = []
        # Find all links to scenarios in the fan-created content section
        for link in soup.select(".entry-content a"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            # Only include links that look like scenario pages
            if href.startswith("https://arkhamcentral.com/index.php/") and title:
                scenario_id = href.split("/")[-2] if href.endswith("/") else href.split("/")[-1]
                scenarios.append({
                    "id": scenario_id,
                    "title": title,
                    "description": f"Arkham Horror scenario: {title}",
                    "url": href
                })
        return scenarios

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
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
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name != "add-note":
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    note_name = arguments.get("name")
    content = arguments.get("content")

    if not note_name or not content:
        raise ValueError("Missing name or content")

    # Update server state
    notes[note_name] = content

    # Notify clients that resources have changed
    await server.request_context.session.send_resource_list_changed()

    return [
        types.TextContent(
            type="text",
            text=f"Added note '{note_name}' with content: {content}",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific Arkham Horror scenario's content by its URI.
    """
    if uri.scheme == "arkham" and uri.path.startswith("/scenario/"):
        scenario_id = uri.path.split("/scenario/")[-1]
        return await fetch_scenario_detail(scenario_id)
    raise ValueError(f"Unsupported URI: {uri}")

async def fetch_scenario_detail(scenario_id: str) -> str:
    """
    Fetch the HTML content for a specific scenario from arkhamcentral.com.
    """
    url = f"https://arkhamcentral.com/scenario/{scenario_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Extract main scenario content (adjust selector as needed)
        main_content = soup.select_one(".scenario-content")
        return str(main_content) if main_content else resp.text

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="arkham-horror-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

# In-memory notes storage for prompt/tool demo
notes = {}

@app.get("/scenarios")
async def get_scenarios():
    """Temporary endpoint to list Arkham Horror scenarios."""
    try:
        scenarios = await fetch_arkham_scenarios()
        return scenarios
    except Exception as e:
        logging.exception("Error fetching scenarios")
        return PlainTextResponse(f"Error: {e}", status_code=500)

@app.get("/scenarios/{scenario_id}")
async def get_scenario_detail(scenario_id: str):
    """Temporary endpoint to get scenario HTML content."""
    html = await fetch_scenario_detail(scenario_id)
    return PlainTextResponse(html)

@app.get("/search")
async def search_arkham(
    type: str = Query(..., description="Type of object: scenario, card, investigator, etc."),
    name: Optional[str] = Query(None, description="Name or partial name to search for")
):
    """
    Search for Arkham Horror LCG objects by type and name.
    """
    results = []
    if type == "scenario":
        scenarios = await fetch_arkham_scenarios()
        if name:
            results = [s for s in scenarios if name.lower() in s["title"].lower()]
        else:
            results = scenarios
    elif type == "card":
        results = [{
            "error": "Card search is not available. ArkhamCentral.com does not provide a card database."
        }]
    elif type == "investigator":
        results = [{
            "error": "Investigator search is not available. ArkhamCentral.com does not provide an investigator database."
        }]
    else:
        results = [{"error": f"Unknown type: {type}"}]
    return results