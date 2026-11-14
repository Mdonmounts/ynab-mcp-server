# Development

## Local Setup

Clone the repository and install its locked dependencies:

```bash
git clone https://github.com/Mdonmounts/ynab-mcp-server.git
cd ynab-mcp-server
uv sync --locked
```

Run the development checkout with:

```bash
YNAB_API_TOKEN=your-token-here uv run ynab-mcp-server
```

Run the tests with:

```bash
uv run pytest
```

## Project Structure

```
.
├── DEVELOPMENT.md
├── LICENSE
├── pyproject.toml
├── README.md
├── tests/
│   ├── smoke_test.py
│   ├── test_caching.py
│   └── test_write_modes.py
├── uv.lock
└── src/
    └── ynab_mcp_server/
        ├── __init__.py
        ├── payees.py
        ├── server.py
        └── spec_cache.py
```

## How It Works

This server uses FastMCP's `from_openapi()` method to automatically generate
MCP tools from YNAB's OpenAPI specification. When the server starts, it:

1. Loads the YNAB OpenAPI spec from
   `https://api.ynab.com/papi/open_api_spec.yaml`, using the copy cached by
   `spec_cache.py` when it is less than 24 hours old.
2. Parses the specification.
3. Creates an authenticated HTTP client with your API token.
4. Generates MCP tools for each API endpoint.
5. Registers custom tools — `searchPayees` and any others added in
   `build_server` — on top of the generated endpoints.

## Adding a Custom Tool

1. Create `src/ynab_mcp_server/<task>.py` with a `register_<task>_tools(server, client)`
   function; expose an async function via `@server.tool(...)` (see `payees.py`).
   The docstring is the tool description.
2. Call it from `build_server()` in `server.py`, after `register_payee_tools(server, client)`.
3. Use the shared authenticated `client`; keep responses small (cap lists, drop fields).
4. Cover it with a test in `tests/` and run `uv run pytest`.

See the README's "Automate a Task: Add a Custom Tool" section for a complete example.

## Publishing

Releases are published to PyPI through GitHub's `pypi` environment and PyPI
Trusted Publishing. The publisher settings must use:

- PyPI project: `ynab-mcp-tools`
- GitHub owner: `rgarcia`
- Repository: `ynab-mcp-server`
- Workflow: `publish.yml`
- Environment: `pypi`

To publish a release:

1. Update the version with `uv version <version>` and merge that change.
2. Publish a GitHub release whose tag matches the version, such as `v0.1.0`.
3. The publish workflow builds and smoke-tests both distributions before
   uploading them to PyPI.
