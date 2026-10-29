"""In-memory payee cache kept current with YNAB delta requests."""

import asyncio
from typing import Any

import httpx

DEFAULT_SEARCH_LIMIT = 25


class PayeeCache:
    """Payees per plan, refreshed with `last_knowledge_of_server` deltas."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._plans: dict[str, tuple[int, dict[str, dict[str, Any]]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def payees(self, plan_id: str) -> list[dict[str, Any]]:
        """Return the plan's non-deleted payees, syncing changes first."""
        lock = self._locks.setdefault(plan_id, asyncio.Lock())
        async with lock:
            knowledge, payees = self._plans.get(plan_id, (None, {}))
            params = {} if knowledge is None else {"last_knowledge_of_server": knowledge}
            response = await self._client.get(f"/plans/{plan_id}/payees", params=params)
            response.raise_for_status()
            data = response.json()["data"]
            for payee in data["payees"]:
                if payee.get("deleted"):
                    payees.pop(payee["id"], None)
                else:
                    payees[payee["id"]] = payee
            self._plans[plan_id] = (data["server_knowledge"], payees)
            return list(payees.values())

    async def search(
        self,
        plan_id: str,
        query: str = "",
        limit: int = DEFAULT_SEARCH_LIMIT,
        include_transfers: bool = False,
    ) -> dict[str, Any]:
        needle = query.casefold().strip()
        matches = [
            {
                "id": payee["id"],
                "name": payee["name"],
                "transfer_account_id": payee.get("transfer_account_id"),
            }
            for payee in await self.payees(plan_id)
            if needle in payee["name"].casefold()
            and (include_transfers or not payee.get("transfer_account_id"))
        ]
        # Exact and prefix matches first, then alphabetical.
        matches.sort(
            key=lambda p: (
                p["name"].casefold() != needle,
                not p["name"].casefold().startswith(needle),
                p["name"].casefold(),
            )
        )
        return {"total_matches": len(matches), "payees": matches[: max(limit, 0)]}


def register_payee_tools(server: Any, client: httpx.AsyncClient) -> PayeeCache:
    """Add the cached `searchPayees` tool to the server."""
    cache = PayeeCache(client)

    @server.tool(
        name="searchPayees",
        annotations={"readOnlyHint": True},
    )
    async def search_payees(
        plan_id: str,
        query: str = "",
        limit: int = DEFAULT_SEARCH_LIMIT,
        include_transfers: bool = False,
    ) -> dict[str, Any]:
        """Search payees by name (case-insensitive substring).

        Use this instead of listing every payee. `plan_id` is a plan (budget)
        id, or "last-used" / "default". Transfer payees are left out unless
        `include_transfers` is true. Results are served from a cache that
        syncs only changes since the last call.
        """
        return await cache.search(plan_id, query, limit, include_transfers)

    return cache
