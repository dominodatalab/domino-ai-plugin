---
type: regex
target: { source: file, path: Cargo.toml }
match: contains
pattern: 'proa_framework_axum\s*=\s*\{[^}\n]*git\s*=\s*"https://github\.com/Proa-Labs/proa"[^}\n]*rev\s*=\s*"[0-9a-f]{7,40}"'
---
