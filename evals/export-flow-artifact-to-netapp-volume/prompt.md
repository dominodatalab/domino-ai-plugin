---
description: "Flows: export a DATA Flow Artifact to a NetApp Volume subdirectory with run_launch_export_artifacts_task and ExportArtifactToNetAppVolumesSpec, overwriting existing files."
tags: [trigger, domino-flows, flows, netapp-volumes]
max_turns: 15
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

My Domino Flow in flow.py has a task that writes a cleaned CSV. After each run I want that file copied
automatically into the `cleaned/` folder of our NetApp volume (id 5d1204c2-24c8-47df-a47f-69185efa602b),
replacing the previous copy. Update flow.py so the flow does this itself; I don't want to export by hand
from the UI. Keep the rest of the flow as it is.
