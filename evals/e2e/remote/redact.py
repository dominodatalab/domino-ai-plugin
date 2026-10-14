"""Redaction filter used inside the Workspace: stdin -> stdout, line by line. The secret comes from E2E_REDACT."""
import os
import re
import sys

secret = os.environ.pop("E2E_REDACT", "")
pats = [(re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_ANTHROPIC_TOKEN]"),
        (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[REDACTED_JWT]")]
for line in sys.stdin:
    if secret and secret in line:
        line = line.replace(secret, "[REDACTED_SECRET]")
    for p, r in pats:
        line = p.sub(r, line)
    sys.stdout.write(line)
    sys.stdout.flush()
