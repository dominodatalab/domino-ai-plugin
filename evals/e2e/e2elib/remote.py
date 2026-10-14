"""SSH into Domino Workspaces through Domino Connect (`dom connect`), with connection multiplexing."""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

DOMINO_SSH_CONFIG = Path.home() / ".domino" / "ssh" / "config"


class Remote:
    def __init__(self, ws_id: str, state_dir: Path):
        self.ws = ws_id
        self.state_dir = state_dir
        self.cm = state_dir / "cm"
        self.cm.mkdir(parents=True, exist_ok=True)

    def ssh_opts(self) -> list[str]:
        return ["-F", str(DOMINO_SSH_CONFIG), "-o", "ControlMaster=auto", "-o", f"ControlPath={self.cm}/%h-%p",
                "-o", "ControlPersist=120m", "-o", f"UserKnownHostsFile={self.state_dir / 'known_hosts'}",
                "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=60",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6"]

    def run(self, cmd: str, input: bytes | None = None, timeout: int = 300, check: bool = False) -> subprocess.CompletedProcess:
        p = subprocess.run(["ssh", *self.ssh_opts(), self.ws, cmd], input=input, capture_output=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"remote command failed ({p.returncode}): {cmd[:120]}\n{p.stderr.decode()[-800:]}")
        return p

    def sh(self, cmd: str, timeout: int = 300) -> tuple[int, str]:
        """Run a bash snippet (login-like env so PATH has ~/.local/bin); return (rc, stdout+stderr)."""
        wrapped = "bash -lc " + shlex.quote('export PATH="$HOME/.local/bin:$PATH"; ' + cmd)
        p = self.run(wrapped, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")

    def popen(self, cmd: str, stderr=subprocess.PIPE) -> subprocess.Popen:
        return subprocess.Popen(["ssh", *self.ssh_opts(), self.ws, cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr)

    def push_dir(self, local: Path, remote: str, excludes=(".git", "__pycache__", ".venv", "node_modules")) -> None:
        """Copy a local tree to the Workspace (rsync if the image has it, else tar over SSH)."""
        rc, _ = self.sh("command -v rsync >/dev/null")
        self.sh(f"rm -rf {shlex.quote(remote)} && mkdir -p {shlex.quote(remote)}")
        if rc == 0:
            ex = sum((["--exclude", e] for e in excludes), [])
            p = subprocess.run(["rsync", "-a", "--delete", *ex, "-e", "ssh " + " ".join(shlex.quote(o) for o in self.ssh_opts()),
                                f"{local}/", f"{self.ws}:{remote}/"], capture_output=True, timeout=600)
            if p.returncode == 0:
                return
        ex = sum((["--exclude", e] for e in excludes), [])
        tar = subprocess.Popen(["tar", "-C", str(local), *ex, "-czf", "-", "."], stdout=subprocess.PIPE,
                               env={**os.environ, "COPYFILE_DISABLE": "1"})
        p = subprocess.run(["ssh", *self.ssh_opts(), self.ws, f"tar -xzf - -C {shlex.quote(remote)}"], stdin=tar.stdout,
                           capture_output=True, timeout=600)
        tar.wait()
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode()[-500:])


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 100, preferred + 200)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port")


def start_dom_connect(dom: str, ws_id: str, user: str, port: int, host: str, log: Path) -> int:
    """Start `dom connect` in the background; returns its PID. It writes a Host entry to ~/.domino/ssh/config."""
    f = open(log, "ab")
    p = subprocess.Popen([dom, "connect", ws_id, "-l", user, "--port", str(port), "--domino-api-host", host],
                         stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid


def wait_ssh(r: Remote, timeout: int = 300) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            p = r.run("echo ok", timeout=90)
            if p.returncode == 0 and b"ok" in p.stdout:
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(5)
    return False


def remove_ssh_host(ws_id: str) -> bool:
    """Drop the `Host <ws_id>` block dom wrote to ~/.domino/ssh/config. Returns True if one was removed."""
    if not DOMINO_SSH_CONFIG.exists():
        return False
    lines = DOMINO_SSH_CONFIG.read_text().splitlines(keepends=True)
    out, skip, removed = [], False, False
    for ln in lines:
        if ln.strip().startswith("Host "):
            skip = ln.strip().split(None, 1)[1].strip() == ws_id
            removed |= skip
        if not skip:
            out.append(ln)
    if removed:
        DOMINO_SSH_CONFIG.write_text("".join(out))
    return removed
