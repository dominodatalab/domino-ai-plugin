---
type: llm
focus: { source: file, path: flow.py }
---

The file must turn the existing task's cleaned CSV into a Flow Artifact and export that artifact to the NetApp Volume from inside the flow.
PASS if ALL hold:
1. A `DATA` `Artifact` is defined (`Artifact(name=..., type=DATA)` from `flytekitplugins.domino.artifact`) and the clean task's `cleaned` output type is that artifact's `.File(name=...)` (a file name ending in `.csv`), so the CSV is tracked as a Flow Artifact.
2. `run_launch_export_artifacts_task(...)` is called inside the `@workflow` function (not merely defined, imported or mentioned in a comment), with a `spec_list` that contains an `ExportArtifactToNetAppVolumesSpec` whose `artifact` is that same `Artifact` object (not the task result, not a string, not a `FlyteFile`).
3. The original `Clean data` task (`DominoJobTask` + `DominoJobConfig`, command `python stages/clean.py`) is still present and still called, and the workflow still returns the cleaned file.
FAIL if the artifact is never attached to the task output, if the export is described in a comment or in prose only, if the task is replaced by a Flyte `@task`, if the export is pointed at a Dataset instead of the NetApp Volume, or if the file tells the user to export from the UI instead of adding the export to the flow.
