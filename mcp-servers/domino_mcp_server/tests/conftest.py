"""Shared fixtures: import the server module with a clean, hermetic environment and a fake HTTP layer.

Hermetic means: no Domino variables from the real environment, no env file, and no ancestor-process
recovery (os.getppid is patched to 1 during import), so the suite passes inside a Domino Workspace.
"""
import asyncio
import importlib
import json as jsonlib
import os
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

_ENV_NAMES = (
    "DOMINO_API_HOST", "DOMINO_API_PROXY", "DOMINO_HOST", "DOMINO_TOKEN", "DOMINO_API_KEY",
    "DOMINO_PROJECT_ID", "DOMINO_PROJECT_NAME", "DOMINO_PROJECT_OWNER", "DOMINO_IS_GIT_BASED",
    "DOMINO_WORKING_DIR", "DOMINO_RUN_ID", "DOMINO_USER_HOST", "VSCODE_PROXY_URI",
    "DOMINO_MCP_ENV_FILE", "DOMINO_INSECURE_HTTP", "XDG_CONFIG_HOME",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """No Domino variables, no env file, no ancestor recovery."""
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DOMINO_MCP_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setattr(os, "getppid", lambda: 1)
    return monkeypatch


def import_server():
    """A freshly imported server module (import-time environment handling runs now)."""
    sys.modules.pop("domino_mcp_server", None)
    module = importlib.import_module("domino_mcp_server")
    module._project_cache.clear()
    module._file_version_cache.clear()
    module._recent_write_log.clear()
    return module


@pytest.fixture
def server(clean_env):
    return import_server()


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, content=b"", text=None):
        self.status_code = status_code
        self._json = json_body
        if json_body is not None and not content:
            content = jsonlib.dumps(json_body).encode()
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", "replace")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeHTTP:
    """Routes requests.request(method, url, ...) to canned responses and records every call.

    An unregistered route fails the test: a wrong URL must never pass as "not found".
    """

    def __init__(self):
        self.routes = {}   # (METHOD, path) -> FakeResponse | callable(kwargs) -> FakeResponse
        self.calls = []    # (METHOD, path, kwargs)

    def add(self, method, path, response):
        self.routes[(method.upper(), path)] = response

    def __call__(self, method, url, **kwargs):
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        self.calls.append((method.upper(), parts.path, {**kwargs, "base": f"{parts.scheme}://{parts.netloc}"}))
        route = self.routes.get((method.upper(), parts.path))
        if route is None:
            raise AssertionError(f"unexpected request {method.upper()} {parts.path}; registered: {sorted(self.routes)}")
        return route(kwargs) if callable(route) else route


@pytest.fixture
def http(server, monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr(server.requests, "request", fake)
    return fake


@pytest.fixture
def run():
    return lambda coro: asyncio.run(coro)
