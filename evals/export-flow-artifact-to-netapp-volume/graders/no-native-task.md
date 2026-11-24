---
type: regex
target: { source: file, path: flow.py }
match: not_contains
flags: m
pattern: '^\s*@task\b'
---
