# MCP server that wraps the Domino API for an AI coding assistant: start Jobs, read their status and
# logs, and read, upload and sync files of DFS (non-Git) projects. See README.md in this directory.
#
# Routes: everything that has a Public API equivalent in both published specs
# (https://docs.domino.ai/api-specs/6.3/public-api.json and .../cloud/public-api.json) uses it.
# Two operations have no public equivalent and keep their older routes; each is labelled at the
# point of use and listed in README.md:
#   - listing project files:  GET /v4/files/browseFiles, GET /v4/files/browseDirectories
#                             (Domino Internal API, may change between Domino versions)
#   - uploading a file:       PUT /v1/projects/{owner}/{project}/{path}
#                             (legacy API, not in any published spec)

from typing import Any, Callable, Dict, List
import base64
import functools
import hashlib
import os
import re
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import anyio
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------------------------

# Variables the server reads for its own configuration (not the ones Domino injects).
_CONFIG_VARS = ("DOMINO_HOST", "DOMINO_TOKEN", "DOMINO_API_KEY", "DOMINO_MCP_ENV_FILE",
                "DOMINO_INSECURE_HTTP")


def _drop_unset_placeholders(environ: Dict[str, str]) -> None:
    """Treat values a host passes for an unset variable as unset.

    Claude Code passes an unset ${VAR} through as the literal text "${VAR}"; Cursor may pass an
    unset ${env:NAME} as literal text or as an empty string. Either way the env-file fallback and
    the "not set" errors must still apply, so delete such values.
    """
    for name in [k for k, v in environ.items() if v.startswith("${")]:
        del environ[name]
    for name in _CONFIG_VARS:
        if environ.get(name) == "":
            del environ[name]


# Some hosts start stdio MCP servers with a minimal environment and give a plugin no way to
# forward more: Codex passes only HOME, LANG, LC_ALL, LOGNAME, PATH, SHELL and USER, and drops a
# plugin server that declares env_vars. Inside a Domino Workspace or Job the Domino variables are
# still set on the process that started the agent, so copy the ones this server reads from the
# nearest ancestor that has them. Linux only; the kernel allows reading the environment of
# processes owned by the same user.
_DOMINO_VARS = (
    "DOMINO_API_HOST", "DOMINO_API_PROXY", "DOMINO_PROJECT_ID", "DOMINO_PROJECT_NAME",
    "DOMINO_PROJECT_OWNER", "DOMINO_IS_GIT_BASED", "DOMINO_WORKING_DIR", "DOMINO_RUN_ID",
    "VSCODE_PROXY_URI",
)
_MARKER_VARS = ("DOMINO_API_PROXY", "DOMINO_API_HOST")


def _recover_domino_env(environ: Dict[str, str] | None = None, proc: str = "/proc",
                        start_pid: int | None = None, max_depth: int = 8) -> List[str]:
    """Copy Domino variables from the nearest ancestor process that has them.

    Returns the names that were recovered. Does nothing when a marker variable is already set or
    when `proc` is not a procfs directory (macOS, Windows).
    """
    env = os.environ if environ is None else environ
    if any(env.get(v) for v in _MARKER_VARS) or not os.path.isdir(proc):
        return []
    pid = os.getppid() if start_pid is None else start_pid
    for _ in range(max_depth):
        if pid <= 1:
            return []
        try:
            with open(f"{proc}/{pid}/environ", "rb") as f:
                parent = dict(kv.split(b"=", 1) for kv in f.read().split(b"\0") if b"=" in kv)
            with open(f"{proc}/{pid}/stat") as f:
                stat = f.read()
        except OSError:
            return []
        if any(v.encode() in parent for v in _MARKER_VARS):
            recovered = []
            for name in _DOMINO_VARS:
                value = parent.get(name.encode())
                if value is not None and name not in env:
                    env[name] = value.decode("utf-8", "replace")
                    recovered.append(name)
            return recovered
        # /proc/<pid>/stat is "pid (comm) state ppid ..."; comm may contain spaces.
        pid = int(stat.rsplit(")", 1)[1].split()[1])
    return []


def _env_file_path() -> Path:
    """Where the server reads DOMINO_HOST and DOMINO_TOKEN from when the host passes neither.

    `uv --directory` runs this server with the plugin directory as its working directory, so a
    `.env` next to the user's project is never found. Use one documented location instead:
    $DOMINO_MCP_ENV_FILE, else $XDG_CONFIG_HOME/domino-mcp-server/.env, else
    ~/.config/domino-mcp-server/.env.
    """
    explicit = os.environ.get("DOMINO_MCP_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "domino-mcp-server" / ".env"


def _load_environment() -> None:
    """Import-time environment handling, in order: placeholders, ancestor recovery, env file."""
    _drop_unset_placeholders(os.environ)
    _recover_domino_env()
    load_dotenv(_env_file_path(), override=False)
    _drop_unset_placeholders(os.environ)
    if os.environ.get("DOMINO_API_KEY") and not os.environ.get("DOMINO_TOKEN"):
        print("domino_mcp_server: DOMINO_API_KEY is set but legacy API keys are not supported by "
              "this server. Set DOMINO_TOKEN to a Personal Access Token or service account token.",
              file=sys.stderr)


_load_environment()


class DominoError(Exception):
    """A tool-level failure with a message meant for the user and the model."""


def _auth_help() -> str:
    text = (
        "Outside a Domino execution set DOMINO_HOST to your Domino URL (for example "
        "https://domino.example.com) and DOMINO_TOKEN to a Personal Access Token (Account settings > "
        "Personal Access Token) or a service account token, either in the environment the MCP host "
        f"passes to this server or in the env file {_env_file_path()} (KEY=value lines, chmod 600; "
        "the file is read when the host strips the environment, as Codex does). Inside a Domino "
        "Workspace or Job the platform sets DOMINO_API_PROXY and no token is needed. See "
        "https://docs.domino.ai/cloud/reference/api/domino-api-authentication."
    )
    legacy_dotenv = Path(__file__).resolve().parent / ".env"
    if legacy_dotenv.is_file():
        text += f" Note: {legacy_dotenv} is no longer read; move its values to the env file above."
    return text


def _is_domino_workspace() -> bool:
    """True inside a Domino execution (Workspace, Job, App): the platform sets DOMINO_API_PROXY."""
    return bool(os.environ.get("DOMINO_API_PROXY"))


def _is_loopback(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def _get_domino_host() -> str:
    """Base URL for API calls.

    Inside a Domino execution: $DOMINO_API_PROXY, which forwards to the platform and adds the
    starting user's token. Outside: DOMINO_HOST (or DOMINO_API_HOST) from the environment.
    """
    proxy = os.environ.get("DOMINO_API_PROXY")
    if proxy:
        return proxy.rstrip("/")
    host = (os.environ.get("DOMINO_HOST") or os.environ.get("DOMINO_API_HOST") or "").strip()
    if not host:
        raise DominoError("DOMINO_HOST is not set and this is not a Domino execution "
                          "(DOMINO_API_PROXY is not set). " + _auth_help())
    if host.startswith("http://") and not _is_loopback(host) \
            and os.environ.get("DOMINO_INSECURE_HTTP", "").lower() not in ("1", "true", "yes"):
        raise DominoError(f"DOMINO_HOST uses http://, which would send DOMINO_TOKEN in clear text. "
                          f"Use the https:// URL of your Domino deployment (set DOMINO_INSECURE_HTTP=true "
                          f"to allow http:// deliberately).")
    if not host.startswith(("http://", "https://")):
        raise DominoError("DOMINO_HOST must be a URL starting with https://")
    return host.rstrip("/")


_TOKEN_BAD_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")


def _get_token() -> str | None:
    """DOMINO_TOKEN, stripped of surrounding whitespace; None when unset.

    Rejects a value with inner whitespace or control characters without echoing it, because
    `requests` would otherwise include the header value in its exception text.
    """
    raw = os.environ.get("DOMINO_TOKEN")
    if raw is None:
        return None
    token = raw.strip()
    if not token:
        return None
    if _TOKEN_BAD_CHARS.search(token):
        raise DominoError("DOMINO_TOKEN contains whitespace or control characters inside the value; "
                          "paste the token on one line with nothing else (the value is not shown here).")
    return token


def _get_auth_headers() -> Dict[str, str]:
    """Authentication headers for Domino API calls.

    Inside a Domino execution: none; the API proxy adds the user's token. Outside: DOMINO_TOKEN
    (Personal Access Token or service account token) as a bearer. Legacy API keys
    (DOMINO_API_KEY, X-Domino-Api-Key) are deprecated by Domino and not sent by this server.
    """
    if _is_domino_workspace():
        return {}
    token = _get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    if os.environ.get("DOMINO_API_KEY"):
        raise DominoError("DOMINO_API_KEY is set, but legacy API keys (X-Domino-Api-Key) are "
                          "deprecated by Domino and not supported by this server. " + _auth_help())
    raise DominoError("DOMINO_TOKEN is not set. " + _auth_help())


def _auth_mode() -> str:
    if _is_domino_workspace():
        return "api_proxy"
    try:
        return "bearer_token" if _get_token() else "none"
    except DominoError:
        return "invalid_token"


def _redact(text: str) -> str:
    """Remove the bearer token from any text that may reach the model or a log."""
    try:
        token = _get_token()
    except DominoError:
        token = (os.environ.get("DOMINO_TOKEN") or "").strip() or None
    if token:
        text = text.replace(token, "<redacted>")
    return re.sub(r"(?i)bearer\s+[^\s'\"]+", "Bearer <redacted>", text)


def _get_external_host() -> str | None:
    """The user-facing Domino URL for links in results, or None when it is not known.

    Inside a Workspace only VSCODE_PROXY_URI carries it (DOMINO_API_HOST is the in-cluster URL
    and would give unreachable links). Outside, DOMINO_HOST is already the external URL.
    """
    if not _is_domino_workspace():
        try:
            return _get_domino_host()
        except DominoError:
            return None
    vpu = os.environ.get("VSCODE_PROXY_URI", "")
    if vpu:
        parsed = urllib.parse.urlparse(vpu)
        if parsed.scheme and parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}"
    return None


def _env_flag(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return value.strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------

_TIMEOUT = (10, 60)  # connect, read (seconds)

# Every tool call runs under a time budget (set by _threaded): the host's per-call limit, see
# _wait_cap. HTTP timeouts shrink to the remaining budget and no request starts once it is spent,
# so a slow deployment cannot push a call past the host's timeout.
_budget = threading.local()
_MIN_REQUEST_SECONDS = 2.0


class BudgetExhausted(DominoError):
    """The tool call's time budget is spent; nothing more is started."""


def _set_budget(seconds: float | None) -> None:
    _budget.deadline = None if seconds is None else time.monotonic() + seconds


def _remaining() -> float | None:
    deadline = getattr(_budget, "deadline", None)
    return None if deadline is None else max(0.0, deadline - time.monotonic())


def _request_timeout() -> tuple:
    remaining = _remaining()
    if remaining is None:
        return _TIMEOUT
    if remaining < _MIN_REQUEST_SECONDS:
        raise BudgetExhausted("the call's time budget is spent; call the tool again to continue")
    return (min(_TIMEOUT[0], remaining), min(_TIMEOUT[1], remaining))


def _describe_http_error(method: str, path: str, resp: requests.Response) -> str:
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = "; ".join(str(x) for x in (body.get("errors") or [])) or \
                str(body.get("message") or body.get("error") or "")
    except ValueError:
        detail = resp.text[:300]
    message = f"{method} {path} returned HTTP {resp.status_code}"
    if detail:
        message += f": {detail}"
    if resp.status_code in (401, 403) and not _is_domino_workspace():
        message += ". Check that DOMINO_TOKEN is a valid, unexpired Personal Access Token or " \
                   "service account token for DOMINO_HOST and that the token's user can access " \
                   "this project."
    return _redact(message)


def _api(method: str, path: str, *, params: Dict[str, Any] | None = None,
         json: Any = None, data: bytes | None = None, headers: Dict[str, str] | None = None,
         allow: tuple = ()) -> requests.Response:
    """One Domino API call. Raises DominoError with a readable, token-free message on failure."""
    url = f"{_get_domino_host()}{path}"
    hdrs = {**_get_auth_headers(), **(headers or {})}
    try:
        timeout = _request_timeout()
    except BudgetExhausted as e:
        raise BudgetExhausted(f"{method} {path} not started: {e}") from None
    try:
        resp = requests.request(method, url, params=params, json=json, data=data, headers=hdrs,
                                timeout=timeout)
    except Exception as e:  # requests exceptions can embed header values; never let them through raw
        raise DominoError(_redact(f"{method} {path} failed: {e}")) from None
    if resp.status_code in allow:
        return resp
    if resp.status_code >= 400:
        raise DominoError(_describe_http_error(method, path, resp))
    return resp


def _api_json(method: str, path: str, **kwargs: Any) -> Any:
    resp = _api(method, path, **kwargs)
    try:
        return resp.json()
    except ValueError:
        raise DominoError(f"{method} {path} returned a non-JSON response (HTTP {resp.status_code}). "
                          f"Check that DOMINO_HOST is the URL of the Domino deployment itself, not a "
                          f"login page or another site.") from None


_CLIENT_NAME = ""   # the MCP client's name from initialize, once a tool call has run


def _capture_client_name() -> None:
    """Remember which MCP host is connected (one host per stdio process)."""
    global _CLIENT_NAME
    if _CLIENT_NAME:
        return
    try:
        params = mcp.get_context().session.client_params
        _CLIENT_NAME = ((params.clientInfo.name if params and params.clientInfo else "") or "").lower()
    except Exception:
        _CLIENT_NAME = ""


def _run_with_budget(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    _set_budget(_wait_cap())
    try:
        return fn(*args, **kwargs)
    finally:
        _set_budget(None)


def _threaded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run a blocking tool implementation in a worker thread, under the per-call time budget,
    so the stdio event loop stays free and no call outlives the host's tool timeout."""
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        _capture_client_name()
        return await anyio.to_thread.run_sync(functools.partial(_run_with_budget, fn, *args, **kwargs))
    return wrapper


# ---------------------------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------------------------

def _plugin_instructions() -> str | None:
    """The lead section of the plugin's always-on rules file, sent as MCP server instructions.

    rules/domino.md is the single source for the plugin's always-on guidance. Hosts that load it
    directly (a session-start hook, a context file, an always-on rule) get the whole file; hosts
    that only surface MCP server instructions, such as Codex, get its lead section: everything
    before the first "## " heading, without frontmatter, capped at 900 bytes.
    """
    rules = Path(__file__).resolve().parents[2] / "rules" / "domino.md"
    try:
        text = rules.read_text(encoding="utf-8")
    except OSError:
        return None
    text = text.replace("\r\n", "\n")
    # Same front-matter rule as scripts/lint-skills.py: exact "---" delimiter lines.
    match = re.match(r"\A---\n.*?\n---\n(.*)\Z", text, re.S)
    if match:
        text = match.group(1)
    lead = text.split("\n## ", 1)[0].strip()
    return lead.encode("utf-8")[:900].decode("utf-8", "ignore") or None


mcp = FastMCP("domino_server", instructions=_plugin_instructions())


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------

def _validate_url_parameter(param_value: str, param_name: str) -> str:
    """Validate and URL-encode a single path segment (user name, project name, job id)."""
    if not param_value:
        raise DominoError(f"Invalid {param_name}: empty")
    if any(char in param_value for char in ['/', '\\', '?', '#', '&', '=', '%']):
        raise DominoError(f"Invalid {param_name}: '{param_value}' contains unsafe URL characters")
    return urllib.parse.quote(param_value, safe='')


def _normalize_project_path(file_path: str) -> str:
    """A project-relative file path: no leading slash, no '..', no URL metacharacters."""
    path = file_path.strip().replace("\\", "/").lstrip("/")
    if not path or path.endswith("/"):
        raise DominoError(f"Invalid file path {file_path!r}: must name a file")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise DominoError(f"Invalid file path {file_path!r}: '..', '.' and empty segments are not allowed")
    if any(c in path for c in "?#%"):
        raise DominoError(f"Invalid file path {file_path!r}: '?', '#' and '%' are not allowed")
    return path


def _file_key(content: bytes) -> str:
    """The version key Domino reports for a DFS file: SHA-1 of its content."""
    return hashlib.sha1(content).hexdigest()


# (owner, name) lower-cased -> {"id": str, "git_based": bool | None}
_project_cache: Dict[tuple, Dict[str, Any]] = {}
_PROJECT_PAGE = 100
_PROJECT_MAX_PAGES = 500   # a hard stop against a server that never returns an empty page


def _project_info(user_name: str, project_name: str) -> Dict[str, Any]:
    """The id of project `user_name/project_name` and whether it is Git-based.

    Inside a Domino execution the platform's DOMINO_PROJECT_ID and DOMINO_IS_GIT_BASED are used
    when the names match the current project. Otherwise the Public API project list is searched
    page by page until an empty page (or totalCount is reached) and the result cached for the
    life of the process.
    """
    owner, name = user_name.strip(), project_name.strip()
    if not owner or not name:
        raise DominoError("user_name and project_name are required")
    key = (owner.lower(), name.lower())
    env_id = os.environ.get("DOMINO_PROJECT_ID")
    if env_id and os.environ.get("DOMINO_PROJECT_OWNER", "").lower() == key[0] \
            and os.environ.get("DOMINO_PROJECT_NAME", "").lower() == key[1]:
        git_based = _env_flag("DOMINO_IS_GIT_BASED")
        if git_based is None:
            project = (_api_json("GET", f"/api/projects/v1/projects/{env_id}") or {}).get("project") or {}
            git_based = bool(project.get("mainRepository"))
        return {"id": env_id, "git_based": git_based}
    cached = _project_cache.get(key)
    if cached:
        return cached
    offset = 0
    for _ in range(_PROJECT_MAX_PAGES):
        body = _api_json("GET", "/api/projects/beta/projects",
                         params={"offset": offset, "limit": _PROJECT_PAGE}) or {}
        projects = body.get("projects") or []
        if not projects:
            break
        for p in projects:
            if (p.get("ownerUsername", "").lower(), p.get("name", "").lower()) == key:
                info = {"id": p["id"], "git_based": bool(p.get("mainRepository"))}
                _project_cache[key] = info
                return info
        offset += len(projects)
        total = (body.get("metadata") or {}).get("totalCount")
        if isinstance(total, int) and offset >= total:
            break
    else:
        raise DominoError(f"Gave up looking for project {owner}/{name} after "
                          f"{_PROJECT_MAX_PAGES * _PROJECT_PAGE} projects.")
    raise DominoError(f"Project {owner}/{name} was not found among the projects this user can "
                      f"access. Check the owner user name and project name.")


def _resolve_project_id(user_name: str, project_name: str) -> str:
    return _project_info(user_name, project_name)["id"]


def _require_dfs_project(user_name: str, project_name: str) -> Dict[str, Any]:
    """The project info, or an error when the project is Git-based (file writes would be lost)."""
    info = _project_info(user_name, project_name)
    if info.get("git_based"):
        raise DominoError(f"{user_name}/{project_name} is a Git-based project: Jobs run the code in "
                          f"its Git repository, so a file uploaded through the Domino file API is not "
                          f"what a Job sees. Commit and push to the repository instead; the file tools "
                          f"are for DFS projects.")
    return info


def _latest_commit_id(project_id: str) -> str:
    body = _api_json("GET", f"/api/projects/beta/projects/{project_id}/commits/latest") or {}
    commit = body.get("commitId")
    if not commit:
        raise DominoError(f"Could not read the latest commit of project {project_id}")
    return commit


def _read_remote_file(project_id: str, commit_id: str, path: str) -> requests.Response:
    """GET the raw content of a project file at a commit (Public API); 403 and 404 are returned."""
    encoded = urllib.parse.quote(path, safe="")  # '/' must be sent as %2F
    return _api("GET", f"/api/projects/v1/projects/{project_id}/files/{commit_id}/{encoded}/content",
                allow=(403, 404))


def _listed_in_directory(user_name: str, project_name: str, path: str) -> bool:
    """Whether `path` appears in the listing of its parent directory (Internal API)."""
    parent = path.rsplit("/", 1)[0] if "/" in path else "/"
    # Domino Internal API, may change between Domino versions: no public listing route exists.
    files = _api_json("GET", "/v4/files/browseFiles",
                      params={"ownerUsername": user_name, "projectName": project_name, "filePath": parent})
    return any(f.get("path") == path for f in (files or []))


_MAX_RETURN_BYTES = 2 * 1024 * 1024   # largest file content a tool returns to the model


def _text_or_none(raw: bytes) -> str | None:
    """The content as text when it is UTF-8, else None (binary)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _content_fields(raw: bytes, text: str | None, prefix: str = "") -> Dict[str, Any]:
    """{"content"} for text, {"content_base64", "encoding"} for binary, under the return cap."""
    if len(raw) > _MAX_RETURN_BYTES:
        return {f"{prefix}content_omitted": f"{len(raw)} bytes; this server returns file content up to {_MAX_RETURN_BYTES} bytes"}
    if text is not None:
        return {f"{prefix}content": text}
    return {f"{prefix}content_base64": base64.b64encode(raw).decode("ascii"), f"{prefix}encoding": "base64"}


def _bytes_from_args(text: str | None, content_base64: str | None, text_arg: str) -> bytes:
    """The upload bytes from exactly one of a text argument and a base64 argument."""
    if (text is None) == (content_base64 is None):
        raise DominoError(f"Pass exactly one of {text_arg} (text) or content_base64 (binary, base64-encoded)")
    if content_base64 is not None:
        try:
            return base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError):
            raise DominoError("content_base64 is not valid base64") from None
    return text.encode("utf-8")


def _read_state(user_name: str, project_name: str, path: str, project_id: str) -> Dict[str, Any]:
    """{"exists": bool, "commit_id": str, "content": str|None, "key": str|None} at the latest commit.

    "Does not exist" is concluded only from a 404, or from a 403 confirmed by a successful listing
    of the parent directory that does not contain the file (Domino answers 403 "... are not valid"
    for a missing path). Any other failure raises, so nothing is ever written over a file that
    could not be read.
    """
    commit_id = _latest_commit_id(project_id)
    resp = _read_remote_file(project_id, commit_id, path)
    if resp.status_code == 200:
        raw = resp.content
        return {"exists": True, "commit_id": commit_id, "raw": raw, "content": _text_or_none(raw),
                "key": _file_key(raw), "size": len(raw)}
    if resp.status_code == 403:
        if _listed_in_directory(user_name, project_name, path):
            raise FileAheadOfCommitError(
                f"Could not read {path} in {user_name}/{project_name} although the directory listing "
                f"shows it ({_describe_http_error('GET', 'file content', resp)}). Domino's latest-commit "
                f"index lags a write by some seconds, so the file was probably uploaded moments ago; "
                f"retry in a minute. Nothing was changed.")
    return {"exists": False, "commit_id": commit_id, "raw": None, "content": None, "key": None, "size": 0}


class FileAheadOfCommitError(DominoError):
    """The directory listing shows the file but the latest commit does not contain it yet."""


# Domino's project-file reads (latest commit, file content) lag a write by up to about 20 seconds
# (observed on Domino Cloud 6.4). A read in that window returns the previous version. The server
# therefore remembers its own writes and, before trusting a read, waits until the read shows the
# version it wrote, or a newer one, or this many seconds have passed.
_WRITE_VISIBILITY_TIMEOUT = 45.0
_WRITE_POLL_INTERVAL = 2.0


def _recent_own_write(entry: Dict[str, Any] | None) -> bool:
    return bool(entry) and "written_at" in entry and not entry.get("visible") \
        and time.monotonic() - entry["written_at"] < _WRITE_VISIBILITY_TIMEOUT * 4


def _remote_state(user_name: str, project_name: str, path: str, info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """The remote state of `path`, robust to the read-after-write lag.

    If this process wrote the file recently and the read still shows an older version, re-read
    until it shows the written version (confirmed, recorded in the cache), a different newer
    version (another client wrote after us: a real conflict), or the timeout passes (the read is
    returned as is and the caller reports the lag).
    """
    project_id = (info or _project_info(user_name, project_name))["id"]
    entry = _recent_write_log.get((user_name, project_name, path))
    if not _recent_own_write(entry):
        return _read_state(user_name, project_name, path, project_id)

    def _read_tolerant() -> Dict[str, Any]:
        # Right after our own write the listing can show the file before the latest commit
        # contains it; for an own write that is "not visible yet", not an error.
        try:
            return _read_state(user_name, project_name, path, project_id)
        except FileAheadOfCommitError as e:
            return {"exists": False, "commit_id": None, "raw": None, "content": None, "key": None,
                    "size": 0, "pending_error": e}

    # Stale means the read still shows what was there before our write (entry["previous_key"],
    # None for a created file); any other key that is not ours is a newer write by someone else.
    state = _read_tolerant()
    expected, previous = entry["key"], entry.get("previous_key")
    deadline = time.monotonic() + _WRITE_VISIBILITY_TIMEOUT
    while state["key"] != expected and state["key"] == previous and time.monotonic() < deadline:
        time.sleep(_WRITE_POLL_INTERVAL)
        state = _read_tolerant()
    if state["key"] == expected:
        entry["visible"] = True
        entry["commit_id"] = state["commit_id"]   # the newest commit known to contain this write
    elif state.get("pending_error"):
        raise state["pending_error"]
    else:
        state["lagging_own_write"] = state["key"] == previous
    return state


# For some seconds after an upload the Jobs, Apps and Model API services still resolve the previous
# DFS head, even once the files API shows the new commit (seen on Domino Cloud 6.4: a Job submitted
# 5 s after an upload ran from the project-creation commit). A Job started right after an upload
# therefore pins commitId to a commit known to contain the uploaded files instead of taking the
# head. Writes older than this many seconds are assumed to have reached every service.
_PIN_WINDOW = 15 * 60


def _recent_writes(user_name: str, project_name: str) -> List[tuple]:
    """[(path, entry)] for files this process wrote to the project within _PIN_WINDOW."""
    now = time.monotonic()
    return [(path, entry) for (owner, project, path), entry in list(_recent_write_log.items())
            if (owner, project) == (user_name, project_name) and now - entry["written_at"] < _PIN_WINDOW]


def _confirm_upload(user_name: str, project_name: str, path: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """After a write: the commit that contains it ("commitId"), waiting for the files API to show it."""
    why = ""
    try:
        _remote_state(user_name, project_name, path, info)
    except FileAheadOfCommitError:
        pass
    except DominoError as e:   # for example the call's time budget: the upload itself succeeded
        why = f" ({e})"
    entry = _recent_write_log.get((user_name, project_name, path)) or {}
    commit = entry.get("commit_id") if entry.get("visible") else None
    result: Dict[str, Any] = {"commitId": commit}
    if not commit:
        result["note"] = (f"The upload succeeded but the latest commit does not show it yet{why}; "
                          f"run_domino_job will wait for it before starting.")
    return result


def _pin_commit_for_recent_writes(user_name: str, project_name: str, info: Dict[str, Any]) -> str | None:
    """The commitId a new Job must run from so that this process's recent uploads are in it.

    None when there were no recent writes (the head is fine). Otherwise every recent write is
    waited for (one timeout budget for all files), then the latest commit is used if it contains
    all of them, else the newest commit confirmed to contain them. Raises instead of starting
    from a commit that would miss an upload.
    """
    writes = _recent_writes(user_name, project_name)
    if not writes:
        return None
    start = time.monotonic()
    for path, entry in writes:
        if entry.get("visible"):
            continue
        if time.monotonic() - start >= _WRITE_VISIBILITY_TIMEOUT:
            break
        try:
            _remote_state(user_name, project_name, path, info)
        except FileAheadOfCommitError:
            pass
    missing = [path for path, entry in writes if not entry.get("visible")]
    if missing:
        raise DominoError(f"The file(s) uploaded moments ago ({', '.join(missing)}) are not in the "
                          f"project's latest commit yet, so the Job would start without them. Retry "
                          f"run_domino_job in a minute, or pass commit_id of a commit that has them.")
    project_id = info["id"]
    latest = _latest_commit_id(project_id)
    confirmed = sorted((entry["written_at"], entry["commit_id"]) for _, entry in writes if entry.get("commit_id"))
    if confirmed and latest == confirmed[-1][1]:
        return latest
    for path, entry in writes:
        if entry.get("commit_id") == latest:
            continue
        resp = _read_remote_file(project_id, latest, path)
        key_at_latest = _file_key(resp.content) if resp.status_code == 200 else None
        if key_at_latest == entry["key"]:
            continue
        if key_at_latest is not None and key_at_latest != entry.get("previous_key"):
            continue   # someone wrote a newer version after ours: the latest commit is ahead, not behind
        # The latest commit does not (yet) contain this write: fall back to the newest commit
        # that was confirmed to; later writes' commits contain the earlier ones.
        return confirmed[-1][1] if confirmed else None
    return latest


def _filter_domino_stdout(stdout_text: str) -> str:
    """
    Filters the stdout text from a Domino job run to extract the relevant output.
    It tries to extract text between known infrastructure markers, but falls back
    to returning the full stdout if markers aren't found.

    Note: Git and DFS projects have different paths:
    - Git projects: /mnt/artifacts/.domino/configure-spark-defaults.sh
    - DFS projects: /mnt/.domino/configure-spark-defaults.sh
    """
    start_patterns = [
        r"### Completed /mnt(?:/artifacts)?/\.domino/configure-spark-defaults\.sh ###",
        r"### Starting user code ###",
        r"Starting job\.\.\.",
    ]
    end_patterns = [
        r"Evaluating cleanup command on EXIT",
        r"### User code finished ###",
        r"Job completed",
    ]
    start_index = 0
    for pattern in start_patterns:
        match = re.search(pattern, stdout_text)
        if match:
            start_index = match.end()
            break
    end_index = len(stdout_text)
    for pattern in end_patterns:
        match = re.search(pattern, stdout_text[start_index:])
        if match:
            end_index = start_index + match.start()
            break
    filtered_text = stdout_text[start_index:end_index].strip()
    if not filtered_text:
        return stdout_text.strip() if stdout_text.strip() else "(No output captured)"
    return filtered_text


_MLFLOW_LOCAL_RUN = r"http://127\.0\.0\.1:8768/#/experiments/(\d+)/runs/([a-f0-9]+)"


def _mlflow_link(text: str, user_name: str, project_name: str) -> Dict[str, str] | None:
    """The Domino experiment-run path for a local MLflow URL printed by a job, if any.

    Returns {"mlflow_path": "/experiments/..."} plus "mlflow_url" when the user-facing host is known.
    """
    match = re.search(_MLFLOW_LOCAL_RUN, text)
    if not match:
        return None
    path = f"/experiments/{user_name}/{project_name}/{match.group(1)}/{match.group(2)}"
    result = {"mlflow_path": path}
    host = _get_external_host()
    if host:
        result["mlflow_url"] = f"{host}{path}"
    return result


# Both specs: "Will not retrieve over 10000 log lines at a time"; Domino Cloud 6.4 applied 1000 to a
# larger request. Ask for the maximum and follow the cursor until isComplete or the page cap.
_LOG_PAGE_LIMIT = 10000
_LOG_MAX_PAGES = 10


def _job_logs(job_id: str, log_type: str) -> Dict[str, Any]:
    """All lines of one log type for a job (Public API, paginated), capped at _LOG_MAX_PAGES."""
    lines: List[str] = []
    cursor = None
    is_complete = False
    last_entry: Dict[str, Any] | None = None
    for _ in range(_LOG_MAX_PAGES):
        params: Dict[str, Any] = {"logType": log_type, "limit": _LOG_PAGE_LIMIT}
        if cursor:
            params["latestTimeNano"] = cursor
        body = _api_json("GET", f"/api/jobs/beta/jobs/{job_id}/logs", params=params) or {}
        logs = body.get("logs") or {}
        entries = list(logs.get("logContent") or [])
        # The cursor means "from this time"; drop a boundary line repeated from the previous page.
        if entries and last_entry and entries[0].get("timestamp") == last_entry.get("timestamp") \
                and entries[0].get("log") == last_entry.get("log"):
            entries = entries[1:]
        lines.extend(str(e.get("log", "")) for e in entries)
        is_complete = bool(logs.get("isComplete"))
        next_cursor = ((body.get("metadata") or {}).get("pagination") or {}).get("latestTimeNano")
        if is_complete or not entries or not next_cursor or next_cursor == cursor:
            break
        last_entry = entries[-1]
        cursor = next_cursor
    return {"lines": lines, "is_complete": is_complete}


def _summarize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    status = job.get("status") or {}
    return {
        "job_id": job.get("id"),
        "run_id": job.get("id"),  # a Domino job id and its run id are the same value
        "number": job.get("number"),
        "title": job.get("title"),
        "run_command": job.get("runCommand"),
        "status": status.get("executionStatus"),
        "is_completed": status.get("isCompleted"),
        "is_archived": status.get("isArchived"),
        "stage_times": job.get("stageTimes"),
        "commit_details": job.get("commitDetails"),
        "domino_stats": job.get("dominoStats"),
    }


# Waiting for a Job happens on the server because hosts block `sleep` and a status call returns
# at once. One call waits at most _WAIT_CAP seconds (Claude Code allows hours per MCP call and
# moves a call past two minutes to a background task); Codex ends a tool call after 60 s by
# default (`tool_timeout_sec`), so under Codex a call waits at most _WAIT_CAP_CODEX seconds and
# the model calls again. Polling backs off from 3 s to 10 s between status reads.
_WAIT_CAP = 600
_WAIT_CAP_CODEX = 50
_POLL_FIRST, _POLL_STEP, _POLL_MAX = 3.0, 2.0, 10.0


def _wait_cap() -> int:
    return _WAIT_CAP_CODEX if "codex" in _CLIENT_NAME else _WAIT_CAP


def _get_job(job_id: str) -> Dict[str, Any]:
    body = _api_json("GET", f"/api/jobs/beta/jobs/{job_id}") or {}   # Public API
    return _summarize_job(body.get("job") or {})


def _time_left() -> bool:
    remaining = _remaining()
    return remaining is None or remaining >= _MIN_REQUEST_SECONDS


def _poll_job(job_id: str, wait_seconds: int) -> Dict[str, Any]:
    """The job summary, after waiting up to wait_seconds for it to complete.

    The wait is capped per host (_wait_cap) and by what is left of the call's time budget; a
    status read is never started once the budget is spent, and a read cut off by it keeps the
    last known state. When no read fits, only the id comes back with a "call again" message.
    """
    budget = max(0.0, float(min(int(wait_seconds or 0), _wait_cap())))
    remaining = _remaining()
    if remaining is not None:
        budget = min(budget, remaining)
    start = time.monotonic()
    deadline = start + budget
    interval = _POLL_FIRST
    result: Dict[str, Any] | None = None
    try:
        if _time_left():
            result = _get_job(job_id)
        while result is not None and not result.get("is_completed") and time.monotonic() < deadline:
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
            interval = min(_POLL_MAX, interval + _POLL_STEP)
            if not _time_left():
                break
            result = _get_job(job_id)
    except DominoError as e:
        if result is None or _time_left():
            raise
        result["note"] = f"The last status read did not finish within the call's time budget ({e})."
    if result is None:
        result = {"job_id": job_id, "run_id": job_id, "status": None, "is_completed": None}
    result["waited_seconds"] = int(round(time.monotonic() - start))
    if not result.get("is_completed"):
        result["message"] = (f"Job is still {result.get('status') or 'in progress'} after "
                             f"{result['waited_seconds']} s. Call check_domino_job_run_status again "
                             f"with run_id={job_id} and wait_seconds (up to {_wait_cap()} per call) "
                             f"to keep waiting; do not use shell sleep.")
    return result


_RESULT_TAIL_LINES, _RESULT_TAIL_CHARS = 100, 8000


def _stdout_tail(job_id: str, user_name: str, project_name: str) -> Dict[str, Any]:
    """The last lines of a completed job's stdout, for run_domino_job(wait_seconds=...)."""
    logs = _job_logs(job_id, "stdOut")
    text = _filter_domino_stdout("\n".join(logs["lines"]))
    lines = text.splitlines()
    truncated = len(lines) > _RESULT_TAIL_LINES or len(text) > _RESULT_TAIL_CHARS
    tail = "\n".join(lines[-_RESULT_TAIL_LINES:])[-_RESULT_TAIL_CHARS:]
    out: Dict[str, Any] = {"results": tail, "results_truncated": truncated}
    if truncated:
        out["results_note"] = "Only the end of the output is shown; call check_domino_job_run_results for all of it."
    link = _mlflow_link(text, user_name, project_name)
    if link:
        out.update(link)
    return out


_hardware_tiers_cache: List[Dict[str, Any]] = []


def _list_all(path: str, key: str) -> List[Dict[str, Any]]:
    """Every item of a paginated Public API list (offset/limit, until an empty page)."""
    items: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(100):
        body = _api_json("GET", path, params={"offset": offset, "limit": 100}) or {}
        page = body.get(key) or []
        if not page:
            break
        items.extend(page)
        offset += len(page)
        total = (body.get("metadata") or {}).get("totalCount")
        if isinstance(total, int) and offset >= total:
            break
    return items


def _resolve_hardware_tier(value: str) -> str:
    """The id of a hardware tier given its id or name. Domino silently falls back to the project
    default for an unknown id, so the value is checked against GET /api/hardwaretiers/v1/hardwaretiers."""
    wanted = value.strip()
    if not wanted:
        raise DominoError("hardware_tier must not be empty")
    global _hardware_tiers_cache
    if not _hardware_tiers_cache:
        _hardware_tiers_cache = _list_all("/api/hardwaretiers/v1/hardwaretiers", "hardwareTiers")   # Public API
    tiers = [x for x in _hardware_tiers_cache if not (x.get("flags") or {}).get("isArchived")]
    for tier in tiers:
        if tier.get("id") == wanted:
            return wanted
    for tier in tiers:
        if (tier.get("name") or "").lower() == wanted.lower():
            return tier["id"]
    available = ", ".join(f"{x.get('id')} ({x.get('name')})" for x in tiers[:40])
    raise DominoError(f"Hardware tier {wanted!r} not found (Domino would silently run the Job on the "
                      f"project default). Use an id or name from: {available}")


def _resolve_environment_id(value: str) -> str:
    """The id of a compute environment given its id or name, checked against the Public API list."""
    wanted = value.strip()
    if not wanted:
        raise DominoError("environment_id must not be empty")
    envs = [x for x in _list_all("/api/environments/beta/environments", "environments") if not x.get("archived")]   # Public API
    for env in envs:
        if env.get("id") == wanted:
            return wanted
    matches = [env for env in envs if (env.get("name") or "").lower() == wanted.lower()]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        raise DominoError(f"Several environments are named {wanted!r}; pass the id of one of: "
                          + ", ".join(f"{e.get('id')} (owner {((e.get('owner') or {}).get('username'))})" for e in matches))
    available = ", ".join(f"{e.get('id')} ({e.get('name')})" for e in envs[:40])
    raise DominoError(f"Environment {wanted!r} not found. Use an id or name from: {available}")


# ---------------------------------------------------------------------------------------------
# Tools: jobs
# ---------------------------------------------------------------------------------------------

@mcp.tool()
@_threaded
def check_domino_job_run_results(run_id: str, user_name: str | None = None,
                                 project_name: str | None = None,
                                 log_type: str = "stdOut") -> Dict[str, Any]:
    """
    Returns the output of a Domino job run (its stdout by default).

    Args:
        run_id (str): The run id (= job id) of the job run to return the output of
        user_name (str, optional): The user name associated with the Domino Project. Kept for
            compatibility; the job id alone identifies the job.
        project_name (str, optional): The name of the Domino project. Kept for compatibility.
        log_type (str): Which log to return: "stdOut" (default), "stdErr", "prepareOutput" or
            "complete" (everything, interleaved).

    Returns:
        {"results": str, "line_count": int, "is_complete": bool, "mlflow_url"?: str}.
        is_complete is False when more log lines exist than this tool returns.
    """
    if log_type not in ("stdOut", "stdErr", "prepareOutput", "complete"):
        raise DominoError("log_type must be one of stdOut, stdErr, prepareOutput, complete")
    encoded_run_id = _validate_url_parameter(run_id, "run_id")
    logs = _job_logs(encoded_run_id, log_type)   # GET /api/jobs/beta/jobs/{jobId}/logs (Public API)
    raw = "\n".join(logs["lines"])

    text = _filter_domino_stdout(raw) if log_type == "stdOut" else (raw.strip() or "(No output captured)")
    result: Dict[str, Any] = {
        "results": text,
        "line_count": len(logs["lines"]),
        "is_complete": logs["is_complete"],
    }
    if user_name and project_name:
        link = _mlflow_link(text, user_name, project_name)
        if link:
            local_exp = r"View experiment at: http://127\.0\.0\.1:8768/#/experiments/\d+"
            kept = [ln for ln in text.splitlines()
                    if not re.search(_MLFLOW_LOCAL_RUN, ln) and not re.search(local_exp, ln)]
            result["results"] = "\n".join(kept).strip()
            result.update(link)
    if not logs["lines"]:
        result["note"] = ("No log lines were returned. The job may have produced no output of this "
                          "type, may still be starting, or its logs may have expired; try "
                          "log_type='complete'.")
    return result


@mcp.tool()
@_threaded
def check_domino_job_run_status(run_id: str, user_name: str | None = None,
                                project_name: str | None = None,
                                wait_seconds: int = 0) -> Dict[str, Any]:
    """
    Checks the status of a job run and, with wait_seconds, waits on the server until it finishes.
    A Job takes one to several minutes (a cold hardware tier alone takes 1-3 minutes to reach
    Running). To wait for a Job, call check_domino_job_run_status(run_id, wait_seconds=300)
    and repeat while is_completed is still false; never use shell sleep or rapid polling.

    Args:
        run_id (str): The run id (= job id) of the job run to return the status of
        user_name (str, optional): Kept for compatibility; the job id alone identifies the job.
        project_name (str, optional): Kept for compatibility.
        wait_seconds (int): How long this call may wait for the job to complete (0 returns at
            once). Capped per call at 600 s, or 50 s under Codex whose tool calls end after 60 s;
            when the cap is reached the current status comes back with "message": call again.

    Returns:
        {"job_id", "run_id", "number", "title", "run_command", "status", "is_completed",
         "waited_seconds", ...}. status is Domino's executionStatus, for example Queued,
        Preparing, Running, Succeeded, Failed, Stopped. Read the output with
        check_domino_job_run_results once is_completed is true.
    """
    encoded_run_id = _validate_url_parameter(run_id, "run_id")
    return _poll_job(encoded_run_id, wait_seconds)


@mcp.tool()
@_threaded
def run_domino_job(user_name: str, project_name: str, run_command: str, title: str,
                   git_branch: str | None = None, hardware_tier: str | None = None,
                   environment_id: str | None = None, wait_seconds: int = 0,
                   commit_id: str | None = None) -> Dict[str, Any]:
    """
    Runs a command as a Job on the Domino platform, typically a script such as
    'python my_script.py --arg1 val1'. The command runs against the project's files: for a
    DFS project the synced files at commit_id, which defaults to the latest commit; for a
    Git-based project the repository's default branch (pushed commits only) unless git_branch
    names another branch.

    Right after an upload the Job service still resolves the previous commit for some seconds,
    so when files were uploaded by this server moments ago and commit_id is omitted, the Job is
    pinned to a commit known to contain them (the commitId the upload tools returned, or the
    latest commit once it contains them). The commit used comes back as "commit_id".

    To run a Job and get its result in one call, pass wait_seconds (for example 300): the call
    waits on the server and returns the final status and the end of the stdout. If the Job is
    not finished when the call returns, continue with check_domino_job_run_status(run_id,
    wait_seconds=300); never use shell sleep.

    Args:
        user_name (str): The user name of the project owner.
        project_name (str): The name of the Domino project.
        run_command (str): The command to run, as one string, exactly as you would type it in a
            shell. Example: 'python my_script.py --arg1 val1 --name "my run"'
        title (str): A title that helps identify the job later. Example: 'running training.py'
        git_branch (str, optional): For a Git-based project, the branch to run from instead of
            the default branch.
        hardware_tier (str, optional): Hardware tier id (for example 'small-k8s') or name from
            GET /api/hardwaretiers/v1/hardwaretiers; checked before the Job starts because
            Domino silently uses the project default for an unknown id. Omit for the default.
        environment_id (str, optional): Compute environment id (or name) from
            GET /api/environments/beta/environments. Omit for the project default.
        wait_seconds (int): Wait on the server for the Job to complete, up to this many seconds
            (capped at 600 per call, 50 under Codex). 0 returns as soon as the Job is queued.
        commit_id (str, optional): The DFS commit to run from (the "commitId" an upload tool
            returned, or from GET /api/projects/beta/projects/{id}/commits/latest). Omit to let the
            server pin it after recent uploads, or to run the latest commit. On a Git-based project
            it is the main repository commit to run (sent as mainRepoGitRef refType "commitId").

    Returns:
        {"job_id", "run_id", "number", "status", "is_completed", "commit_id", ...} of the new job,
        plus "hardware_tier" and "environment_id" when given. commit_id is the DFS commit the Job
        was pinned to (null when the latest commit was taken). With wait_seconds:
        "waited_seconds", and once completed "results" (end of the stdout) and "results_truncated".
    """
    if not run_command or not run_command.strip():
        raise DominoError("run_command must not be empty")
    info = _project_info(user_name, project_name)
    project_id = info["id"]
    payload: Dict[str, Any] = {"projectId": project_id, "runCommand": run_command.strip(), "title": title}
    if git_branch:
        payload["mainRepoGitRef"] = {"refType": "branches", "value": git_branch}
    if hardware_tier:
        payload["hardwareTier"] = _resolve_hardware_tier(hardware_tier)
    if environment_id:
        payload["environmentId"] = _resolve_environment_id(environment_id)
    pinned: str | None = None
    if commit_id:
        commit_id = commit_id.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit_id):
            raise DominoError("commit_id must be a commit hash")
        if info.get("git_based"):
            if git_branch:
                raise DominoError("Pass either git_branch or commit_id for a Git-based project, not both")
            # NewJobV1.commitId is the DFS commit and is rejected for Git-based projects (Cloud spec);
            # a main-repository commit is pinned through mainRepoGitRef.
            payload["mainRepoGitRef"] = {"refType": "commitId", "value": commit_id}
        else:
            payload["commitId"] = commit_id
        pinned = commit_id
    elif not info.get("git_based"):
        gate = _project_gate(user_name, project_name)
        gate.begin_select()   # no upload to this project is in flight while the commit is chosen
        try:
            pinned = _pin_commit_for_recent_writes(user_name, project_name, info)
        finally:
            gate.end_select()
        if pinned:
            payload["commitId"] = pinned
    body = _api_json("POST", "/api/jobs/v1/jobs", json=payload) or {}   # Public API (NewJobV1)
    result = _summarize_job(body.get("job") or {})
    result["commit_id"] = pinned
    if "hardwareTier" in payload:
        result["hardware_tier"] = payload["hardwareTier"]
    if "environmentId" in payload:
        result["environment_id"] = payload["environmentId"]
    job_id = result.get("job_id")
    if wait_seconds and job_id:
        # From here on the Job exists: whatever the time budget allows is reported, never an error.
        result.update(_poll_job(job_id, wait_seconds))
        if result.get("is_completed"):
            try:
                result.update(_stdout_tail(job_id, user_name, project_name))
            except DominoError as e:
                result["results_note"] = f"Output not read within the call's time budget ({e}); call check_domino_job_run_results."
            result["message"] = (f"Job {result.get('number')} ({job_id}) finished with status "
                                 f"{result.get('status')} after {result.get('waited_seconds')} s.")
        return result
    result["message"] = (f"Started job {result.get('number')} ({job_id}) in "
                         f"{user_name}/{project_name}. Wait for it with "
                         f"check_domino_job_run_status(run_id, wait_seconds=300) until is_completed "
                         f"is true, then read check_domino_job_run_results.")
    return result


@mcp.tool()
def open_web_browser(url: str) -> bool:
    """Opens the specified URL in the default web browser on the machine running this server.
    Inside a Domino Workspace or Job there is no browser: the tool returns False without doing
    anything, and you should show the URL to the user instead.

    Args:
        url: The URL to open.

    Returns:
        True if the browser was opened successfully, False otherwise.
    """
    if _is_domino_workspace() or not url.startswith(("http://", "https://")):
        return False
    try:
        return bool(webbrowser.open_new_tab(url))
    except webbrowser.Error:
        return False


@mcp.tool()
async def get_domino_environment_info() -> Dict[str, Any]:
    """
    Returns information about the current Domino environment. Call this at the start of a
    session to learn whether the server runs inside a Domino execution, the project owner and
    name, whether the project is Git-based or DFS, and which authentication is in use.

    Inside a Domino Workspace or Job everything comes from platform environment variables.
    Outside Domino the response says what is configured (DOMINO_HOST, DOMINO_TOKEN) and what
    is missing; project owner, project name and the DFS setting then come from the user or
    from domino_project_settings.md.
    """
    inside = _is_domino_workspace()
    info: Dict[str, Any] = {
        "inside_domino_workspace": inside,
        "auth_mode": _auth_mode(),
        "domino_host": None,
    }
    try:
        info["domino_host"] = _get_domino_host()
    except DominoError as e:
        info["error"] = str(e)

    if inside:
        info["user_name"] = os.environ.get("DOMINO_PROJECT_OWNER", "")
        info["project_name"] = os.environ.get("DOMINO_PROJECT_NAME", "")
        info["project_id"] = os.environ.get("DOMINO_PROJECT_ID", "")
        info["run_id"] = os.environ.get("DOMINO_RUN_ID", "")
        info["working_dir"] = os.environ.get("DOMINO_WORKING_DIR", "")
        is_git = _env_flag("DOMINO_IS_GIT_BASED")
        if is_git is None:
            is_git = _probe_git(info["working_dir"])
        info["is_git_based"] = is_git
        info["is_dfs_project"] = (not is_git) if is_git is not None else None
        if is_git is None:
            info["note"] = ("DOMINO_IS_GIT_BASED is not set and the working directory could not be "
                            "probed; ask the user whether the project is Git-based or DFS.")
    else:
        info["is_git_based"] = None
        info["is_dfs_project"] = None
        if info["auth_mode"] == "none":
            info["error"] = info.get("error") or ("DOMINO_TOKEN is not set. " + _auth_help())
        elif info["auth_mode"] == "invalid_token":
            try:
                _get_token()
            except DominoError as e:
                info["error"] = str(e)
        if os.environ.get("DOMINO_API_KEY"):
            info["warning"] = ("DOMINO_API_KEY is set but legacy API keys are not supported by this "
                               "server; set DOMINO_TOKEN instead.")
        info["note"] = ("Running outside Domino. Take the project owner, project name and the "
                        "DFS setting from the user or from domino_project_settings.md.")
    return info


def _probe_git(working_dir: str) -> bool | None:
    """Fallback when DOMINO_IS_GIT_BASED is unset: is DOMINO_WORKING_DIR inside a Git work tree?"""
    if not working_dir or not os.path.isdir(working_dir):
        return None
    import subprocess
    try:
        result = subprocess.run(["git", "-C", working_dir, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return result.returncode == 0 and result.stdout.strip() == "true"


# ---------------------------------------------------------------------------------------------
# Tools: DFS (Domino File System) files
# These support syncing files with non-Git Domino projects. Reads use the Public API; listing
# uses the Domino Internal API and uploading the legacy v1 API (no public equivalent exists).
# Writes refuse Git-based projects, whose Jobs run the repository, not uploaded files.
# ---------------------------------------------------------------------------------------------

# Versions this process has seen, for conflict detection in smart_sync_file.
# Key: (user_name, project_name, file_path) -> {"key": sha1, "raw": bytes}
_file_version_cache: Dict[tuple, Dict[str, Any]] = {}
# Files this process wrote, for read-after-write handling and commit pinning. Kept apart from the
# conflict baseline above, which a download or an identical sync may replace at any time.
# Key: (user_name, project_name, file_path) ->
#   {"key", "previous_key", "written_at", "visible", "commit_id"}
_recent_write_log: Dict[tuple, Dict[str, Any]] = {}

# Tools run in worker threads. Read-check-write-confirm on one path is serialized with a lock per
# path, and a Job's commit selection waits for in-flight uploads to the project (and holds new
# ones back) with a gate per project. This coordinates this process's own threads only; two
# clients of the same project are not serialized (Domino has no conditional write).
_locks_guard = threading.Lock()
_path_locks: Dict[tuple, threading.Lock] = {}
_project_gates: Dict[tuple, "_ProjectGate"] = {}


def _path_lock(cache_key: tuple) -> threading.Lock:
    with _locks_guard:
        return _path_locks.setdefault(cache_key, threading.Lock())


class _ProjectGate:
    """Uploads (writers) and Job commit selection (selector) exclude each other per project."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._writes = 0
        self._selecting = False

    def begin_write(self) -> None:
        with self._cv:
            while self._selecting:
                self._cv.wait()
            self._writes += 1

    def end_write(self) -> None:
        with self._cv:
            self._writes -= 1
            self._cv.notify_all()

    def begin_select(self) -> None:
        with self._cv:
            while self._selecting or self._writes:
                self._cv.wait()
            self._selecting = True

    def end_select(self) -> None:
        with self._cv:
            self._selecting = False
            self._cv.notify_all()


def _project_gate(user_name: str, project_name: str) -> _ProjectGate:
    with _locks_guard:
        return _project_gates.setdefault((user_name, project_name), _ProjectGate())


@mcp.tool()
@_threaded
def list_domino_project_files(user_name: str, project_name: str, path: str = "/") -> Dict[str, Any]:
    """
    Lists the files and subdirectories in one directory of a Domino project (not recursive).
    Works with DFS (non-git) projects. Use it to see what exists before uploading or downloading.

    Args:
        user_name (str): The username of the project owner (e.g., 'alice')
        project_name (str): The name of the Domino project (e.g., 'diabetes_dfs_proj')
        path (str): The directory to list (default: "/" for the project root). Files in
            subdirectories are not included; list each subdirectory separately.

    Returns:
        {"path", "files": [{path, name, size, lastModified, key}], "directories": [{path, name}],
         "count"}
    """
    directory = path.strip() or "/"
    params = {"ownerUsername": user_name, "projectName": project_name, "filePath": directory}
    # Domino Internal API, may change between Domino versions: the Public API has no directory
    # listing for DFS project files.
    files = _api_json("GET", "/v4/files/browseFiles", params=params) or []
    dirs = _api_json("GET", "/v4/files/browseDirectories", params=params) or []
    simplified_files = [{
        "path": f.get("path"),
        "name": f.get("name"),
        "size": f.get("size"),
        "lastModified": f.get("lastModified"),
        "key": f.get("key"),
    } for f in files]
    simplified_dirs = [{"path": d.get("path"), "name": d.get("name")} for d in dirs]
    return {
        "path": directory,
        "files": simplified_files,
        "directories": simplified_dirs,
        "count": len(simplified_files),
    }


def _record_write(cache_key: tuple, key: str, data: bytes, previous_key: str | None) -> None:
    """Record a file this process just wrote: conflict baseline plus the write log entry
    (see _WRITE_VISIBILITY_TIMEOUT and _PIN_WINDOW).

    previous_key is the remote key read just before the write (None for a new file): a later
    read that still shows it is stale, not a conflict.
    """
    _file_version_cache[cache_key] = {"key": key, "raw": data}
    _recent_write_log[cache_key] = {"key": key, "previous_key": previous_key,
                                    "written_at": time.monotonic(), "visible": False, "commit_id": None}


def _upload(user_name: str, project_name: str, path: str, data: bytes) -> Dict[str, Any]:
    encoded_user_name = _validate_url_parameter(user_name, "user_name")
    encoded_project_name = _validate_url_parameter(project_name, "project_name")
    encoded_path = "/".join(urllib.parse.quote(seg, safe="") for seg in path.split("/"))
    # Legacy v1 API, not in any published spec: the Public API has no upload route for DFS
    # project files. The body is the raw bytes (text or binary).
    resp = _api("PUT", f"/v1/projects/{encoded_user_name}/{encoded_project_name}/{encoded_path}",
                data=data, headers={"Content-Type": "application/octet-stream"})
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return {
        "success": True,
        "path": body.get("path") or path,
        "size": body.get("size", len(data)),
        "key": _file_key(data),   # always the local SHA-1, the same source the conflict check uses
        "lastModified": body.get("lastModified"),
    }


def _upload_file(user_name: str, project_name: str, file_path: str, data: bytes,
                 overwrite: bool) -> Dict[str, Any]:
    path = _normalize_project_path(file_path)
    info = _require_dfs_project(user_name, project_name)
    cache_key = (user_name, project_name, path)
    gate = _project_gate(user_name, project_name)
    with _path_lock(cache_key):
        gate.begin_write()
        try:
            remote = _remote_state(user_name, project_name, path, info)   # also records the pre-write key
            if remote["exists"]:
                if remote["key"] == _file_key(data):
                    _file_version_cache[cache_key] = {"key": remote["key"], "raw": remote["raw"]}
                    return {"success": True, "action": "no_change", "path": path, "key": remote["key"],
                            "commitId": remote["commit_id"],
                            "message": "File content identical to remote, no upload needed"}
                if not overwrite:
                    raise DominoError(f"{path} already exists in {user_name}/{project_name} with different "
                                      f"content (key {remote['key']}). Use smart_sync_file to compare and "
                                      f"merge, or pass overwrite=True to replace it.")
            result = _upload(user_name, project_name, path, data)
            _record_write(cache_key, result["key"], data, remote["key"])
            result.update(_confirm_upload(user_name, project_name, path, info))
            return result
        finally:
            gate.end_write()


@mcp.tool()
@_threaded
def upload_file_to_domino_project(
    user_name: str,
    project_name: str,
    file_path: str,
    file_content: str | None = None,
    overwrite: bool = False,
    content_base64: str | None = None
) -> Dict[str, Any]:
    """
    Uploads a file of any type to a DFS (non-git) Domino project. Creates the file if it does
    not exist. Refuses to replace an existing file unless overwrite=True; prefer smart_sync_file,
    which detects conflicts instead of overwriting. Refuses Git-based projects (commit and push
    there). For a file on disk (a model artifact, an image) use sync_local_file_to_domino.

    Args:
        user_name (str): The username of the project owner (e.g., 'alice')
        project_name (str): The name of the Domino project (e.g., 'diabetes_dfs_proj')
        file_path (str): The path where the file should be saved in the project (e.g., 'scripts/train.py')
        file_content (str, optional): The content of a text file
        content_base64 (str, optional): The content of a binary file, base64-encoded (pass
            exactly one of file_content and content_base64)
        overwrite (bool): Replace the file if it already exists (default False).

    Returns:
        {"success": True, "path", "size", "key", "commitId", "lastModified"} on success. commitId
        is the project commit that contains the uploaded file; pass it as commit_id to
        run_domino_job (or as the commit of an App or Model API version) so the execution starts
        from it rather than from a head that may still be the previous commit for some seconds.
    """
    data = _bytes_from_args(file_content, content_base64, "file_content")
    return _upload_file(user_name, project_name, file_path, data, overwrite)


@mcp.tool()
@_threaded
def download_file_from_domino_project(
    user_name: str,
    project_name: str,
    file_path: str
) -> Dict[str, Any]:
    """
    Downloads a file's content from a Domino project at its latest commit (text as "content",
    binary as "content_base64"). Works with DFS (non-git) projects.

    IMPORTANT: This function remembers the version you downloaded. When you later use
    smart_sync_file to upload changes, it detects whether someone else modified the file in
    the meantime. Domino file reads lag a write by about 20 s; a file this server uploaded
    moments ago is waited for, but another client's very recent write may not be visible yet.

    Args:
        user_name (str): The username of the project owner (e.g., 'alice')
        project_name (str): The name of the Domino project (e.g., 'diabetes_dfs_proj')
        file_path (str): The path of the file to download (e.g., 'scripts/train.py')

    Returns:
        {"success": True, "path", "content" or "content_base64", "size", "key", "commitId"};
        key is the version identifier used for conflict detection. Files over 2 MiB are
        recorded for conflict detection but their content is not returned.
    """
    path = _normalize_project_path(file_path)
    with _path_lock((user_name, project_name, path)):
        remote = _remote_state(user_name, project_name, path)   # Public API
        if not remote["exists"]:
            raise DominoError(f"{path} does not exist in {user_name}/{project_name} at commit "
                              f"{remote['commit_id']}. Use list_domino_project_files to see what exists.")
        # The conflict baseline only; a recent own write stays recorded for commit pinning.
        _file_version_cache[(user_name, project_name, path)] = {"key": remote["key"], "raw": remote["raw"]}
    return {
        "success": True,
        "path": path,
        **_content_fields(remote["raw"], remote["content"]),
        "size": remote["size"],
        "key": remote["key"],
        "commitId": remote["commit_id"],
    }


@mcp.tool()
@_threaded
def sync_local_file_to_domino(
    user_name: str,
    project_name: str,
    local_file_path: str,
    domino_file_path: str | None = None,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Reads a local file of any type (text, model artifacts such as .joblib or .pkl, images) and
    uploads it unchanged to a DFS (non-git) Domino project. Refuses to replace an existing remote
    file unless overwrite=True; use smart_sync_file for conflict detection. Refuses Git-based
    projects (commit and push there).

    Args:
        user_name (str): The username of the project owner (e.g., 'alice')
        project_name (str): The name of the Domino project (e.g., 'diabetes_dfs_proj')
        local_file_path (str): The absolute path to the local file to upload
        domino_file_path (str, optional): The path in Domino where the file should be saved.
                                          If not provided, uses the filename from local_file_path.
        overwrite (bool): Replace the remote file if it already exists (default False).

    Returns:
        {"success": True, "path", "size", "key", "commitId", "lastModified"} on success. commitId
        is the project commit that contains the uploaded file; pass it as commit_id to
        run_domino_job so the Job starts from it.
    """
    try:
        with open(local_file_path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        raise DominoError(f"Local file not found: {local_file_path}") from None
    except OSError as e:
        raise DominoError(f"Failed to read local file: {e}") from None

    if domino_file_path is None:
        domino_file_path = os.path.basename(local_file_path)

    return _upload_file(user_name, project_name, domino_file_path, data, overwrite)


@mcp.tool()
@_threaded
def smart_sync_file(
    user_name: str,
    project_name: str,
    file_path: str,
    content: str | None = None,
    force_overwrite: bool = False,
    content_base64: str | None = None
) -> Dict[str, Any]:
    """
    Syncs a file of any type to a DFS (non-git) Domino project with conflict detection. Refuses
    Git-based projects (commit and push there).

    This is the RECOMMENDED way to upload files when working with shared projects. It never
    replaces a remote file it has not seen: it compares the remote version with the one you
    downloaded (or uploaded) earlier and reports a conflict instead of overwriting.

    Workflow:
    1. If the file does not exist remotely, it is created.
    2. If it exists and you have not downloaded it in this session, the remote content is
       returned as a conflict (unless it is identical to yours).
    3. If you downloaded it earlier and the remote version is unchanged, your content is uploaded.
    4. If the remote version changed since your download, both versions are returned as a conflict.
    Only force_overwrite=True replaces a conflicting remote file.
    Domino file reads lag a write by about 20 s: the check waits for this server's own recent
    uploads to become visible, but a write by another client in that window may not be seen.

    Args:
        user_name (str): The username of the project owner
        project_name (str): The name of the Domino project
        file_path (str): The path where the file should be saved
        content (str, optional): The new content of a text file
        content_base64 (str, optional): The new content of a binary file, base64-encoded (pass
            exactly one of content and content_base64)
        force_overwrite (bool): Replace the remote file whatever its current content.

    Returns:
        On success: {"success": True, "action": "created"|"uploaded"|"no_change"|"force_overwritten",
                     "key", "commitId"}. commitId is the project commit that contains the file;
                     pass it as commit_id to run_domino_job so the Job starts from it.
        On conflict: {"conflict": True, "message", "remote_content" (text) or
                      "remote_content_base64" (binary), "remote_key", "your_base_key"?,
                      "original_content"?, "suggestion"}
    """
    data = _bytes_from_args(content, content_base64, "content")
    path = _normalize_project_path(file_path)
    cache_key = (user_name, project_name, path)
    info = _require_dfs_project(user_name, project_name)
    gate = _project_gate(user_name, project_name)
    with _path_lock(cache_key):
        gate.begin_write()
        try:
            return _smart_sync_locked(user_name, project_name, path, data, force_overwrite, info)
        finally:
            gate.end_write()


def _smart_sync_locked(user_name: str, project_name: str, path: str, data: bytes,
                       force_overwrite: bool, info: Dict[str, Any]) -> Dict[str, Any]:
    cache_key = (user_name, project_name, path)
    cached = _file_version_cache.get(cache_key)
    remote = _remote_state(user_name, project_name, path, info)   # Public API, latest commit

    def _do_upload(action: str, **extra: Any) -> Dict[str, Any]:
        result = _upload(user_name, project_name, path, data)
        _record_write(cache_key, result["key"], data, remote["key"])
        confirmed = _confirm_upload(user_name, project_name, path, info)
        return {"success": True, "action": action, "path": path, "key": result["key"],
                "size": result["size"], "message": f"{action}: {path}", **confirmed, **extra}

    # Case 1: the file does not exist remotely: create it.
    if not remote["exists"]:
        return _do_upload("created")

    # Identical content needs no upload, whatever the history. Only the conflict baseline moves; a
    # recent own write stays recorded for commit pinning.
    if remote["key"] == _file_key(data):
        _file_version_cache[cache_key] = {"key": remote["key"], "raw": remote["raw"]}
        return {"success": True, "action": "no_change", "path": path, "key": remote["key"],
                "commitId": remote["commit_id"],
                "message": "File content identical to remote, no upload needed"}

    if force_overwrite:
        return _do_upload("force_overwritten", previous_remote_key=remote["key"])

    remote_fields = {**_content_fields(remote["raw"], remote["content"], "remote_"),
                     "remote_key": remote["key"], "remote_size": remote["size"]}

    # Case 2: the file exists but this session has no baseline for it.
    if cached is None:
        return {
            "conflict": True,
            "message": (f"'{path}' already exists in {user_name}/{project_name} with different "
                        f"content and you have not downloaded it in this session. Nothing was "
                        f"uploaded."),
            **remote_fields,
            "suggestion": ("Review the remote content, merge it with your version if needed, then call "
                           "smart_sync_file again with force_overwrite=True to upload your final "
                           "version (or download_file_from_domino_project first to set a baseline)."),
        }

    # Case 3: a baseline exists; did the remote file change since then?
    if remote["key"] != cached["key"]:
        result = {
            "conflict": True,
            "message": f"Remote file '{path}' changed since you last downloaded it. Nothing was uploaded.",
            "your_base_key": cached["key"],
            **remote_fields,
            "suggestion": ("Someone modified this file. Review the remote changes, merge if needed, "
                           "then call smart_sync_file again with force_overwrite=True."),
        }
        base_raw = cached.get("raw")
        if isinstance(base_raw, (bytes, bytearray)):
            result.update(_content_fields(bytes(base_raw), _text_or_none(bytes(base_raw)), "original_"))
        if remote.get("lagging_own_write"):
            result["note"] = (f"The remote read still shows the version from before your own upload "
                              f"after {int(_WRITE_VISIBILITY_TIMEOUT)} s; Domino file reads normally "
                              f"lag a write by about 20 s. Wait a minute and call smart_sync_file again.")
        return result

    # Case 4: remote unchanged since the baseline: safe to upload.
    return _do_upload("uploaded")


if __name__ == "__main__":
    # Initialize and run the server using stdio transport
    mcp.run(transport='stdio')
