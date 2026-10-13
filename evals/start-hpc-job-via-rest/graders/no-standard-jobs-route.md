---
type: regex
target: last_message
match: not_contains
pattern: '["\x27][^"\x27\n]*/api/jobs/v1/jobs[^"\x27\n]*["\x27]|[\x27"]clusterType[\x27"]\s*:\s*[\x27"]slurm[\x27"]'
---
