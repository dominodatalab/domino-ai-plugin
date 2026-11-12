---
type: regex
target: { source: file, path: flow.py }
flags: m
pattern: '^(?!\s*#)[^\n]*file_collision_setting\s*=\s*FileCollisionSetting\.OVERWRITE\b'
---
