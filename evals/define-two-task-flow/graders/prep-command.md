---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*[Cc]ommand\s*=\s*f?[\x27"][^\x27"\n]*prep\.py'
---
