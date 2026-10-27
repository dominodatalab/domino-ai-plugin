---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*\brun_launch_export_artifacts_task\('
---
