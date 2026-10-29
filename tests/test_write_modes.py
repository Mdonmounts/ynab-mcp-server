"""Tests for the read-only and bulk-write settings."""

import asyncio

import httpx
import pytest

from ynab_mcp_server.server import (
    WriteBlockedError,
    _make_request_guard,
    build_server,
)


def _op(operation_id, body_ref=None):
    op = {"operationId": operation_id, "responses": {"200": {"description": "ok"}}}
    if body_ref:
        op["requestBody"] = {
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{body_ref}"}}}
        }
    return op


SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "YNAB", "version": "1"},
    "paths": {
        "/plans": {"get": _op("getPlans")},
        "/plans/{plan_id}/payees": {"get": _op("getPayees")},
        "/plans/{plan_id}/transactions": {
            "get": _op("getTransactions"),
            "post": _op("createTransaction", "PostTransactionsWrapper"),
            "patch": _op("updateTransactions", "PatchTransactionsWrapper"),
        },
        "/plans/{plan_id}/transactions/import": {"post": _op("importTransactions")},
        "/plans/{plan_id}/transactions/{transaction_id}": {
            "get": _op("getTransactionById"),
            "put": _op("updateTransaction"),
            "delete": _op("deleteTransaction"),
        },
        "/budgets/{budget_id}/transactions/bulk": {"post": _op("bulkCreateTransactions")},
    },
    "components": {
        "schemas": {
            "PostTransactionsWrapper": {
                "type": "object",
                "properties": {
                    "transaction": {"type": "object"},
                    "transactions": {"type": "array", "items": {"type": "object"}},
                },
            },
            "PatchTransactionsWrapper": {
                "type": "object",
                "properties": {"transactions": {"type": "array", "items": {"type": "object"}}},
            },
        }
    },
}


def _tools(**kwargs):
    server = build_server(SPEC, "token", **kwargs)
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def test_default_hides_bulk_writes():
    tools = _tools()
    assert "getPayees" not in tools
    assert {"createTransaction", "updateTransaction", "deleteTransaction"} <= tools.keys()
    assert not {"updateTransactions", "importTransactions", "bulkCreateTransactions"} & tools.keys()
    schema = str(tools["createTransaction"].parameters)
    assert "transaction" in schema and "transactions" not in schema


def test_bulk_writes_allowed():
    tools = _tools(allow_bulk_writes=True)
    assert {"updateTransactions", "importTransactions", "bulkCreateTransactions"} <= tools.keys()
    assert "transactions" in str(tools["createTransaction"].parameters)


def test_read_only_hides_all_writes():
    tools = _tools(read_only=True, allow_bulk_writes=True)
    assert set(tools) == {"getPlans", "getTransactions", "getTransactionById"}


def _check(guard, method, path, json=None):
    request = httpx.Request(method, f"https://api.ynab.com/v1{path}", json=json)
    asyncio.run(guard(request))


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PATCH", "/plans/p1/transactions", {"transactions": []}),
        ("POST", "/plans/p1/transactions/import", None),
        ("POST", "/budgets/b1/transactions/bulk", {"transactions": []}),
        ("POST", "/plans/p1/transactions", {"transactions": [{}]}),
    ],
)
def test_guard_blocks_bulk_requests(method, path, body):
    with pytest.raises(WriteBlockedError, match="bulk writes are disabled"):
        _check(_make_request_guard(False, False), method, path, body)
    _check(_make_request_guard(False, True), method, path, body)


def test_guard_allows_single_writes():
    guard = _make_request_guard(False, False)
    _check(guard, "POST", "/plans/p1/transactions", {"transaction": {}})
    _check(guard, "PUT", "/plans/p1/transactions/t1", {"transaction": {}})
    _check(guard, "DELETE", "/plans/p1/transactions/t1")


def test_guard_read_only_blocks_every_write():
    guard = _make_request_guard(True, True)
    _check(guard, "GET", "/plans/p1/transactions")
    with pytest.raises(WriteBlockedError, match="read-only"):
        _check(guard, "PUT", "/plans/p1/transactions/t1", {"transaction": {}})


def test_blocked_request_reports_reason_to_caller(monkeypatch):
    from fastmcp import Client

    monkeypatch.setattr("ynab_mcp_server.server.BULK_WRITE_ROUTES", [])

    async def call():
        async with Client(build_server(SPEC, "token")) as client:
            return await client.call_tool(
                "updateTransactions", {"plan_id": "p1", "transactions": []}, raise_on_error=False
            )

    result = asyncio.run(call())
    assert result.is_error
    assert "bulk writes are disabled" in result.content[0].text
