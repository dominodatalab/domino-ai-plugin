---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*\b(DominoJobConfig|run_domino_job_task)\('
---
