"""Disk cache for the YNAB OpenAPI spec."""

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

YNAB_OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"
SPEC_CACHE_TTL_SECONDS = 24 * 60 * 60
SPEC_CACHE_FILENAME = "open_api_spec.yaml"


def cache_dir() -> Path:
    """Return the cache directory, honoring YNAB_MCP_CACHE_DIR and XDG_CACHE_HOME."""
    override = os.environ.get("YNAB_MCP_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "ynab-mcp-server"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_openapi_spec(
    url: str = YNAB_OPENAPI_SPEC_URL,
    ttl_seconds: float = SPEC_CACHE_TTL_SECONDS,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Load the spec from cache when fresh, else download it.

    A failed download falls back to a stale cached copy if there is one.
    """
    path = (directory or cache_dir()) / SPEC_CACHE_FILENAME
    cached = path.read_text(encoding="utf-8") if path.is_file() else None

    if cached is not None and time.time() - path.stat().st_mtime < ttl_seconds:
        return yaml.safe_load(cached)

    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        spec = yaml.safe_load(response.text)
    except (httpx.HTTPError, yaml.YAMLError) as error:
        if cached is None:
            raise
        print(
            f"Could not refresh the YNAB OpenAPI spec ({error}); using cached copy at {path}",
            file=sys.stderr,
        )
        return yaml.safe_load(cached)

    try:
        _write_atomic(path, response.text)
    except OSError as error:
        print(f"Could not cache the YNAB OpenAPI spec at {path}: {error}", file=sys.stderr)
    return spec
