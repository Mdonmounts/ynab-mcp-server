"""YNAB MCP Server using FastMCP and OpenAPI specification."""

import copy
import json
import os
import re
from typing import Any

import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, OpenAPITool, RouteMap

YNAB_API_BASE = "https://api.ynab.com/v1"
YNAB_OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# YNAB renamed budgets to plans; accept either form of the path prefix.
_PLAN = r"/(?:budgets|plans)/\{(?:budget|plan)_id\}"
_PLAN_REQUEST = r"/(?:budgets|plans)/[^/]+"

# Routes to exclude from the MCP server (these return too much data and bomb the context)
EXCLUDED_ROUTES = [
    RouteMap(
        methods=["GET"],
        pattern=rf"^{_PLAN}/payees$",
        mcp_type=MCPType.EXCLUDE,
    ),
]

# Endpoints that write many records in one call.
BULK_WRITE_ROUTES = [
    RouteMap(methods=["PATCH"], pattern=rf"^{_PLAN}/transactions$", mcp_type=MCPType.EXCLUDE),
    RouteMap(methods=["POST"], pattern=rf"^{_PLAN}/transactions/(?:import|bulk)$", mcp_type=MCPType.EXCLUDE),
]

READ_ONLY_ROUTES = [
    RouteMap(methods=sorted(WRITE_METHODS), mcp_type=MCPType.EXCLUDE),
]

# createTransaction stays available for one transaction, but its
# `transactions` array (many at once) is a bulk write.
_CREATE_TRANSACTIONS_PATH = re.compile(rf"^{_PLAN}/transactions$")
_BULK_REQUEST_PATHS = [
    ("PATCH", re.compile(rf"^{_PLAN_REQUEST}/transactions$")),
    ("POST", re.compile(rf"^{_PLAN_REQUEST}/transactions/(?:import|bulk)$")),
]
_CREATE_TRANSACTIONS_REQUEST = re.compile(rf"^{_PLAN_REQUEST}/transactions$")


class WriteBlockedError(httpx.RequestError):
    """Raised when a request is not allowed by the server's write settings.

    A RequestError so FastMCP reports the message back to the caller.
    """


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _omit_openapi_output_schemas(_route: object, component: object) -> None:
    """Cursor rejects some YNAB OpenAPI response schemas; tools do not need them."""
    if isinstance(component, OpenAPITool):
        component.output_schema = None


def _strip_bulk_create(openapi_spec: dict[str, Any]) -> dict[str, Any]:
    """Remove the `transactions` array from createTransaction's request body."""
    spec = copy.deepcopy(openapi_spec)
    for path, operations in spec.get("paths", {}).items():
        if not _CREATE_TRANSACTIONS_PATH.search(path):
            continue
        schema = (
            operations.get("post", {})
            .get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        ref = schema.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            schema = spec["components"]["schemas"][ref.rsplit("/", 1)[1]]
        schema.get("properties", {}).pop("transactions", None)
        if "transactions" in schema.get("required", []):
            schema["required"].remove("transactions")
    return spec


def _make_request_guard(read_only: bool, allow_bulk_writes: bool):
    """Block disallowed writes at the HTTP layer, whatever tools are exposed."""

    async def guard(request: httpx.Request) -> None:
        method = request.method.upper()
        if method not in WRITE_METHODS:
            return
        if read_only:
            raise WriteBlockedError(
                f"{method} {request.url.path} blocked: server is in read-only mode "
                "(unset YNAB_READ_ONLY to allow writes).",
                request=request,
            )
        if allow_bulk_writes:
            return
        path = request.url.path.removeprefix("/v1")
        bulk = any(m == method and p.search(path) for m, p in _BULK_REQUEST_PATHS)
        if not bulk and method == "POST" and _CREATE_TRANSACTIONS_REQUEST.search(path):
            try:
                body = json.loads(request.content or b"{}")
            except ValueError:
                body = {}
            bulk = isinstance(body, dict) and "transactions" in body
        if bulk:
            raise WriteBlockedError(
                f"{method} {request.url.path} blocked: bulk writes are disabled "
                "(set YNAB_ALLOW_BULK_WRITES=true to allow them).",
                request=request,
            )

    return guard


def build_server(
    openapi_spec: dict[str, Any],
    token: str,
    *,
    read_only: bool = False,
    allow_bulk_writes: bool = False,
) -> FastMCP:
    """Build the MCP server from a parsed OpenAPI spec and write settings."""
    route_maps = list(EXCLUDED_ROUTES)
    if read_only:
        route_maps += READ_ONLY_ROUTES
    elif not allow_bulk_writes:
        route_maps += BULK_WRITE_ROUTES
        openapi_spec = _strip_bulk_create(openapi_spec)

    # Create an authenticated HTTP client
    client = httpx.AsyncClient(
        base_url=YNAB_API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
        event_hooks={"request": [_make_request_guard(read_only, allow_bulk_writes)]},
    )

    # Create MCP server from OpenAPI spec
    return FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        route_maps=route_maps,
        mcp_component_fn=_omit_openapi_output_schemas,
    )


def create_server() -> FastMCP:
    """Create and configure the YNAB MCP server from the OpenAPI spec."""
    token = os.environ.get("YNAB_API_TOKEN")
    if not token:
        raise ValueError(
            "YNAB_API_TOKEN environment variable is required. "
            "Get your personal access token from https://app.ynab.com/settings/developer"
        )

    # Fetch the OpenAPI spec from YNAB
    spec_response = httpx.get(YNAB_OPENAPI_SPEC_URL)
    spec_response.raise_for_status()
    openapi_spec = yaml.safe_load(spec_response.text)

    return build_server(
        openapi_spec,
        token,
        read_only=_env_flag("YNAB_READ_ONLY", default=False),
        allow_bulk_writes=_env_flag("YNAB_ALLOW_BULK_WRITES", default=False),
    )


def main() -> None:
    """Run the YNAB MCP server over stdio."""
    create_server().run()


if __name__ == "__main__":
    main()
