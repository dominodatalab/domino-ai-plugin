---
type: llm
focus: { source: file, path: flow.py }
---

The file must define a Domino Flow with two tasks that run in sequence with a real data dependency.
PASS if ALL hold:
1. There are two Domino tasks, built with `DominoJobTask` + `DominoJobConfig` or with `run_domino_job_task`, and both are actually called inside the `@workflow` function (not only defined, not only mentioned in comments).
2. The first task's command runs `stages/prep.py` and declares an output (for example `prepared_path`); the second task's command runs `stages/train.py` and declares an input with a matching name.
3. The second task is called with the first task's result as that input. When the first task declares exactly one output, the result is passed directly (`train_task(prepared_path=prep_result)`). Only when the first task declares more than one output may the value be selected by attribute access (`prep_result.prepared_path`) or tuple unpacking.
FAIL if the workflow body makes no task calls, if the second task's input is a literal or a workflow parameter instead of the first task's result, if a task result is indexed with a string (`prep_result["prepared_path"]`, which fails to compile for multi-output tasks and binds the wrong thing for single-output tasks), if attribute access or unpacking is applied to a single-output result, or if Flyte `@task` functions replace the Domino tasks.
