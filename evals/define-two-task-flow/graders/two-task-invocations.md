---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*\b(DominoJobTask|run_domino_job_task)\([\s\S]*?^(?!\s*#)[^\n]*\b(DominoJobTask|run_domino_job_task)\('
---
