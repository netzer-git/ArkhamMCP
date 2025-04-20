# MCP Server: Arkham Horror Data

This project is an MCP (Model Context Protocol) server for retrieving Arkham Horror data from arkhamcentral.com.

## Features
- Fetches Arkham Horror scenarios from arkhamcentral.com (fan-created content)
- Exposes endpoints for use with MCP clients and LLMs
- Provides a `/search` endpoint for structured retrieval of scenarios
- Returns clear errors for card/investigator queries (not available on ArkhamCentral)

## Setup
1. Ensure you have Python 3.12+ and [uv](https://github.com/astral-sh/uv) installed and available in your PATH.
2. Install dependencies:
   ```pwsh
   uv sync --dev --all-extras
   ```
3. To run the server:
   ```pwsh
   uvicorn src.arkham_horror_mcp.server:app --reload
   ```

## API Endpoints
- `GET /scenarios` — List all fan-created scenarios
- `GET /scenarios/{scenario_id}` — Get HTML content for a specific scenario
- `GET /search?type=scenario&name=...` — Search for scenarios by name
- `GET /search?type=card|investigator` — Returns a clear error (not available)

## Development
- See `.github/copilot-instructions.md` for Copilot customization and SDK links.
- Extend `src/arkham_horror_mcp/server.py` to implement endpoints for Arkham Horror data.

---

For more on MCP, see: https://modelcontextprotocol.io/llms-full.txt
