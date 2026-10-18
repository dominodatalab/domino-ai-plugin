"""Minimal Domino REST client for the harness. Tokens stay in memory; nothing is printed or written."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class DominoError(RuntimeError):
    pass


class Domino:
    def __init__(self, cfg: dict):
        self.host = cfg["host"].rstrip("/")
        self.auth = cfg["auth"]
        self._tok = None
        self._exp = 0.0

    # -- auth -------------------------------------------------------------------------------------
    def _token(self) -> str:
        if self.auth["mode"] == "pat":
            t = os.environ.get(self.auth.get("pat_env", "DOMINO_TOKEN"), "")
            if not t:
                raise DominoError(f"set ${self.auth.get('pat_env', 'DOMINO_TOKEN')} to a Personal Access Token")
            return t
        if self._tok and time.time() < self._exp - 30:
            return self._tok
        with open(os.path.expanduser(self.auth["token_file"])) as f:
            rt = f.read().strip()
        realm = self.auth.get("realm", "DominoRealm")
        data = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": self.auth.get("client_id", "cli-client"),
                                       "refresh_token": rt}).encode()
        del rt
        req = urllib.request.Request(f"{self.host}/auth/realms/{realm}/protocol/openid-connect/token", data=data)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        self._tok = body.get("access_token")
        if not self._tok:
            raise DominoError("token exchange failed")
        self._exp = time.time() + float(body.get("expires_in", 120))
        return self._tok

    # -- requests ---------------------------------------------------------------------------------
    def request(self, method: str, path: str, body=None, params: dict | None = None, ok=(200, 201, 202, 204),
                raw: bool = False, timeout: int = 60, url: str | None = None, headers: dict | None = None):
        u = url or (self.host + path)
        if params:
            u += ("&" if "?" in u else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        data = None
        h = {"Accept": "application/json", "Authorization": f"Bearer {self._token()}"}
        if headers:
            h.update(headers)
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(u, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, txt = r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            code, txt = e.code, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            code, txt = 0, str(e)
        if ok is not None and code not in ok:
            raise DominoError(f"{method} {path} -> HTTP {code}: {txt[:400]}")
        if raw:
            return code, txt
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            return txt

    def fetch(self, url: str, accept: str = "*/*", timeout: int = 60):
        """GET a full URL with the bearer token, following redirects: (status, final URL, body)."""
        req = urllib.request.Request(url, headers={"Accept": accept, "Authorization": f"Bearer {self._token()}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.geturl() or url, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            return 0, url, str(e)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body if body is not None else {}, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    # -- convenience ------------------------------------------------------------------------------
    def whoami(self) -> dict:
        return self.get("/v4/users/self")

    def jobs(self, project_id: str, limit: int = 50) -> list[dict]:
        r = self.get("/api/jobs/beta/jobs", params={"projectId": project_id, "limit": limit, "sortBy": "submissionTime",
                                                     "ascending": "false", "showArchived": "true"})
        return r.get("jobs", []) if isinstance(r, dict) else []

    def job(self, job_id: str) -> dict:
        r = self.get(f"/api/jobs/beta/jobs/{job_id}")
        return r.get("job", r) if isinstance(r, dict) else {}

    def job_stdout(self, job_id: str) -> str:
        r = self.get(f"/api/jobs/beta/jobs/{job_id}/logs", params={"logType": "stdout", "limit": 10000}, ok=None)
        if isinstance(r, dict):
            if isinstance(r.get("logs"), dict):
                r = r["logs"]
            lines = r.get("logContent") or r.get("logs") or []
            if isinstance(lines, list):
                return "\n".join((x.get("log") if isinstance(x, dict) else str(x)) or "" for x in lines)
            return str(lines)
        return str(r or "")

    def datasets(self, project_id: str) -> list[dict]:
        r = self.get("/api/datasetrw/v1/datasets", params={"projectId": project_id, "limit": 100})
        out = r.get("datasets", []) if isinstance(r, dict) else []
        return [d.get("dataset", d) for d in out]

    def snapshots(self, dataset_id: str) -> list[dict]:
        r = self.get(f"/api/datasetrw/v1/datasets/{dataset_id}/snapshots", params={"limit": 100})
        out = r.get("snapshots", []) if isinstance(r, dict) else []
        return [s.get("snapshot", s) for s in out]


def ts_ms(v) -> float:
    """Domino timestamps come as epoch ms ints or ISO strings; return epoch seconds (0 if unknown)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return v / 1000.0 if v > 1e11 else float(v)
    s = str(v)
    if s.isdigit():
        return ts_ms(int(s))
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
