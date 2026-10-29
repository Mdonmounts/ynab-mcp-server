"""Tests for the OpenAPI spec cache and the payee cache."""

import asyncio
import os
import time

import httpx
import pytest

from ynab_mcp_server import spec_cache
from ynab_mcp_server.payees import PayeeCache

SPEC_TEXT = "openapi: 3.0.0\ninfo: {title: YNAB, version: '1'}\npaths: {}\n"


@pytest.fixture
def fetches(monkeypatch):
    class Calls(list):
        fail = False

    calls = Calls()

    def fake_get(url, timeout):
        calls.append(url)
        if calls.fail:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, text=SPEC_TEXT, request=httpx.Request("GET", url))

    monkeypatch.setattr(spec_cache.httpx, "get", fake_get)
    return calls


def test_spec_downloaded_then_served_from_cache(tmp_path, fetches):
    assert spec_cache.load_openapi_spec(directory=tmp_path)["openapi"] == "3.0.0"
    assert (tmp_path / spec_cache.SPEC_CACHE_FILENAME).read_text() == SPEC_TEXT
    spec_cache.load_openapi_spec(directory=tmp_path)
    assert len(fetches) == 1


def test_stale_spec_refreshed(tmp_path, fetches):
    path = tmp_path / spec_cache.SPEC_CACHE_FILENAME
    path.write_text("openapi: old\n")
    old = time.time() - spec_cache.SPEC_CACHE_TTL_SECONDS - 1
    os.utime(path, (old, old))
    assert spec_cache.load_openapi_spec(directory=tmp_path)["openapi"] == "3.0.0"
    assert len(fetches) == 1


def test_stale_spec_used_when_offline(tmp_path, fetches):
    path = tmp_path / spec_cache.SPEC_CACHE_FILENAME
    path.write_text("openapi: old\n")
    old = time.time() - spec_cache.SPEC_CACHE_TTL_SECONDS - 1
    os.utime(path, (old, old))
    fetches.fail = True
    assert spec_cache.load_openapi_spec(directory=tmp_path)["openapi"] == "old"


def test_offline_without_cache_raises(tmp_path, fetches):
    fetches.fail = True
    with pytest.raises(httpx.ConnectError):
        spec_cache.load_openapi_spec(directory=tmp_path)


def test_cache_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("YNAB_MCP_CACHE_DIR", str(tmp_path))
    assert spec_cache.cache_dir() == tmp_path


def _payee(id, name, deleted=False, transfer=None):
    return {"id": id, "name": name, "deleted": deleted, "transfer_account_id": transfer}


def test_payee_cache_applies_deltas():
    responses = [
        {"payees": [_payee("1", "Grocer"), _payee("2", "Groceries Plus"), _payee("3", "Transfer : Savings", transfer="a")], "server_knowledge": 10},
        {"payees": [_payee("1", "Grocer", deleted=True), _payee("4", "Gas Co")], "server_knowledge": 11},
    ]
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"data": responses[len(seen) - 1]})

    client = httpx.AsyncClient(base_url="https://api.ynab.com/v1", transport=httpx.MockTransport(handler))
    cache = PayeeCache(client)

    first = asyncio.run(cache.search("p1", "groc"))
    assert [p["name"] for p in first["payees"]] == ["Grocer", "Groceries Plus"]

    second = asyncio.run(cache.search("p1", "", include_transfers=True))
    assert {p["name"] for p in second["payees"]} == {"Groceries Plus", "Transfer : Savings", "Gas Co"}
    assert seen == [{}, {"last_knowledge_of_server": "10"}]


def test_payee_search_limit():
    payees = [_payee(str(i), f"Shop {i}") for i in range(5)]

    def handler(request):
        return httpx.Response(200, json={"data": {"payees": payees, "server_knowledge": 1}})

    client = httpx.AsyncClient(base_url="https://api.ynab.com/v1", transport=httpx.MockTransport(handler))
    result = asyncio.run(PayeeCache(client).search("p1", "shop", limit=2))
    assert result["total_matches"] == 5 and len(result["payees"]) == 2
