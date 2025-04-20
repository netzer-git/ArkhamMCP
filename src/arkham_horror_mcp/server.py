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
    url = "https://arkhamcentral.com/scenarios"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        scenarios = []
        for item in soup.select(".scenario-listing .scenario-title"):
            title = item.get_text(strip=True)
            link = item.find("a")
            href = link["href"] if link else ""
            scenario_id = href.split("/")[-1] if href else title.lower().replace(" ", "-")
            scenarios.append({
                "id": scenario_id,
                "title": title,
                "description": f"Arkham Horror scenario: {title}",
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