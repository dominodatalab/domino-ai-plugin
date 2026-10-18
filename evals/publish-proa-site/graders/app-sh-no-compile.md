---
type: regex
target: { source: file, path: app.sh }
match: not_contains
pattern: '(^|\n)[^#\n]*\b(cargo|proa)\s+(\+\S+\s+)?(build|run|install|dev)\b'
---
