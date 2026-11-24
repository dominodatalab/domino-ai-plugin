---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*target_relative_path\s*=\s*[\x27"]/?cleaned/?[\x27"]'
---
