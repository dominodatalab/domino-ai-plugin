"""Unit tests for domino_mcp_server with mocked HTTP. Run: uv run --with pytest pytest"""
import hashlib
import os
from pathlib import Path

import pytest

from conftest import FakeResponse, import_server

OWNER, PROJECT, PID = "alice", "demo", "0123456789abcdef01234567"
COMMIT = "fb2876cc5381e72ec8213596d80fef2d80de60e6"
GIT_REPO = {"id": "r1", "name": "demo", "serviceProvider": "github", "uri": "git@github.com:alice/demo.git"}


def _add_project_lookup(http, projects=None):
    projects = projects if projects is not None else [
        {"id": "ffffffffffffffffffffffff", "name": "other", "ownerUsername": OWNER},
        {"id": PID, "name": PROJECT, "ownerUsername": OWNER},
    ]
    http.add("GET", "/api/projects/beta/projects", FakeResponse(200, {"projects": projects, "metadata": {}}))


def _add_listing(http, entries):
    """browseFiles answers with `entries` (list of paths) for any directory."""
    http.add("GET", "/v4/files/browseFiles",
             FakeResponse(200, [{"path": p, "name": p.rsplit("/", 1)[-1], "size": 1, "lastModified": 1, "key": "k", "goalIds": []} for p in entries]))


def _add_file(http, path, content: bytes | None, commit=COMMIT, missing_status=403, listing=()):
    http.add("GET", f"/api/projects/beta/projects/{PID}/commits/latest",
             FakeResponse(200, {"commitId": commit, "metadata": {}}))
    encoded = path.replace("/", "%2F")
    route = f"/api/projects/v1/projects/{PID}/files/{commit}/{encoded}/content"
    if content is None:
        body = {"errors": [f"Not authorized: File {path}, commitId AnyObjectId[{commit}], projectId: {PID} are not valid."]} \
            if missing_status == 403 else {"errors": ["not found"]}
        http.add("GET", route, FakeResponse(missing_status, body))
        _add_listing(http, listing)
    else:
        http.add("GET", route, FakeResponse(200, content=content))


def _add_upload(http, path, visible_at="default"):
    """Register the legacy PUT. Unless visible_at is None, the uploaded bytes become readable at
    that commit (default: COMMIT) right away, which stands for the files API having caught up."""
    def handler(kwargs):
        data = kwargs["data"]
        if visible_at is not None:
            commit = COMMIT if visible_at == "default" else visible_at
            http.add("GET", f"/api/projects/v1/projects/{PID}/files/{commit}/{path.replace('/', '%2F')}/content",
                     FakeResponse(200, content=data))
        return FakeResponse(200, {"path": path, "size": len(data), "key": "server-key", "lastModified": 1})
    http.add("PUT", f"/v1/projects/{OWNER}/{PROJECT}/{path}", handler)


def _puts(http):
    return [c for c in http.calls if c[0] == "PUT"]


# ---------------------------------------------------------------------------------------------
# Auth and host selection
# ---------------------------------------------------------------------------------------------

def test_inside_domino_uses_proxy_without_auth_header(server, clean_env):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899/")
    clean_env.setenv("DOMINO_API_HOST", "http://nucleus-frontend.domino-platform:80")
    clean_env.setenv("DOMINO_TOKEN", "ignored-inside-domino")
    assert server._is_domino_workspace()
    assert server._get_domino_host() == "http://localhost:8899"
    assert server._get_auth_headers() == {}
    assert server._auth_mode() == "api_proxy"


def test_outside_domino_sends_bearer_token(server, clean_env, http):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com/")
    clean_env.setenv("DOMINO_TOKEN", "pat-value")
    assert not server._is_domino_workspace()
    assert server._get_domino_host() == "https://domino.example.com"
    assert server._get_auth_headers() == {"Authorization": "Bearer pat-value"}
    http.add("GET", "/api/users/v1/self", FakeResponse(200, {"user": {"userName": "alice"}}))
    server._api("GET", "/api/users/v1/self")
    method, path, kwargs = http.calls[-1]
    assert kwargs["base"] == "https://domino.example.com"
    assert kwargs["headers"] == {"Authorization": "Bearer pat-value"}
    assert "X-Domino-Api-Key" not in kwargs["headers"]
    assert kwargs["timeout"] == server._TIMEOUT


def test_outside_domino_accepts_domino_api_host_as_fallback(server, clean_env):
    clean_env.setenv("DOMINO_API_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")
    assert server._get_domino_host() == "https://domino.example.com"


def test_outside_domino_missing_config_gives_clear_error_naming_the_env_file(server, clean_env, tmp_path):
    with pytest.raises(server.DominoError) as host_err:
        server._get_domino_host()
    text = str(host_err.value)
    assert "DOMINO_HOST" in text and "DOMINO_TOKEN" in text
    assert str(tmp_path / "absent.env") in text            # Codex users can only use the env file
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    with pytest.raises(server.DominoError) as token_err:
        server._get_auth_headers()
    assert "DOMINO_TOKEN is not set" in str(token_err.value)
    assert "Personal Access Token" in str(token_err.value)


def test_legacy_api_key_is_rejected_with_migration_message(server, clean_env):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_API_KEY", "OLDKEYVALUE-123")
    with pytest.raises(server.DominoError) as err:
        server._get_auth_headers()
    assert "deprecated" in str(err.value) and "DOMINO_TOKEN" in str(err.value)
    assert "OLDKEYVALUE-123" not in str(err.value)


def test_literal_placeholders_and_empty_values_are_treated_as_unset(clean_env):
    clean_env.setenv("DOMINO_HOST", "${DOMINO_HOST}")
    clean_env.setenv("DOMINO_TOKEN", "${env:DOMINO_TOKEN}")
    clean_env.setenv("DOMINO_API_KEY", "")
    module = import_server()
    assert "DOMINO_HOST" not in os.environ and "DOMINO_TOKEN" not in os.environ
    assert "DOMINO_API_KEY" not in os.environ
    with pytest.raises(module.DominoError):
        module._get_domino_host()


def test_env_file_fills_missing_or_empty_variables_but_never_overrides(clean_env, tmp_path):
    env_file = tmp_path / "mcp.env"
    env_file.write_text("DOMINO_HOST=https://from-file.example.com\nDOMINO_TOKEN=file-token\n")
    clean_env.setenv("DOMINO_MCP_ENV_FILE", str(env_file))
    clean_env.setenv("DOMINO_TOKEN", "shell-token")
    clean_env.setenv("DOMINO_HOST", "")                      # empty, as a host might pass it
    module = import_server()
    assert module._get_domino_host() == "https://from-file.example.com"
    assert module._get_auth_headers() == {"Authorization": "Bearer shell-token"}


def test_default_env_file_location(server, clean_env, tmp_path):
    clean_env.delenv("DOMINO_MCP_ENV_FILE")
    clean_env.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert server._env_file_path() == tmp_path / "domino-mcp-server" / ".env"


def test_http_host_is_refused_unless_loopback_or_opted_in(server, clean_env):
    clean_env.setenv("DOMINO_TOKEN", "t")
    clean_env.setenv("DOMINO_HOST", "http://domino.example.com")
    with pytest.raises(server.DominoError) as err:
        server._get_domino_host()
    assert "clear text" in str(err.value) and "DOMINO_INSECURE_HTTP" in str(err.value)
    clean_env.setenv("DOMINO_HOST", "http://localhost:8080")
    assert server._get_domino_host() == "http://localhost:8080"
    clean_env.setenv("DOMINO_HOST", "http://domino.example.com")
    clean_env.setenv("DOMINO_INSECURE_HTTP", "true")
    assert server._get_domino_host() == "http://domino.example.com"
    clean_env.setenv("DOMINO_HOST", "domino.example.com")
    with pytest.raises(server.DominoError):
        server._get_domino_host()


def test_http_error_outside_domino_mentions_token(server, clean_env, http):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")
    http.add("GET", "/api/jobs/beta/jobs/abc", FakeResponse(401, {"message": "Unauthorized"}))
    with pytest.raises(server.DominoError) as err:
        server._api("GET", "/api/jobs/beta/jobs/abc")
    assert "HTTP 401" in str(err.value) and "DOMINO_TOKEN" in str(err.value)


def test_non_json_success_body_points_at_domino_host(server, clean_env, http):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")
    http.add("GET", "/api/users/v1/self", FakeResponse(200, content=b"<!doctype html><html>login</html>"))
    with pytest.raises(server.DominoError) as err:
        server._api_json("GET", "/api/users/v1/self")
    assert "non-JSON" in str(err.value) and "DOMINO_HOST" in str(err.value)


# ---------------------------------------------------------------------------------------------
# Token hygiene: never echo the token
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["SECRETPAT123\r", "SECRETPAT123\n", "  SECRETPAT123 \r\n", "\tSECRETPAT123"])
def test_token_is_stripped_of_surrounding_whitespace(server, clean_env, raw):
    clean_env.setenv("DOMINO_TOKEN", raw)
    assert server._get_auth_headers() == {"Authorization": "Bearer SECRETPAT123"}
    assert server._auth_mode() == "bearer_token"


@pytest.mark.parametrize("raw", ["SECRET PAT123", "SECRET\rPAT123", "SECRET\nPAT", "SECRET\x7fPAT", "SECRET\x01PAT"])
def test_token_with_inner_whitespace_or_control_chars_is_rejected_without_echo(server, clean_env, raw, run):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", raw)
    with pytest.raises(server.DominoError) as err:
        server._get_auth_headers()
    assert "DOMINO_TOKEN" in str(err.value) and "SECRET" not in str(err.value)
    info = run(server.get_domino_environment_info())
    assert info["auth_mode"] == "invalid_token" and "SECRET" not in info["error"]


def test_request_exception_text_is_redacted(server, clean_env, http):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "SECRETPAT123")

    def boom(kwargs):
        raise server.requests.exceptions.InvalidHeader(
            f"Invalid header value: {kwargs['headers']['Authorization']!r} for SECRETPAT123")
    http.add("GET", "/api/users/v1/self", boom)
    with pytest.raises(server.DominoError) as err:
        server._api("GET", "/api/users/v1/self")
    text = str(err.value)
    assert "SECRETPAT123" not in text and "<redacted>" in text and "failed" in text


def test_http_error_body_is_redacted(server, clean_env, http):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "SECRETPAT123")
    http.add("GET", "/api/users/v1/self",
             FakeResponse(401, {"message": "bad token SECRETPAT123 in header Bearer SECRETPAT123"}))
    with pytest.raises(server.DominoError) as err:
        server._api("GET", "/api/users/v1/self")
    assert "SECRETPAT123" not in str(err.value)
    http.add("GET", "/api/users/v1/self", FakeResponse(500, content=b"oops SECRETPAT123", text="oops SECRETPAT123"))
    with pytest.raises(server.DominoError) as err:
        server._api("GET", "/api/users/v1/self")
    assert "SECRETPAT123" not in str(err.value)


def test_environment_info_never_contains_the_token(server, clean_env, http, run):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "SECRETPAT123")
    http.add("GET", "/api/users/v1/self", FakeResponse(401, {"message": "token SECRETPAT123 rejected"}))
    assert "SECRETPAT123" not in str(run(server.get_domino_environment_info()))


# ---------------------------------------------------------------------------------------------
# Environment recovery from an ancestor process (Codex strips the environment)
# ---------------------------------------------------------------------------------------------

def _fake_proc(tmp_path, chain):
    """chain: list of (pid, ppid, env dict) from the server's parent upwards."""
    proc = tmp_path / "proc"
    for pid, ppid, env in chain:
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0")
        (d / "stat").write_text(f"{pid} (node (main)) S {ppid} 1 1 0 -1")
    return str(proc)


def test_recovers_domino_vars_from_nearest_ancestor(server, tmp_path):
    proc = _fake_proc(tmp_path, [
        (300, 200, {"HOME": "/home/u", "PATH": "/bin"}),                      # codex, stripped
        (200, 100, {"DOMINO_API_PROXY": "http://localhost:8899", "DOMINO_API_HOST": "http://api",
                    "DOMINO_PROJECT_OWNER": "alice", "DOMINO_PROJECT_NAME": "demo",
                    "DOMINO_PROJECT_ID": PID, "DOMINO_IS_GIT_BASED": "false",
                    "DOMINO_WORKING_DIR": "/mnt", "DOMINO_USER_API_KEY": "secret",
                    "DOMINO_RUN_ID": "run1"}),
    ])
    env = {"HOME": "/home/u", "DOMINO_PROJECT_NAME": "preset"}
    recovered = server._recover_domino_env(env, proc=proc, start_pid=300)
    assert set(recovered) == {"DOMINO_API_HOST", "DOMINO_API_PROXY", "DOMINO_PROJECT_ID",
                              "DOMINO_PROJECT_OWNER", "DOMINO_IS_GIT_BASED", "DOMINO_WORKING_DIR",
                              "DOMINO_RUN_ID"}
    assert env["DOMINO_API_PROXY"] == "http://localhost:8899"
    assert env["DOMINO_IS_GIT_BASED"] == "false" and env["DOMINO_WORKING_DIR"] == "/mnt"
    assert env["DOMINO_PROJECT_NAME"] == "preset"          # existing values are kept
    assert "DOMINO_USER_API_KEY" not in env                 # only the listed names are copied


def test_recovery_is_a_no_op_when_already_set_or_without_procfs(server, tmp_path):
    proc = _fake_proc(tmp_path, [(300, 1, {"DOMINO_API_PROXY": "http://localhost:8899"})])
    env = {"DOMINO_API_PROXY": "http://set"}
    assert server._recover_domino_env(env, proc=proc, start_pid=300) == []
    assert env == {"DOMINO_API_PROXY": "http://set"}
    env = {}
    assert server._recover_domino_env(env, proc=str(tmp_path / "no-proc"), start_pid=300) == []
    assert env == {}


def test_recovery_stops_at_depth_or_pid_1(server, tmp_path):
    proc = _fake_proc(tmp_path, [(300, 1, {"HOME": "/home/u"})])
    env = {}
    assert server._recover_domino_env(env, proc=proc, start_pid=300) == []


def test_import_is_hermetic_under_the_test_fixture(server):
    """The fixture pins os.getppid to 1, so import-time recovery cannot read the real /proc."""
    assert "DOMINO_API_PROXY" not in os.environ and not server._is_domino_workspace()


# ---------------------------------------------------------------------------------------------
# get_domino_environment_info: DFS detection from DOMINO_IS_GIT_BASED, not from `git status`
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("flag, expected_git, expected_dfs", [
    ("true", True, False), ("True", True, False), ("false", False, True), ("FALSE", False, True),
])
def test_environment_info_inside_domino(server, clean_env, run, flag, expected_git, expected_dfs):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_PROJECT_OWNER", OWNER)
    clean_env.setenv("DOMINO_PROJECT_NAME", PROJECT)
    clean_env.setenv("DOMINO_PROJECT_ID", PID)
    clean_env.setenv("DOMINO_IS_GIT_BASED", flag)
    clean_env.setenv("DOMINO_WORKING_DIR", "/mnt/code")
    info = run(server.get_domino_environment_info())
    assert info["inside_domino_workspace"] is True
    assert info["auth_mode"] == "api_proxy"
    assert info["domino_host"] == "http://localhost:8899"
    assert info["user_name"] == OWNER and info["project_name"] == PROJECT and info["project_id"] == PID
    assert info["is_git_based"] is expected_git and info["is_dfs_project"] is expected_dfs
    assert info["working_dir"] == "/mnt/code"
    assert "error" not in info


def test_environment_info_inside_domino_without_flag_probes_working_dir(server, clean_env, run, tmp_path, monkeypatch):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_WORKING_DIR", str(tmp_path))
    calls = []

    class Result:
        returncode, stdout = 0, "true\n"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Result()
    monkeypatch.setattr("subprocess.run", fake_run)
    info = run(server.get_domino_environment_info())
    assert info["is_git_based"] is True and info["is_dfs_project"] is False
    assert calls and calls[0][:3] == ["git", "-C", str(tmp_path)]   # probes the project, not the server's cwd


def test_environment_info_outside_domino_reports_missing_config(server, clean_env, run):
    info = run(server.get_domino_environment_info())
    assert info["inside_domino_workspace"] is False
    assert info["auth_mode"] == "none"
    assert info["domino_host"] is None
    assert "DOMINO_HOST" in info["error"] and "DOMINO_TOKEN" in info["error"]
    assert info["is_dfs_project"] is None


def test_environment_info_outside_domino_with_token(server, clean_env, http, run):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")
    clean_env.setenv("DOMINO_API_KEY", "legacy")
    http.add("GET", "/api/users/v1/self", FakeResponse(200, {"user": {"userName": "jane"}}))
    info = run(server.get_domino_environment_info())
    assert info["auth_mode"] == "bearer_token" and info["domino_host"] == "https://domino.example.com"
    assert "error" not in info and "DOMINO_TOKEN" in info["warning"]
    assert info["connection"] == {"ok": True, "authenticated_as": "jane"}


def test_environment_info_connection_reports_a_rejected_token_with_the_fix(server, clean_env, http, run):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "expired")
    http.add("GET", "/api/users/v1/self", FakeResponse(401, {"message": "Unauthorized"}))
    connection = run(server.get_domino_environment_info())["connection"]
    assert connection["ok"] is False
    assert "401" in connection["error"] and "DOMINO_TOKEN" in connection["error"]
    assert "Personal Access Token" in connection["error"]


def test_environment_info_connection_reports_an_unreachable_host(server, clean_env, http, run):
    clean_env.setenv("DOMINO_HOST", "https://wrong.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")

    def refuse(kwargs):
        raise server.requests.ConnectionError("Name or service not known")
    http.add("GET", "/api/users/v1/self", refuse)
    connection = run(server.get_domino_environment_info())["connection"]
    assert connection["ok"] is False and "reach" in connection["error"]


def test_environment_info_makes_no_call_without_credentials(server, clean_env, http, run):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    info = run(server.get_domino_environment_info())
    assert "connection" not in info and http.calls == []
    assert info["credential_sources"] == {"DOMINO_HOST": "not set", "DOMINO_TOKEN": "not set"}


def test_plugin_options_win_over_the_environment_and_leave_no_trace(clean_env, tmp_path):
    env_file = tmp_path / "mcp.env"
    env_file.write_text("DOMINO_HOST=https://from-file.example.com\nDOMINO_TOKEN=file-token\n")
    clean_env.setenv("DOMINO_MCP_ENV_FILE", str(env_file))
    clean_env.setenv("DOMINO_HOST", "https://from-shell.example.com")
    clean_env.setenv("DOMINO_PLUGIN_HOST", " https://from-plugin.example.com ")
    clean_env.setenv("DOMINO_PLUGIN_TOKEN", "plugin-token")
    module = import_server()
    assert module._get_domino_host() == "https://from-plugin.example.com"
    assert module._get_auth_headers() == {"Authorization": "Bearer plugin-token"}
    assert "DOMINO_PLUGIN_HOST" not in os.environ and "DOMINO_PLUGIN_TOKEN" not in os.environ
    assert module._CONFIG_SOURCES == {"DOMINO_HOST": "plugin options", "DOMINO_TOKEN": "plugin options"}


def test_unset_plugin_options_fall_back_to_environment_then_env_file(clean_env, tmp_path):
    env_file = tmp_path / "mcp.env"
    env_file.write_text("DOMINO_TOKEN=file-token\n")
    clean_env.setenv("DOMINO_MCP_ENV_FILE", str(env_file))
    clean_env.setenv("DOMINO_PLUGIN_HOST", "${user_config.domino_host}")   # option never set
    clean_env.setenv("DOMINO_PLUGIN_TOKEN", "")                             # option left empty
    clean_env.setenv("DOMINO_HOST", "https://from-shell.example.com")
    module = import_server()
    assert module._get_domino_host() == "https://from-shell.example.com"
    assert module._get_auth_headers() == {"Authorization": "Bearer file-token"}
    assert module._CONFIG_SOURCES == {"DOMINO_HOST": "environment", "DOMINO_TOKEN": f"env file {env_file}"}


def test_open_web_browser_is_a_no_op_inside_domino(server, clean_env, monkeypatch, run):
    opened = []
    monkeypatch.setattr(server.webbrowser, "open_new_tab", lambda url: opened.append(url) or True)
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    assert run(server.open_web_browser("https://example.com/x")) is False and opened == []
    clean_env.delenv("DOMINO_API_PROXY")
    assert run(server.open_web_browser("https://example.com/x")) is True and opened == ["https://example.com/x"]
    assert run(server.open_web_browser("file:///etc/passwd")) is False


# ---------------------------------------------------------------------------------------------
# Jobs on the Public API
# ---------------------------------------------------------------------------------------------

@pytest.fixture
def laptop(clean_env):
    clean_env.setenv("DOMINO_HOST", "https://domino.example.com")
    clean_env.setenv("DOMINO_TOKEN", "t")
    return clean_env


def test_run_domino_job_posts_public_api_body(server, laptop, http, run):
    _add_project_lookup(http)
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {
        "id": "job1", "number": 7, "runCommand": "python train.py --name \"my run\"", "title": "t",
        "status": {"executionStatus": "Queued", "isCompleted": False, "isArchived": False}}}))
    result = run(server.run_domino_job(OWNER, PROJECT, 'python train.py --name "my run"', "t"))
    method, path, kwargs = http.calls[-1]
    assert (method, path) == ("POST", "/api/jobs/v1/jobs")
    assert kwargs["json"] == {"projectId": PID, "runCommand": 'python train.py --name "my run"', "title": "t"}
    assert result["job_id"] == "job1" and result["run_id"] == "job1" and result["status"] == "Queued"
    # project lookup is cached for the process
    run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t2", git_branch="feature/x"))
    assert sum(1 for m, p, _ in http.calls if p == "/api/projects/beta/projects") == 1
    assert http.calls[-1][2]["json"]["mainRepoGitRef"] == {"refType": "branches", "value": "feature/x"}


def test_run_domino_job_inside_domino_uses_platform_project_id(server, clean_env, http, run):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_PROJECT_OWNER", OWNER)
    clean_env.setenv("DOMINO_PROJECT_NAME", PROJECT)
    clean_env.setenv("DOMINO_PROJECT_ID", PID)
    clean_env.setenv("DOMINO_IS_GIT_BASED", "false")
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t"))
    method, path, kwargs = http.calls[-1]
    assert kwargs["base"] == "http://localhost:8899" and kwargs["headers"] == {}
    assert kwargs["json"]["projectId"] == PID
    assert len(http.calls) == 1   # no project lookup


def test_project_lookup_paginates_until_an_empty_page(server, laptop, http):
    """The server may cap the page size below what was asked; only an empty page ends the scan."""
    pages = {0: [{"id": f"{i:024x}", "name": f"p{i}", "ownerUsername": OWNER} for i in range(10)],
             10: [{"id": f"{i:024x}", "name": f"p{i}", "ownerUsername": OWNER} for i in range(10, 20)],
             20: [{"id": PID, "name": PROJECT, "ownerUsername": OWNER}]}
    seen = []

    def handler(kw):
        seen.append(kw["params"]["offset"])
        return FakeResponse(200, {"projects": pages.get(kw["params"]["offset"], []), "metadata": {}})
    http.add("GET", "/api/projects/beta/projects", handler)
    assert server._resolve_project_id(OWNER, PROJECT) == PID
    assert seen == [0, 10, 20]
    with pytest.raises(server.DominoError) as err:
        server._resolve_project_id(OWNER, "missing")
    assert "not found" in str(err.value)
    assert seen[3:] == [0, 10, 20, 21]        # scanned to the empty page, no premature stop


def test_project_lookup_stops_at_total_count(server, laptop, http):
    seen = []

    def handler(kw):
        seen.append(kw["params"]["offset"])
        return FakeResponse(200, {"projects": [{"id": "a" * 24, "name": "x", "ownerUsername": OWNER}],
                                  "metadata": {"totalCount": 1}})
    http.add("GET", "/api/projects/beta/projects", handler)
    with pytest.raises(server.DominoError):
        server._resolve_project_id(OWNER, "missing")
    assert seen == [0]


def test_project_lookup_gives_up_only_at_the_hard_cap(server, laptop, http, monkeypatch):
    monkeypatch.setattr(server, "_PROJECT_MAX_PAGES", 3)
    http.add("GET", "/api/projects/beta/projects",
             lambda kw: FakeResponse(200, {"projects": [{"id": "a" * 24, "name": "x", "ownerUsername": OWNER}], "metadata": {}}))
    with pytest.raises(server.DominoError) as err:
        server._resolve_project_id(OWNER, "missing")
    assert "Gave up" in str(err.value)


def test_check_job_status_uses_public_job_route(server, laptop, http, run):
    http.add("GET", "/api/jobs/beta/jobs/job1", FakeResponse(200, {"job": {
        "id": "job1", "number": 3, "runCommand": "main.py",
        "status": {"executionStatus": "Succeeded", "isCompleted": True, "isArchived": False, "isScheduled": False},
        "stageTimes": {"completedTime": "2026-05-24T23:29:14.169Z"},
        "dominoStats": [{"name": "R^2", "value": "0.5157"}]}}))
    result = run(server.check_domino_job_run_status("job1", OWNER, PROJECT))
    assert result["status"] == "Succeeded" and result["is_completed"] is True
    assert result["run_id"] == "job1" and result["domino_stats"][0]["name"] == "R^2"
    with pytest.raises(server.DominoError):
        run(server.check_domino_job_run_status("../x"))


def test_check_job_results_pages_logs_and_rewrites_mlflow_url(server, laptop, http, run):
    pages = [
        {"logs": {"logContent": [{"timestamp": "1", "log": "### Starting user code ###"}, {"timestamp": "2", "log": "hello"},
                                 {"timestamp": "3", "log": "View run at: http://127.0.0.1:8768/#/experiments/12/runs/abc123"}],
                  "isComplete": False},
         "metadata": {"pagination": {"limit": 1000, "latestTimeNano": "100"}}},
        {"logs": {"logContent": [{"timestamp": "3", "log": "View run at: http://127.0.0.1:8768/#/experiments/12/runs/abc123"},
                                 {"timestamp": "4", "log": "done"}, {"timestamp": "5", "log": "### User code finished ###"}],
                  "isComplete": True},
         "metadata": {"pagination": {"limit": 1000, "latestTimeNano": "200"}}},
    ]
    seen = []

    def handler(kw):
        seen.append(kw["params"])
        return FakeResponse(200, pages[len(seen) - 1])
    http.add("GET", "/api/jobs/beta/jobs/job1/logs", handler)
    result = run(server.check_domino_job_run_results("job1", OWNER, PROJECT))
    assert seen[0] == {"logType": "stdOut", "limit": server._LOG_PAGE_LIMIT}
    assert seen[1]["latestTimeNano"] == "100"
    assert result["results"] == "hello\ndone"              # boundary line repeated by the cursor is dropped
    assert result["mlflow_url"] == f"https://domino.example.com/experiments/{OWNER}/{PROJECT}/12/abc123"
    assert result["mlflow_path"] == f"/experiments/{OWNER}/{PROJECT}/12/abc123"
    assert result["is_complete"] is True and result["line_count"] == 5


def test_mlflow_link_inside_domino_without_external_host_gives_path_only(server, clean_env, http, run):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_API_HOST", "http://nucleus-frontend.domino-platform:80")
    http.add("GET", "/api/jobs/beta/jobs/job1/logs", FakeResponse(200, {
        "logs": {"logContent": [{"log": "http://127.0.0.1:8768/#/experiments/1/runs/aa"}], "isComplete": True}, "metadata": {}}))
    result = run(server.check_domino_job_run_results("job1", OWNER, PROJECT))
    assert result["mlflow_path"] == f"/experiments/{OWNER}/{PROJECT}/1/aa" and "mlflow_url" not in result
    clean_env.setenv("VSCODE_PROXY_URI", "https://domino.example.com/vscode/{{port}}/")
    result = run(server.check_domino_job_run_results("job1", OWNER, PROJECT))
    assert result["mlflow_url"] == f"https://domino.example.com/experiments/{OWNER}/{PROJECT}/1/aa"


def test_check_job_results_other_log_types(server, laptop, http, run):
    http.add("GET", "/api/jobs/beta/jobs/job1/logs",
             lambda kw: FakeResponse(200, {"logs": {"logContent": [], "isComplete": True}, "metadata": {}})
             if kw["params"]["logType"] == "stdErr" else FakeResponse(500))
    result = run(server.check_domino_job_run_results("job1", log_type="stdErr"))
    assert result["results"] == "(No output captured)" and "note" in result
    with pytest.raises(server.DominoError):
        run(server.check_domino_job_run_results("job1", log_type="nope"))


# ---------------------------------------------------------------------------------------------
# Files: read on the Public API, list on the Internal API, upload on the legacy v1 API
# ---------------------------------------------------------------------------------------------

def test_list_files_uses_internal_browse_routes(server, laptop, http, run):
    http.add("GET", "/v4/files/browseFiles", FakeResponse(200, [
        {"path": "results/stdout.txt", "name": "stdout.txt", "size": 23, "lastModified": 1, "key": "k", "goalIds": []}]))
    http.add("GET", "/v4/files/browseDirectories", FakeResponse(200, [{"path": "results/sub", "name": "sub", "sizeInBytes": 1}]))
    result = run(server.list_domino_project_files(OWNER, PROJECT, "results"))
    assert result["files"][0]["path"] == "results/stdout.txt" and result["files"][0]["key"] == "k"
    assert result["directories"] == [{"path": "results/sub", "name": "sub"}]
    assert result["count"] == 1 and result["path"] == "results"
    assert http.calls[0][2]["params"] == {"ownerUsername": OWNER, "projectName": PROJECT, "filePath": "results"}


def test_download_reads_nested_path_at_latest_commit(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "scripts/train.py", b"print(1)\n")
    result = run(server.download_file_from_domino_project(OWNER, PROJECT, "/scripts/train.py"))
    assert result["content"] == "print(1)\n" and result["commitId"] == COMMIT
    assert result["key"] == hashlib.sha1(b"print(1)\n").hexdigest()
    assert any(p == f"/api/projects/v1/projects/{PID}/files/{COMMIT}/scripts%2Ftrain.py/content" for _, p, _ in http.calls)
    assert server._file_version_cache[(OWNER, PROJECT, "scripts/train.py")]["key"] == result["key"]


def test_download_missing_file_is_an_error_not_empty_content(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "nope.py", None)
    with pytest.raises(server.DominoError) as err:
        run(server.download_file_from_domino_project(OWNER, PROJECT, "nope.py"))
    assert "does not exist" in str(err.value)
    assert (OWNER, PROJECT, "nope.py") not in server._file_version_cache


@pytest.mark.parametrize("bad", ["", "/", "../etc/passwd", "a/../b", "dir/", "a?b", "a#b"])
def test_path_validation(server, bad):
    with pytest.raises(server.DominoError):
        server._normalize_project_path(bad)


def test_upload_refuses_existing_file_without_overwrite(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "scripts/train.py", b"old")
    _add_upload(http, "scripts/train.py")
    with pytest.raises(server.DominoError) as err:
        run(server.upload_file_to_domino_project(OWNER, PROJECT, "scripts/train.py", "new"))
    assert "already exists" in str(err.value) and "smart_sync_file" in str(err.value)
    assert not _puts(http)
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "scripts/train.py", "new", overwrite=True))
    assert result["success"] and result["key"] == hashlib.sha1(b"new").hexdigest()   # local key, not the server's
    assert result["commitId"] == COMMIT
    method, path, kwargs = _puts(http)[-1]
    assert (method, path) == ("PUT", f"/v1/projects/{OWNER}/{PROJECT}/scripts/train.py")
    assert kwargs["data"] == b"new"


def test_upload_creates_missing_file_and_reports_no_change(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "new.py", None)
    _add_upload(http, "new.py")
    assert run(server.upload_file_to_domino_project(OWNER, PROJECT, "new.py", "x"))["success"]
    assert len(_puts(http)) == 1
    _add_file(http, "same.py", b"x")
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "same.py", "x"))
    assert result["action"] == "no_change" and len(_puts(http)) == 1


def test_sync_local_file_reads_and_uploads(server, laptop, http, run, tmp_path):
    _add_project_lookup(http)
    local = tmp_path / "train.py"
    local.write_text("print('hi')\n")
    _add_file(http, "train.py", None)
    _add_upload(http, "train.py")
    result = run(server.sync_local_file_to_domino(OWNER, PROJECT, str(local)))
    assert result["path"] == "train.py" and _puts(http)[-1][2]["data"] == b"print('hi')\n"
    with pytest.raises(server.DominoError):
        run(server.sync_local_file_to_domino(OWNER, PROJECT, str(tmp_path / "missing.py")))


# ---------------------------------------------------------------------------------------------
# "Missing" is concluded only from a 404 or a 403 confirmed by the directory listing
# ---------------------------------------------------------------------------------------------

def test_404_means_missing(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", None, missing_status=404)
    _add_upload(http, "a.py")
    assert run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x"))["action"] == "created"
    assert not any(p == "/v4/files/browseFiles" for _, p, _ in http.calls)


def test_403_with_file_present_in_listing_is_an_error_and_never_overwrites(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "scripts/a.py", None, listing=["scripts/a.py", "scripts/b.py"])
    _add_upload(http, "scripts/a.py")
    for call in (lambda: server.smart_sync_file(OWNER, PROJECT, "scripts/a.py", "x"),
                 lambda: server.smart_sync_file(OWNER, PROJECT, "scripts/a.py", "x", force_overwrite=True),
                 lambda: server.upload_file_to_domino_project(OWNER, PROJECT, "scripts/a.py", "x"),
                 lambda: server.download_file_from_domino_project(OWNER, PROJECT, "scripts/a.py")):
        with pytest.raises(server.DominoError) as err:
            run(call())
        assert "directory listing shows it" in str(err.value) and "Nothing was changed" in str(err.value)
    assert not _puts(http)
    listing_calls = [c for c in http.calls if c[1] == "/v4/files/browseFiles"]
    assert listing_calls and listing_calls[0][2]["params"]["filePath"] == "scripts"


def test_403_with_failing_listing_is_an_error_and_never_overwrites(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", None)
    http.add("GET", "/v4/files/browseFiles", FakeResponse(403, {"message": "forbidden"}))
    _add_upload(http, "a.py")
    with pytest.raises(server.DominoError) as err:
        run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x", force_overwrite=True))
    assert "HTTP 403" in str(err.value) and not _puts(http)


def test_403_confirmed_absent_by_listing_creates(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "scripts/new.py", None, listing=["scripts/other.py"])
    _add_upload(http, "scripts/new.py")
    assert run(server.smart_sync_file(OWNER, PROJECT, "scripts/new.py", "x"))["action"] == "created"
    assert [c[2]["params"]["filePath"] for c in http.calls if c[1] == "/v4/files/browseFiles"] == ["scripts"]


def test_other_errors_on_read_never_lead_to_an_upload(server, laptop, http, run):
    _add_project_lookup(http)
    http.add("GET", f"/api/projects/beta/projects/{PID}/commits/latest", FakeResponse(200, {"commitId": COMMIT}))
    http.add("GET", f"/api/projects/v1/projects/{PID}/files/{COMMIT}/a.py/content", FakeResponse(500, {"errors": ["boom"]}))
    _add_upload(http, "a.py")
    with pytest.raises(server.DominoError):
        run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x", force_overwrite=True))
    assert not _puts(http)


# ---------------------------------------------------------------------------------------------
# Git-based projects: writes refuse, reads and jobs still work
# ---------------------------------------------------------------------------------------------

def test_write_tools_refuse_git_based_project_from_lookup(server, laptop, http, run, tmp_path):
    _add_project_lookup(http, [{"id": PID, "name": PROJECT, "ownerUsername": OWNER, "mainRepository": GIT_REPO}])
    _add_upload(http, "a.py")
    local = tmp_path / "a.py"
    local.write_text("x")
    for call in (lambda: server.smart_sync_file(OWNER, PROJECT, "a.py", "x", force_overwrite=True),
                 lambda: server.upload_file_to_domino_project(OWNER, PROJECT, "a.py", "x", overwrite=True),
                 lambda: server.sync_local_file_to_domino(OWNER, PROJECT, str(local), overwrite=True)):
        with pytest.raises(server.DominoError) as err:
            run(call())
        assert "Git-based" in str(err.value) and "Commit and push" in str(err.value)
    assert not _puts(http)
    # jobs still start on a Git-based project
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    assert run(server.run_domino_job(OWNER, PROJECT, "python a.py", "t"))["job_id"] == "j"


def test_write_tools_refuse_git_based_project_inside_domino(server, clean_env, http, run):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_PROJECT_OWNER", OWNER)
    clean_env.setenv("DOMINO_PROJECT_NAME", PROJECT)
    clean_env.setenv("DOMINO_PROJECT_ID", PID)
    clean_env.setenv("DOMINO_IS_GIT_BASED", "true")
    with pytest.raises(server.DominoError) as err:
        run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x"))
    assert "Git-based" in str(err.value) and http.calls == []


def test_inside_domino_without_flag_asks_the_api_whether_git_based(server, clean_env, http, run):
    clean_env.setenv("DOMINO_API_PROXY", "http://localhost:8899")
    clean_env.setenv("DOMINO_PROJECT_OWNER", OWNER)
    clean_env.setenv("DOMINO_PROJECT_NAME", PROJECT)
    clean_env.setenv("DOMINO_PROJECT_ID", PID)
    http.add("GET", f"/api/projects/v1/projects/{PID}",
             FakeResponse(200, {"project": {"id": PID, "name": PROJECT, "ownerUsername": OWNER, "mainRepository": GIT_REPO}}))
    with pytest.raises(server.DominoError) as err:
        run(server.upload_file_to_domino_project(OWNER, PROJECT, "a.py", "x"))
    assert "Git-based" in str(err.value) and not _puts(http)


# ---------------------------------------------------------------------------------------------
# smart_sync_file: never overwrites a file it has not seen
# ---------------------------------------------------------------------------------------------

def test_smart_sync_creates_new_file(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "scripts/new.py", None)
    _add_upload(http, "scripts/new.py")
    result = run(server.smart_sync_file(OWNER, PROJECT, "scripts/new.py", "a = 1\n"))
    assert result["action"] == "created" and result["success"]
    assert len(_puts(http)) == 1
    assert server._file_version_cache[(OWNER, PROJECT, "scripts/new.py")]["key"] == hashlib.sha1(b"a = 1\n").hexdigest()


def test_smart_sync_nested_existing_file_is_a_conflict_not_an_overwrite(server, laptop, http, run):
    """The old implementation listed only the project root, saw nothing for scripts/train.py and
    'created' it, overwriting the remote file. The nested file must be found and protected."""
    _add_project_lookup(http)
    _add_file(http, "scripts/train.py", b"remote version\n")
    _add_upload(http, "scripts/train.py")
    result = run(server.smart_sync_file(OWNER, PROJECT, "scripts/train.py", "my version\n"))
    assert result["conflict"] is True
    assert result["remote_content"] == "remote version\n"
    assert result["remote_key"] == hashlib.sha1(b"remote version\n").hexdigest()
    assert "Nothing was uploaded" in result["message"]
    assert not _puts(http)


def test_smart_sync_identical_content_is_no_change(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"same\n")
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "same\n"))
    assert result["action"] == "no_change" and not _puts(http)


def test_smart_sync_uploads_when_baseline_matches_remote(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    _add_upload(http, "a.py")
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v2\n"))
    assert result["action"] == "uploaded" and _puts(http)[-1][2]["data"] == b"v2\n"
    assert server._file_version_cache[(OWNER, PROJECT, "a.py")]["key"] == hashlib.sha1(b"v2\n").hexdigest()


def test_smart_sync_detects_remote_change_since_download(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    _add_file(http, "a.py", b"someone else\n", commit="ab" * 20)
    _add_upload(http, "a.py")
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v2\n"))
    assert result["conflict"] is True
    assert result["your_base_key"] == hashlib.sha1(b"v1\n").hexdigest()
    assert result["remote_key"] == hashlib.sha1(b"someone else\n").hexdigest()
    assert result["original_content"] == "v1\n" and result["remote_content"] == "someone else\n"
    assert result["remote_size"] == len(b"someone else\n")
    assert not _puts(http)


def test_smart_sync_force_overwrite_replaces_and_reports_previous_key(server, laptop, http, run):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"remote\n")
    _add_upload(http, "a.py")
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "mine\n", force_overwrite=True))
    assert result["action"] == "force_overwritten"
    assert result["previous_remote_key"] == hashlib.sha1(b"remote\n").hexdigest()
    assert _puts(http)[-1][2]["data"] == b"mine\n"


# ---------------------------------------------------------------------------------------------
# Server surface
# ---------------------------------------------------------------------------------------------

def test_tool_names_schemas_and_instructions(server, run):
    tools = {t.name: t for t in run(server.mcp.list_tools())}
    schema = {name: t.input_schema for name, t in tools.items()}   # mcp.types.Tool (SDK 2.x, snake_case)
    assert set(tools) == {
        "check_domino_job_run_results", "check_domino_job_run_status", "run_domino_job",
        "open_web_browser", "get_domino_environment_info", "list_domino_project_files",
        "upload_file_to_domino_project", "download_file_from_domino_project",
        "sync_local_file_to_domino", "smart_sync_file",
    }
    # the thread wrapper keeps the real signature, so the schema has the real parameters
    assert set(schema["run_domino_job"]["properties"]) == {
        "user_name", "project_name", "run_command", "title", "git_branch", "hardware_tier", "environment_id", "wait_seconds", "commit_id"}
    assert "commitId" in tools["upload_file_to_domino_project"].description
    assert "commitId" in tools["sync_local_file_to_domino"].description
    assert "commitId" in tools["smart_sync_file"].description
    assert set(schema["smart_sync_file"]["properties"]) >= {"content", "content_base64"}
    assert schema["smart_sync_file"]["required"] == ["user_name", "project_name", "file_path"]
    assert "wait_seconds" in schema["check_domino_job_run_status"]["properties"]
    assert "wait_seconds=300" in tools["check_domino_job_run_status"].description
    assert "conflict detection" in tools["smart_sync_file"].description
    instructions = server._plugin_instructions()
    rules = (Path(server.__file__).resolve().parents[2] / "rules" / "domino.md").read_text(encoding="utf-8")
    lead = rules.split("\n---\n", 2)[-1].split("\n## ", 1)[0].strip()
    assert instructions == lead
    # The lead's wording is the rules file's business; the server only needs it to identify
    # Domino and carry the in-run auth rule it is the single source for.
    first_line = instructions.splitlines()[0]
    assert "Domino" in first_line and "DOMINO_API_PROXY" in instructions
    assert len(lead.encode()) <= 900, "rules/domino.md lead section would be truncated"


def test_tool_errors_are_reported_as_mcp_errors(server, clean_env, run):
    """The SDK turns a raised DominoError (a ToolError) into an isError result with its message."""
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError) as err:
        run(server.mcp.call_tool("check_domino_job_run_status", {"run_id": "job1"}))
    assert "DOMINO_HOST" in str(err.value)


def test_tools_run_through_the_sdk_with_the_threaded_wrapper(server, laptop, http, run):
    http.add("GET", "/api/jobs/beta/jobs/job1", FakeResponse(200, {"job": {
        "id": "job1", "status": {"executionStatus": "Running", "isCompleted": False}}}))
    result = run(server.mcp.call_tool("check_domino_job_run_status", {"run_id": "job1"}))
    import json
    text = " ".join(getattr(c, "text", "") for c in result.content)
    assert json.loads(text)["status"] == "Running"
    assert result.structured_content is None          # JSON text is the contract; no "result" wrapper


@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
def test_client_identity_is_captured_at_the_first_tool_call(server, laptop, http, run, mode):
    """The Codex cap depends on the client name; it must be read from the SDK connection's
    client params for handshake-era and 2026-07-28 clients alike, at tool-call time."""
    from mcp import Client
    from mcp.types import Implementation
    http.add("GET", "/api/jobs/beta/jobs/job1", FakeResponse(200, {"job": {"id": "job1", "status": {"executionStatus": "Queued", "isCompleted": False}}}))

    async def go():
        async with Client(server.mcp, client_info=Implementation(name="codex-test", version="1"), mode=mode) as c:
            await c.list_tools()
            assert server._CLIENT_NAME == "codex-test"             # the tools/list hook saw it first
            server._CLIENT_NAME = server._CLIENT_PROTOCOL = ""     # the tool-call path must work on its own
            res = await c.call_tool("check_domino_job_run_status", {"run_id": "job1"})
            assert not res.is_error
    run(go())
    assert server._CLIENT_NAME == "codex-test"
    assert server._CLIENT_PROTOCOL == ("2026-07-28" if mode == "2026-07-28" else "2025-11-25")
    assert server._wait_cap() == server._WAIT_CAP_CODEX


def test_tool_errors_reach_the_client_with_their_message(server, clean_env, run):
    """Through a real client, a DominoError's text arrives; the SDK masks other exceptions."""
    from mcp import Client

    async def go():
        async with Client(server.mcp) as c:
            res = await c.call_tool("check_domino_job_run_status", {"run_id": "job1"})
            assert res.is_error and "DOMINO_HOST" in " ".join(x.text for x in res.content)
    run(go())


def test_tool_descriptions_keep_args_and_returns(server, run):
    tools = {t.name: t for t in run(server.mcp.list_tools())}
    desc = tools["upload_file_to_domino_project"].description
    assert "Args:" in desc and "Returns:" in desc and "commitId" in desc
    assert "overwrite (bool)" in desc and "overwrite" in tools["upload_file_to_domino_project"].input_schema["properties"]
    assert "ctx" not in tools["upload_file_to_domino_project"].input_schema["properties"]


# ---------------------------------------------------------------------------------------------
# Read-after-write lag: own writes are waited for; another client's later write still conflicts
# ---------------------------------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def clock(server, monkeypatch):
    """Every test runs on a fake clock: the server's waits and sleeps never take real time."""
    c = FakeClock()
    monkeypatch.setattr(server.time, "monotonic", c.monotonic)
    monkeypatch.setattr(server.time, "sleep", c.sleep)
    return c


def _add_read_sequence(http, path, contents):
    """Successive content reads return successive items (bytes, or None for "missing"); the last repeats."""
    http.add("GET", f"/api/projects/beta/projects/{PID}/commits/latest", FakeResponse(200, {"commitId": COMMIT, "metadata": {}}))
    _add_listing(http, [])
    served = []

    def handler(kw):
        item = contents[min(len(served), len(contents) - 1)]
        served.append(item)
        if item is None:
            return FakeResponse(403, {"errors": [f"Not authorized: File {path} ... are not valid."]})
        return FakeResponse(200, content=item)
    http.add("GET", f"/api/projects/v1/projects/{PID}/files/{COMMIT}/{path.replace('/', '%2F')}/content", handler)
    return served


def _baseline_then_upload(server, http, run, path="a.py"):
    """download v1 (baseline), then smart_sync v2 which uploads and is confirmed; sleeps cleared."""
    _add_project_lookup(http)
    _add_file(http, path, b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, path))
    _add_upload(http, path)
    assert run(server.smart_sync_file(OWNER, PROJECT, path, "v2\n"))["action"] == "uploaded"


def test_stale_read_after_own_upload_is_waited_out_by_the_upload(server, laptop, http, run, clock):
    """Right after our write the files API still shows the previous version: the upload tool
    re-reads until it shows ours and only then reports commitId; no false conflict later."""
    _add_project_lookup(http)
    _add_file(http, "a.py", b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    _add_upload(http, "a.py", visible_at=None)
    served = _add_read_sequence(http, "a.py", [b"v1\n", b"v1\n", b"v1\n", b"v2\n"])   # pre-write read, then stale, then ours
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v2\n"))
    assert result["action"] == "uploaded" and result["commitId"] == COMMIT
    assert served == [b"v1\n", b"v1\n", b"v1\n", b"v2\n"] and clock.sleeps == [2.0, 2.0]
    clock.sleeps.clear()
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v3\n"))     # remote now shows v2 = our baseline
    assert result["action"] == "uploaded" and _puts(http)[-1][2]["data"] == b"v3\n"


def test_create_waits_until_the_file_is_visible_and_later_reads_do_not_wait(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_upload(http, "new.py", visible_at=None)
    served = _add_read_sequence(http, "new.py", [None, None, None, b"x\n"])   # pre-write, two stale, visible
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "new.py", "x\n"))
    assert result["success"] and result["commitId"] == COMMIT and len(clock.sleeps) == 2
    result = run(server.download_file_from_domino_project(OWNER, PROJECT, "new.py"))
    assert result["content"] == "x\n" and len(served) == 5 and len(clock.sleeps) == 2


def test_another_clients_newer_write_during_confirmation_is_not_mistaken_for_ours(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    _add_upload(http, "a.py", visible_at=None)
    served = _add_read_sequence(http, "a.py", [b"v1\n", b"v1\n", b"v3\n"])   # pre-write, stale, then someone else's v3
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v2\n"))
    assert result["action"] == "uploaded" and result["commitId"] is None and "note" in result
    assert clock.sleeps == [2.0]                                                # stopped as soon as a foreign key appeared
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v4\n"))
    assert result["conflict"] is True and result["remote_content"] == "v3\n"
    assert result["your_base_key"] == hashlib.sha1(b"v2\n").hexdigest()
    assert "note" not in result and not any(c[2]["data"] == b"v4\n" for c in _puts(http))


def test_visibility_timeout_is_reported_and_blocks_a_job(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_file(http, "a.py", b"v1\n")
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    _add_upload(http, "a.py", visible_at=None)
    _add_read_sequence(http, "a.py", [b"v1\n"])                                # never catches up
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v2\n"))
    assert result["action"] == "uploaded" and result["commitId"] is None
    assert "does not show it yet" in result["note"] and sum(clock.sleeps) >= server._WRITE_VISIBILITY_TIMEOUT
    clock.sleeps.clear()
    posted = []
    http.add("POST", "/api/jobs/v1/jobs", lambda kw: posted.append(kw["json"]) or FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python a.py", "t"))
    assert "a.py" in str(err.value) and posted == [] and sum(clock.sleeps) >= server._WRITE_VISIBILITY_TIMEOUT
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "v3\n"))
    assert result["conflict"] is True and "lag" in result["note"] and result["remote_content"] == "v1\n"


def test_run_domino_job_waits_once_for_recent_uploads(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_upload(http, "scripts/train.py", visible_at=None)
    served = _add_read_sequence(http, "scripts/train.py", [None, None, b"print(42)\n"])
    up = run(server.upload_file_to_domino_project(OWNER, PROJECT, "scripts/train.py", "print(42)\n"))
    assert up["commitId"] == COMMIT and clock.sleeps == [2.0]
    posted = []
    http.add("POST", "/api/jobs/v1/jobs", lambda kw: posted.append(kw["json"]) or FakeResponse(200, {"job": {"id": "j1", "status": {}}}))
    assert run(server.run_domino_job(OWNER, PROJECT, "python scripts/train.py", "t"))["commit_id"] == COMMIT
    assert posted[0]["commitId"] == COMMIT and len(served) == 3 and clock.sleeps == [2.0]
    run(server.run_domino_job(OWNER, PROJECT, "python scripts/train.py", "t2"))   # confirmed: no reads, no wait
    assert len(served) == 3 and clock.sleeps == [2.0] and posted[1]["commitId"] == COMMIT


def test_run_domino_job_pin_wait_has_one_budget_for_all_files(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    for name in ("one.py", "two.py"):
        _add_upload(http, name, visible_at=None)
        _add_read_sequence(http, name, [None])
        run(server.upload_file_to_domino_project(OWNER, PROJECT, name, "x\n"))
    clock.sleeps.clear()
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python one.py", "t"))
    assert "one.py" in str(err.value) and "two.py" in str(err.value)
    assert server._WRITE_VISIBILITY_TIMEOUT <= sum(clock.sleeps) < 2 * server._WRITE_VISIBILITY_TIMEOUT


def test_reads_do_not_wait_without_a_recent_own_write(server, laptop, http, run, clock):
    _add_project_lookup(http)
    served = _add_read_sequence(http, "a.py", [b"v1\n"])
    run(server.download_file_from_domino_project(OWNER, PROJECT, "a.py"))
    assert len(served) == 1 and clock.sleeps == []


# ---------------------------------------------------------------------------------------------
# Waiting for a Job on the server (hosts block `sleep`)
# ---------------------------------------------------------------------------------------------

def _job_status_sequence(http, job_id, statuses):
    served = []

    def handler(kw):
        status = statuses[min(len(served), len(statuses) - 1)]
        served.append(status)
        return FakeResponse(200, {"job": {"id": job_id, "number": 5, "runCommand": "python x.py",
                                          "status": {"executionStatus": status, "isCompleted": status in ("Succeeded", "Failed", "Stopped")}}})
    http.add("GET", f"/api/jobs/beta/jobs/{job_id}", handler)
    return served


def test_check_status_waits_with_backoff_until_completed(server, laptop, http, run, clock):
    served = _job_status_sequence(http, "job1", ["Pending", "Preparing", "Running", "Running", "Succeeded"])
    result = run(server.check_domino_job_run_status("job1", wait_seconds=300))
    assert result["status"] == "Succeeded" and result["is_completed"] is True
    assert served == ["Pending", "Preparing", "Running", "Running", "Succeeded"]
    assert clock.sleeps == [3.0, 5.0, 7.0, 9.0] and result["waited_seconds"] == 24
    assert "message" not in result


def test_check_status_returns_partial_result_at_the_deadline(server, laptop, http, run, clock):
    served = _job_status_sequence(http, "job1", ["Pending"])
    result = run(server.check_domino_job_run_status("job1", wait_seconds=20))
    assert result["status"] == "Pending" and result["is_completed"] is False
    assert result["waited_seconds"] == 20 and sum(clock.sleeps) == 20
    assert "check_domino_job_run_status again" in result["message"] and "wait_seconds" in result["message"]
    assert "do not use shell sleep" in result["message"]
    assert len(served) == len(clock.sleeps) + 1


def test_check_status_without_wait_returns_at_once(server, laptop, http, run, clock):
    served = _job_status_sequence(http, "job1", ["Pending"])
    result = run(server.check_domino_job_run_status("job1"))
    assert result["status"] == "Pending" and result["waited_seconds"] == 0
    assert len(served) == 1 and clock.sleeps == [] and "message" in result


def test_wait_is_capped_per_host(server, laptop, http, run, clock, monkeypatch):
    _job_status_sequence(http, "job1", ["Running"])
    run(server.check_domino_job_run_status("job1", wait_seconds=100000))
    assert sum(clock.sleeps) == server._WAIT_CAP
    clock.sleeps.clear()
    monkeypatch.setattr(server, "_CLIENT_NAME", "codex (codex-cli)")
    result = run(server.check_domino_job_run_status("job1", wait_seconds=300))
    assert sum(clock.sleeps) == server._WAIT_CAP_CODEX and "up to 50 per call" in result["message"]


def test_run_domino_job_with_wait_returns_final_status_and_stdout_tail(server, laptop, http, run, clock):
    _add_project_lookup(http)
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "job9", "number": 9, "status": {"executionStatus": "Queued", "isCompleted": False}}}))
    _job_status_sequence(http, "job9", ["Queued", "Running", "Succeeded"])
    lines = [{"log": "### Starting user code ###"}] + [{"log": f"line {i}"} for i in range(150)] + [{"log": "42"}]
    http.add("GET", "/api/jobs/beta/jobs/job9/logs", FakeResponse(200, {"logs": {"logContent": lines, "isComplete": True}, "metadata": {}}))
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", wait_seconds=300))
    assert result["job_id"] == "job9" and result["status"] == "Succeeded" and result["is_completed"] is True
    assert result["waited_seconds"] == 8 and clock.sleeps == [3.0, 5.0]
    assert result["results"].endswith("line 149\n42") and result["results_truncated"] is True
    assert "line 0\n" not in result["results"] and "check_domino_job_run_results" in result["results_note"]
    assert "finished with status Succeeded" in result["message"]


def test_run_domino_job_with_wait_not_finished_says_how_to_continue(server, laptop, http, run, clock):
    _add_project_lookup(http)
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "job9", "number": 9, "status": {"executionStatus": "Queued", "isCompleted": False}}}))
    _job_status_sequence(http, "job9", ["Queued"])
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", wait_seconds=10))
    assert result["is_completed"] is False and result["waited_seconds"] == 10 and "results" not in result
    assert "run_id=job9" in result["message"] and "wait_seconds" in result["message"]


def test_run_domino_job_without_wait_points_at_wait_seconds(server, laptop, http, run):
    _add_project_lookup(http)
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t"))
    assert "wait_seconds=300" in result["message"] and "waited_seconds" not in result


# ---------------------------------------------------------------------------------------------
# Hardware tier and environment
# ---------------------------------------------------------------------------------------------

TIERS = [{"id": "small-k8s", "name": "Small", "flags": {"isDefault": True, "isArchived": False}},
         {"id": "gpu-k8s", "name": "GPU Large", "flags": {"isDefault": False, "isArchived": False}},
         {"id": "old-k8s", "name": "Old", "flags": {"isDefault": False, "isArchived": True}}]


def _add_tiers(http):
    http.add("GET", "/api/hardwaretiers/v1/hardwaretiers",
             lambda kw: FakeResponse(200, {"hardwareTiers": TIERS if kw["params"]["offset"] == 0 else [],
                                           "metadata": {"totalCount": len(TIERS)}}))


def test_run_domino_job_passes_a_validated_hardware_tier(server, laptop, http, run):
    _add_project_lookup(http)
    _add_tiers(http)
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", hardware_tier="small-k8s"))
    assert http.calls[-1][2]["json"]["hardwareTier"] == "small-k8s" and result["hardware_tier"] == "small-k8s"
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", hardware_tier="gpu large"))   # by name
    assert http.calls[-1][2]["json"]["hardwareTier"] == "gpu-k8s"
    assert sum(1 for c in http.calls if c[1] == "/api/hardwaretiers/v1/hardwaretiers") == 1   # cached
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", hardware_tier="huge-k8s"))
    assert "not found" in str(err.value) and "small-k8s (Small)" in str(err.value) and "old-k8s" not in str(err.value)
    with pytest.raises(server.DominoError):
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", hardware_tier="old-k8s"))   # archived
    assert sum(1 for c in http.calls if c[0] == "POST") == 2


def test_run_domino_job_passes_a_validated_environment(server, laptop, http, run):
    _add_project_lookup(http)
    envs = [{"id": "e" * 24, "name": "Domino Standard Environment", "archived": False, "owner": {"username": "admin"}},
            {"id": "f" * 24, "name": "Dup", "archived": False, "owner": {"username": "a"}},
            {"id": "a" * 24, "name": "Dup", "archived": False, "owner": {"username": "b"}}]
    http.add("GET", "/api/environments/beta/environments",
             lambda kw: FakeResponse(200, {"environments": envs if kw["params"]["offset"] == 0 else [], "metadata": {}}))
    http.add("POST", "/api/jobs/v1/jobs", FakeResponse(200, {"job": {"id": "j", "status": {}}}))
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", environment_id="e" * 24))
    assert http.calls[-1][2]["json"]["environmentId"] == "e" * 24 and result["environment_id"] == "e" * 24
    run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", environment_id="domino standard environment"))
    assert http.calls[-1][2]["json"]["environmentId"] == "e" * 24
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", environment_id="Dup"))
    assert "Several environments" in str(err.value)
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", environment_id="nope"))
    assert "not found" in str(err.value)


# ---------------------------------------------------------------------------------------------
# Binary files
# ---------------------------------------------------------------------------------------------

BINARY = bytes(range(256)) * 4   # not UTF-8


def test_sync_local_file_uploads_binary_bytes_unchanged(server, laptop, http, run, tmp_path):
    _add_project_lookup(http)
    local = tmp_path / "model.joblib"
    local.write_bytes(BINARY)
    _add_file(http, "model.joblib", None)
    _add_upload(http, "model.joblib")
    result = run(server.sync_local_file_to_domino(OWNER, PROJECT, str(local)))
    put = _puts(http)[-1]
    assert result["success"] and put[2]["data"] == BINARY
    assert put[2]["headers"]["Content-Type"] == "application/octet-stream"
    assert result["key"] == hashlib.sha1(BINARY).hexdigest() and result["size"] == len(BINARY)


def test_upload_and_smart_sync_accept_base64(server, laptop, http, run):
    import base64
    _add_project_lookup(http)
    _add_file(http, "a.bin", None)
    _add_upload(http, "a.bin")
    encoded = base64.b64encode(BINARY).decode()
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "a.bin", content_base64=encoded))
    assert result["success"] and _puts(http)[-1][2]["data"] == BINARY
    _add_file(http, "b.bin", None)
    _add_upload(http, "b.bin")
    result = run(server.smart_sync_file(OWNER, PROJECT, "b.bin", content_base64=encoded))
    assert result["action"] == "created" and _puts(http)[-1][2]["data"] == BINARY
    with pytest.raises(server.DominoError) as err:
        run(server.smart_sync_file(OWNER, PROJECT, "b.bin", content="x", content_base64=encoded))
    assert "exactly one" in str(err.value)
    with pytest.raises(server.DominoError):
        run(server.upload_file_to_domino_project(OWNER, PROJECT, "b.bin"))
    with pytest.raises(server.DominoError) as err:
        run(server.upload_file_to_domino_project(OWNER, PROJECT, "b.bin", content_base64="not base64!!"))
    assert "base64" in str(err.value)


def test_download_returns_binary_as_base64_and_detects_binary_conflicts(server, laptop, http, run):
    import base64
    _add_project_lookup(http)
    _add_file(http, "model.joblib", BINARY)
    result = run(server.download_file_from_domino_project(OWNER, PROJECT, "model.joblib"))
    assert result["encoding"] == "base64" and base64.b64decode(result["content_base64"]) == BINARY
    assert "content" not in result and result["size"] == len(BINARY)
    # identical bytes: no change
    assert run(server.smart_sync_file(OWNER, PROJECT, "model.joblib", content_base64=base64.b64encode(BINARY).decode()))["action"] == "no_change"
    # someone else replaced the binary: conflict carries base64, keys and sizes, no upload
    other = BINARY[::-1]
    _add_file(http, "model.joblib", other, commit="ab" * 20)
    _add_upload(http, "model.joblib")
    result = run(server.smart_sync_file(OWNER, PROJECT, "model.joblib", content_base64=base64.b64encode(BINARY + b"x").decode()))
    assert result["conflict"] is True and base64.b64decode(result["remote_content_base64"]) == other
    assert base64.b64decode(result["original_content_base64"]) == BINARY
    assert result["remote_key"] == hashlib.sha1(other).hexdigest() and not _puts(http)


def test_large_remote_file_is_compared_but_not_returned(server, laptop, http, run, monkeypatch):
    monkeypatch.setattr(server, "_MAX_RETURN_BYTES", 10)
    _add_project_lookup(http)
    big = b"x" * 11
    _add_file(http, "big.bin", big)
    result = run(server.download_file_from_domino_project(OWNER, PROJECT, "big.bin"))
    assert "content" not in result and "content_base64" not in result and "content_omitted" in result
    assert result["key"] == hashlib.sha1(big).hexdigest()
    assert run(server.smart_sync_file(OWNER, PROJECT, "big.bin", content="x" * 11))["action"] == "no_change"


# ---------------------------------------------------------------------------------------------
# Commit pinning: a Job started right after an upload runs the commit that contains the upload
# ---------------------------------------------------------------------------------------------

C2 = "ab" * 20
C3 = "cd" * 20


def _add_commit_sequence(http, commits):
    """commits/latest returns successive commit ids; the last repeats."""
    served = []

    def handler(kw):
        c = commits[min(len(served), len(commits) - 1)]
        served.append(c)
        return FakeResponse(200, {"commitId": c, "metadata": {}})
    http.add("GET", f"/api/projects/beta/projects/{PID}/commits/latest", handler)
    return served


def _add_content_at(http, commit, path, content):
    route = f"/api/projects/v1/projects/{PID}/files/{commit}/{path.replace('/', '%2F')}/content"
    if content is None:
        http.add("GET", route, FakeResponse(403, {"errors": [f"Not authorized: File {path} ... are not valid."]}))
    else:
        http.add("GET", route, FakeResponse(200, content=content))


def _job_post(http):
    posted = []

    def handler(kw):
        posted.append(kw["json"])
        return FakeResponse(200, {"job": {"id": "j1", "number": 1, "status": {"executionStatus": "Queued", "isCompleted": False}}})
    http.add("POST", "/api/jobs/v1/jobs", handler)
    return posted


def test_upload_returns_the_commit_that_contains_it(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, COMMIT, C2])       # the pre-upload read, then a stale read, then the new commit
    _add_content_at(http, COMMIT, "train.py", None)
    _add_content_at(http, C2, "train.py", b"v2\n")
    _add_upload(http, "train.py", visible_at=None)
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "v2\n"))
    assert result["success"] and result["commitId"] == C2 and clock.sleeps == [2.0]
    entry = server._recent_write_log[(OWNER, PROJECT, "train.py")]
    assert entry["visible"] and entry["commit_id"] == C2


def test_sync_local_and_smart_sync_return_commit_id(server, laptop, http, run, clock, tmp_path):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, C2])
    _add_content_at(http, COMMIT, "a.py", None)
    _add_content_at(http, C2, "a.py", b"x\n")
    _add_upload(http, "a.py", visible_at=None)
    local = tmp_path / "a.py"
    local.write_text("x\n")
    assert run(server.sync_local_file_to_domino(OWNER, PROJECT, str(local)))["commitId"] == C2
    server._file_version_cache.clear()
    http.calls.clear()
    _add_commit_sequence(http, [COMMIT, C2])
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x\n"))
    assert result["action"] == "created" and result["commitId"] == C2
    # identical content: no upload, but the commit it was read at is still reported
    _add_commit_sequence(http, [C2])
    result = run(server.smart_sync_file(OWNER, PROJECT, "a.py", "x\n"))
    assert result["action"] == "no_change" and result["commitId"] == C2


def test_upload_tolerates_listing_ahead_of_the_commit_index(server, laptop, http, run, clock):
    """Right after our own write the listing shows the file while the latest commit does not yet."""
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_upload(http, "a.py", visible_at=None)
    _add_commit_sequence(http, [COMMIT])
    _add_content_at(http, COMMIT, "a.py", None)
    posted = run(server.upload_file_to_domino_project(OWNER, PROJECT, "a.py", "x\n"))
    assert posted["success"]
    # the 403-but-listed case keeps polling instead of raising, and resolves once C2 appears
    server._recent_write_log[(OWNER, PROJECT, "a.py")]["visible"] = False
    _add_listing(http, ["a.py"])
    _add_commit_sequence(http, [COMMIT, COMMIT, C2])
    _add_content_at(http, C2, "a.py", b"x\n")
    state = server._remote_state(OWNER, PROJECT, "a.py", {"id": PID, "git_based": False})
    assert state["exists"] and state["commit_id"] == C2


def test_run_domino_job_pins_the_latest_commit_that_contains_recent_uploads(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, C2])
    _add_content_at(http, COMMIT, "train.py", None)
    _add_content_at(http, C2, "train.py", b"v2\n")
    _add_upload(http, "train.py", visible_at=None)
    assert run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "v2\n"))["commitId"] == C2
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == C2 and result["commit_id"] == C2


def test_run_domino_job_uses_a_newer_latest_commit_when_it_contains_the_uploads(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, C2, C3])           # pre-upload, confirmation, then at job start
    _add_content_at(http, COMMIT, "train.py", None)
    _add_content_at(http, C2, "train.py", b"v2\n")
    _add_content_at(http, C3, "train.py", b"v2\n")         # someone added another file after us
    _add_upload(http, "train.py", visible_at=None)
    run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "v2\n"))
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == C3 and result["commit_id"] == C3


def test_run_domino_job_falls_back_to_the_confirmed_commit(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, C2, C3])
    _add_content_at(http, COMMIT, "train.py", None)
    _add_content_at(http, C2, "train.py", b"v2\n")
    _add_content_at(http, C3, "train.py", None)            # latest moved but does not serve our file
    _add_upload(http, "train.py", visible_at=None)
    run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "v2\n"))
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == C2 and result["commit_id"] == C2


def test_run_domino_job_refuses_to_start_without_an_unconfirmed_upload(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT])                    # never moves
    _add_content_at(http, COMMIT, "train.py", None)
    _add_upload(http, "train.py", visible_at=None)
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "v2\n"))
    assert result["success"] and result["commitId"] is None and "note" in result
    posted = _job_post(http)
    with pytest.raises(server.DominoError) as err:
        run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert "train.py" in str(err.value) and "commit_id" in str(err.value) and posted == []


def test_run_domino_job_without_recent_uploads_takes_the_head(server, laptop, http, run):
    _add_project_lookup(http)
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t"))
    assert "commitId" not in posted[0] and result["commit_id"] is None
    assert not any(p.endswith("/commits/latest") for _, p, _ in http.calls)


def test_run_domino_job_explicit_commit_id(server, laptop, http, run):
    _add_project_lookup(http)
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", commit_id=C2))
    assert posted[0]["commitId"] == C2 and result["commit_id"] == C2
    with pytest.raises(server.DominoError):
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", commit_id="not a hash"))


def test_run_domino_job_commit_id_on_git_based_project_uses_main_repo_git_ref(server, laptop, http, run):
    _add_project_lookup(http, [{"id": PID, "name": PROJECT, "ownerUsername": OWNER, "mainRepository": GIT_REPO}])
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", commit_id=C2))
    assert "commitId" not in posted[0] and posted[0]["mainRepoGitRef"] == {"refType": "commitId", "value": C2}
    assert result["commit_id"] == C2
    with pytest.raises(server.DominoError):
        run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", commit_id=C2, git_branch="main"))


def test_run_domino_job_wait_after_upload_pins_then_returns_results(server, laptop, http, run, clock):
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_commit_sequence(http, [COMMIT, C2])
    _add_content_at(http, COMMIT, "x.py", None)
    _add_content_at(http, C2, "x.py", b"print(42)\n")
    _add_upload(http, "x.py", visible_at=None)
    run(server.upload_file_to_domino_project(OWNER, PROJECT, "x.py", "print(42)\n"))
    posted = _job_post(http)
    _job_status_sequence(http, "j1", ["Queued", "Succeeded"])
    http.add("GET", "/api/jobs/beta/jobs/j1/logs", FakeResponse(200, {"logs": {"logContent": [{"log": "42"}], "isComplete": True}, "metadata": {}}))
    result = run(server.run_domino_job(OWNER, PROJECT, "python x.py", "t", wait_seconds=60))
    assert posted[0]["commitId"] == C2 and result["commit_id"] == C2
    assert result["status"] == "Succeeded" and result["results"] == "42"


# ---------------------------------------------------------------------------------------------
# Release-review regressions: pinning survives reads; writes are serialized; the wait cap caps
# ---------------------------------------------------------------------------------------------

def _upload_confirmed(server, http, run, path="train.py", content="print(42)\n"):
    _add_project_lookup(http)
    _add_file(http, path, None)
    _add_upload(http, path)
    result = run(server.upload_file_to_domino_project(OWNER, PROJECT, path, content))
    assert result["commitId"] == COMMIT
    return result


def test_download_after_upload_keeps_the_commit_pin(server, laptop, http, run):
    _upload_confirmed(server, http, run)
    run(server.download_file_from_domino_project(OWNER, PROJECT, "train.py"))
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == COMMIT and result["commit_id"] == COMMIT


def test_identical_smart_sync_after_upload_keeps_the_commit_pin(server, laptop, http, run):
    _upload_confirmed(server, http, run)
    assert run(server.smart_sync_file(OWNER, PROJECT, "train.py", "print(42)\n"))["action"] == "no_change"
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == COMMIT and result["commit_id"] == COMMIT


def test_conflict_baseline_is_separate_from_write_tracking(server, laptop, http, run):
    """A download sets the conflict baseline to what it saw without forgetting the own write."""
    _upload_confirmed(server, http, run)
    _add_file(http, "train.py", b"someone else\n", commit=C2)
    run(server.download_file_from_domino_project(OWNER, PROJECT, "train.py"))
    assert server._file_version_cache[(OWNER, PROJECT, "train.py")]["key"] == hashlib.sha1(b"someone else\n").hexdigest()
    assert [p for p, _ in server._recent_writes(OWNER, PROJECT)] == ["train.py"]


def test_a_newer_foreign_version_at_the_latest_commit_is_not_treated_as_lag(server, laptop, http, run):
    _upload_confirmed(server, http, run)
    _add_commit_sequence(http, [C3])
    _add_content_at(http, C3, "train.py", b"someone else\n")   # newer than ours, not the pre-write content
    posted = _job_post(http)
    result = run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t"))
    assert posted[0]["commitId"] == C3 and result["commit_id"] == C3


def test_concurrent_creates_of_the_same_path_are_serialized(server, laptop, http, run, monkeypatch):
    """Two threads reach the remote-state read together; only one PUT may happen without overwrite."""
    import threading
    barrier = threading.Barrier(2, timeout=1)
    uploaded = []
    state = {"exists": False, "commit_id": COMMIT, "raw": None, "content": None, "key": None, "size": 0}

    def fake_remote_state(user_name, project_name, path, info=None):
        # Snapshot first, then rendezvous: without serialization both threads snapshot "absent"
        # and both write; with it the second thread cannot read until the first has written.
        snapshot = dict(state)
        if uploaded:
            data = uploaded[-1]
            snapshot.update({"exists": True, "raw": data, "content": data.decode(), "key": server._file_key(data), "size": len(data)})
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return snapshot

    def fake_upload(user_name, project_name, path, data):
        uploaded.append(data)
        return {"success": True, "path": path, "size": len(data), "key": server._file_key(data), "lastModified": 1}

    monkeypatch.setattr(server, "_require_dfs_project", lambda u, p: {"id": PID, "git_based": False})
    monkeypatch.setattr(server, "_remote_state", fake_remote_state)
    monkeypatch.setattr(server, "_upload", fake_upload)
    monkeypatch.setattr(server, "_confirm_upload", lambda *a, **k: {"commitId": COMMIT})
    results = {}

    def worker(data):
        try:
            results[data] = server._upload_file(OWNER, PROJECT, "train.py", data, False)
        except server.DominoError as e:
            results[data] = e
    threads = [threading.Thread(target=worker, args=(d,)) for d in (b"A", b"B")]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=10)
    assert len(uploaded) == 1
    outcomes = sorted(type(v).__name__ for v in results.values())
    assert outcomes == ["DominoError", "dict"]
    err = next(v for v in results.values() if isinstance(v, server.DominoError))
    assert "already exists" in str(err)


def test_run_domino_job_waits_for_an_in_flight_upload_before_choosing_the_commit(server, laptop, http, run, monkeypatch):
    import threading
    in_upload = threading.Event()
    release = threading.Event()
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_file(http, "train.py", None)
    _add_upload(http, "train.py")
    real_upload = server._upload

    def slow_upload(user_name, project_name, path, data):
        in_upload.set()
        assert release.wait(timeout=10)
        return real_upload(user_name, project_name, path, data)
    monkeypatch.setattr(server, "_upload", slow_upload)
    posted = _job_post(http)
    order = []
    t_up = threading.Thread(target=lambda: order.append(("upload", run(server.upload_file_to_domino_project(OWNER, PROJECT, "train.py", "x\n")))))
    t_up.start()
    assert in_upload.wait(timeout=10)
    t_job = threading.Thread(target=lambda: order.append(("job", run(server.run_domino_job(OWNER, PROJECT, "python train.py", "t")))))
    t_job.start()
    t_job.join(timeout=0.5)
    assert t_job.is_alive() and posted == []          # the Job waits for the upload instead of taking the head
    release.set()
    t_up.join(timeout=10)
    t_job.join(timeout=10)
    assert {name for name, _ in order} == {"upload", "job"}
    methods = [m for m, _, _ in http.calls]
    assert methods.index("PUT") < methods.index("POST")          # the upload landed before the Job was submitted
    job_result = next(r for name, r in order if name == "job")
    assert posted[0]["commitId"] == COMMIT and job_result["commit_id"] == COMMIT


def test_wait_cap_bounds_the_whole_status_call(server, laptop, http, run, clock, monkeypatch):
    """Two slow status reads of 40 s each must not push a 50 s cap to 80 s."""
    monkeypatch.setattr(server, "_CLIENT_NAME", "codex")
    reads = []

    def slow_job(kw):
        allowed = kw["timeout"][1]
        reads.append(allowed)
        took = min(40.0, allowed)
        clock.now += took
        if took < 40.0:
            raise server.requests.exceptions.ReadTimeout("read timed out")
        return FakeResponse(200, {"job": {"id": "job1", "status": {"executionStatus": "Running", "isCompleted": False}}})
    http.add("GET", "/api/jobs/beta/jobs/job1", slow_job)
    t0 = clock.now
    result = run(server.check_domino_job_run_status("job1", wait_seconds=300))
    assert clock.now - t0 <= server._WAIT_CAP_CODEX
    assert result["status"] == "Running" and result["is_completed"] is False
    assert result["waited_seconds"] <= server._WAIT_CAP_CODEX and "call" in result["message"].lower()
    assert reads[0] == 50.0 and all(r <= 50.0 for r in reads)


def test_run_domino_job_returns_the_job_id_when_little_time_is_left(server, laptop, http, run, clock, monkeypatch):
    monkeypatch.setattr(server, "_CLIENT_NAME", "codex")
    _add_project_lookup(http)
    _add_listing(http, [])
    _add_upload(http, "a.py", visible_at=None)
    _add_read_sequence(http, "a.py", [None])            # the upload never becomes visible: 45 s of confirmation
    run(server.upload_file_to_domino_project(OWNER, PROJECT, "a.py", "x\n"))
    # make the pending write visible for the job's own wait so that submission happens near the cap
    _add_read_sequence(http, "a.py", [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, b"x\n"])
    posted = _job_post(http)
    _job_status_sequence(http, "j1", ["Queued"])
    t0 = clock.now
    result = run(server.run_domino_job(OWNER, PROJECT, "python a.py", "t", wait_seconds=300))
    assert posted and result["job_id"] == "j1" and result["is_completed"] is not True
    assert clock.now - t0 <= server._WAIT_CAP_CODEX + 1
    assert "check_domino_job_run_status" in result["message"] and "results" not in result
