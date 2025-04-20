# MCP Server: Arkham Horror Data

This project is an MCP (Model Context Protocol) server for retrieving Arkham Horror data from arkhamcentral.com.

## Features
- Fetches Arkham Horror scenarios, cards, and resources from arkhamcentral.com
- Exposes endpoints for use with MCP clients

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

## Development
- See `.github/copilot-instructions.md` for Copilot customization and SDK links.
- Extend `src/arkham_horror_mcp/server.py` to implement endpoints for Arkham Horror data.

---

For more on MCP, see: https://modelcontextprotocol.io/llms-full.txt
