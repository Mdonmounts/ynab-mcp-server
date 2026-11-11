# YNAB MCP Server

An MCP (Model Context Protocol) server for the [YNAB (You Need A Budget)](https://www.ynab.com/) API, built with [FastMCP](https://gofastmcp.com/).

This server automatically exposes all YNAB API endpoints as MCP tools, allowing AI assistants like Claude to interact with your YNAB budgets, accounts, transactions, and more.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) package manager
- A YNAB account with API access

## Setup

### Get Your YNAB API Token

1. Log in to your YNAB account at [app.ynab.com](https://app.ynab.com)
2. Go to **Account Settings** → **Developer Settings**
3. Click **New Token** under "Personal Access Tokens"
4. Give your token a name and click **Generate**
5. Copy the token (you won't be able to see it again!)

## Run the Server

The published package runs with `uvx ynab-mcp-tools`. `uvx` downloads it from
PyPI into an isolated environment, so you do not need to clone this repository
or manage a virtualenv.

1. Install [uv](https://docs.astral.sh/uv/) (see Prerequisites).
2. Set `YNAB_API_TOKEN` (see "Get Your YNAB API Token" above).
3. Run `uvx ynab-mcp-tools`. The server speaks stdio: with the token set it
   starts quietly and waits for an MCP client — press Ctrl+C to stop. Without
   `YNAB_API_TOKEN` it exits immediately with an error naming the variable.

From a source checkout instead:

1. `git clone https://github.com/Mdonmounts/ynab-mcp-server.git && cd ynab-mcp-server`
2. `uv sync --locked`
3. `YNAB_API_TOKEN=your-token-here uv run ynab-mcp-tools`

## Connect an Agent (MCP Client)

JSON-based clients share one server block:

```json
{
  "mcpServers": {
    "ynab": {
      "command": "uvx",
      "args": ["ynab-mcp-tools"],
      "env": {
        "YNAB_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

### Claude Desktop

1. Open `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).
2. Paste the shared server block above into `mcpServers`.
3. Restart Claude Desktop.

### Claude Code

1. Add the server for all projects (user scope) — the `--` separates Claude's options from the server command:
   ```bash
   claude mcp add ynab --scope user \
     -e "YNAB_API_TOKEN=your-token-here" \
     -- uvx ynab-mcp-tools
   ```
   For the current project only, use `--scope local` instead.
2. Verify with `claude mcp list`. Uninstall with `claude mcp remove ynab --scope user` (or `local`).

### Cursor

1. Open `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project.
2. Paste the shared server block above into `mcpServers`.

### OpenCode

1. Open `~/.config/opencode/opencode.json`.
2. Add:
   ```json
   {
     "mcp": {
       "ynab": {
         "type": "local",
         "command": ["uvx", "ynab-mcp-tools"],
         "enabled": true,
         "environment": {
           "YNAB_API_TOKEN": "your-token-here"
         }
       }
     }
   }
   ```

### Any other stdio client

Point it at command `uvx` with args `["ynab-mcp-tools"]` and env `YNAB_API_TOKEN`.

### Verify the connection

1. Restart your client so it picks up the config.
2. Ask it to run a read tool, e.g. "List my YNAB budgets" (`getBudgets`). A missing or invalid token fails at startup with a `YNAB_API_TOKEN` error.

## Write Safety Settings

Two environment variables control what the server may change in your budget.
Set them next to `YNAB_API_TOKEN` in your MCP client config.

| Variable | Default | Effect |
| --- | --- | --- |
| `YNAB_READ_ONLY` | `false` | `true` hides every create, update and delete tool and blocks all write requests. Use this for reporting and analytics. |
| `YNAB_ALLOW_BULK_WRITES` | `false` | Bulk writes are off unless this is `true`. Off hides `updateTransactions` and `importTransactions`, removes the `transactions` array from `createTransaction` (one transaction at a time still works), and blocks those requests. |

Blocked requests are refused before they reach YNAB, and the tool error tells the
assistant which setting blocked it. For example, a read-only Claude Code setup:

```bash
claude mcp add ynab-reports --scope user \
  -e "YNAB_API_TOKEN=your-token-here" \
  -e "YNAB_READ_ONLY=true" \
  -- uvx ynab-mcp-tools
```

## Caching

- **OpenAPI spec:** the server builds its tools from YNAB's OpenAPI spec. It
  keeps a copy in `~/.cache/ynab-mcp-server/` (or `$XDG_CACHE_HOME`, or
  `YNAB_MCP_CACHE_DIR` if set), uses it for 24 hours, and falls back to the
  stale copy if YNAB can't be reached.
- **Payees:** `searchPayees` keeps payees in memory while the server runs. The
  first search downloads them once; later searches fetch only what changed.
  Payee data is never written to disk.

## Available Tools

The server automatically exposes all YNAB API endpoints as MCP tools. Here are some of the available operations:

### User

- `getUser` - Get authenticated user information

### Budgets

- `getBudgets` - List all budgets
- `getBudgetById` - Get a single budget with all related entities
- `getBudgetSettingsById` - Get budget settings

### Accounts

- `getAccounts` - List all accounts for a budget
- `getAccountById` - Get a single account
- `createAccount` - Create a new account

### Categories

- `getCategories` - List all categories for a budget
- `getCategoryById` - Get a single category
- `updateCategory` - Update a category
- `getMonthCategoryById` - Get a category for a specific month
- `updateMonthCategory` - Update a category for a specific month

### Transactions

- `getTransactions` - List transactions
- `getTransactionById` - Get a single transaction
- `createTransaction` - Create a new transaction
- `updateTransaction` - Update a transaction
- `deleteTransaction` - Delete a transaction
- `importTransactions` - Import transactions
- `getTransactionsByAccount` - List transactions for an account
- `getTransactionsByCategory` - List transactions for a category
- `getTransactionsByPayee` - List transactions for a payee

### Payees

- `searchPayees` - Search payees by name, served from a cache (replaces listing every payee, which is too large)
- `getPayeeById` - Get a single payee
- `updatePayee` - Update a payee

### Scheduled Transactions

- `getScheduledTransactions` - List scheduled transactions
- `getScheduledTransactionById` - Get a single scheduled transaction
- `createScheduledTransaction` - Create a new scheduled transaction
- `updateScheduledTransaction` - Update a scheduled transaction

### Months

- `getBudgetMonths` - List budget months
- `getBudgetMonth` - Get a single budget month

## Example Usage

Once connected, you can ask Claude things like:

- "Show me my YNAB budgets"
- "What's my current balance in my checking account?"
- "List my transactions from last week"
- "Create a transaction for $50 at the grocery store"
- "How much have I spent on dining out this month?"

## Automate a Task: Add a Custom Tool

The OpenAPI tools cover raw CRUD. For a repeatable task — "find this month's
uncategorized transactions", "flag anything over $500" — add one custom tool
so any agent can run it by name. `src/ynab_mcp_server/payees.py`
(`searchPayees`) is the reference implementation.

1. Create `src/ynab_mcp_server/<task>.py` with a `register_<task>_tools(server, client)` function.
2. Inside it, define an async function and expose it with `@server.tool(name="myTask", annotations={"readOnlyHint": True})`. The docstring becomes the tool description — state what it does and when to use it.
3. Call YNAB through the shared `client` (already authenticated and write-guarded). Keep the response small: cap list sizes and drop fields the agent doesn't need.
4. Register it in `build_server()` in `src/ynab_mcp_server/server.py`, right after `register_payee_tools(server, client)`.
5. Add a test in `tests/` and run `uv run pytest`.
6. Restart your client and ask for the task by name.

Minimal example — list uncategorized transactions since a date:

```python
# src/ynab_mcp_server/review.py
from typing import Any

import httpx


def register_review_tools(server: Any, client: httpx.AsyncClient) -> None:
    @server.tool(name="uncategorizedSince", annotations={"readOnlyHint": True})
    async def uncategorized_since(plan_id: str, since_date: str, limit: int = 50) -> dict[str, Any]:
        """Uncategorized transactions in a plan since a date (YYYY-MM-DD), newest first.

        `plan_id` is a plan (budget) id, or "last-used" / "default".
        """
        response = await client.get(
            f"/plans/{plan_id}/transactions", params={"since_date": since_date}
        )
        response.raise_for_status()
        uncategorized = [
            t for t in response.json()["data"]["transactions"] if not t.get("category_id")
        ]
        return {"count": len(uncategorized), "transactions": uncategorized[:limit]}
```

Write safety applies automatically: when `YNAB_READ_ONLY=true` the HTTP guard
in `server.py` blocks every write, including from custom tools. Mark
annotations honestly (`readOnlyHint` for reads, `destructiveHint` for deletes).

For conventions that need no code — "AMZN goes to Shopping unless the memo says
Kindle" — encode them as a skill instead (next section).

## Creating Custom Skills for Your YNAB Workflow

YNAB workflows are personal. Everyone has their own conventions for handling transactions, categorizing expenses, and managing duplicates. This repo includes a skill system that lets you encode your personal conventions so Claude can learn and apply them consistently.

### Step 1: Explore Your Budget

Start by asking Claude to do something useful with your YNAB data:

```
"Show me all my unapproved transactions"
"Help me categorize my uncategorized transactions"
"Find duplicate transactions in my budget"
```

Work through the task interactively. As you do, you'll naturally develop conventions. For example:

- "Venmo transactions always have a matching withdrawal in my checking account - I delete the Venmo one and keep the bank record"
- "Transactions from 'AMZN' should be categorized as 'Shopping' unless the memo mentions 'Kindle'"
- "Any transaction over $500 should be flagged for review"

### Step 2: Create a Skill to Encode Your Conventions

Once you've established patterns you want to reuse, create a skill to encode them. This repo includes the `skill-creator` skill in `.skills/skill-creator/` to help you build custom skills.

Ask Claude:

```
"Load the skill-creator skill and help me create a ynab skill that encodes
the conventions we just used for processing transactions"
```

The skill-creator will guide you through:

1. Identifying the reusable patterns from your workflow
2. Creating a SKILL.md file with your conventions
3. Structuring the skill for future use

### Step 3: Use Your Skills

Once created, your skills live in `.skills/` and Claude will automatically apply them when relevant. You can:

- Add more conventions as you discover them
- Share skills with others who have similar YNAB setups
- Build on the included examples

### Included Skills

- `.skills/skill-creator/` - Claude's official guide for creating new skills, included for convenience

## Resources

- [Development Guide](https://github.com/Mdonmounts/ynab-mcp-server/blob/main/DEVELOPMENT.md)
- [YNAB API Documentation](https://api.ynab.com/)
- [FastMCP Documentation](https://gofastmcp.com/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

## License

MIT
