# Launcher examples

Scripts and result patterns for Domino Launchers. The launcher itself (name, command, controls, hardware tier, environment, notification list) is configured in the wizard under **Deployments > Launchers** or through the web UI routes in [Manage launchers from code](#manage-launchers-from-code); see [SKILL.md](./SKILL.md).

## Parse launcher arguments

Values arrive as positional command-line arguments in the order of the `${name}` placeholders in the command. Each value is single-quoted by Domino; file uploads arrive as a path; multi-select values arrive as one comma-separated string.

### Python (positional)

Command: `score.py ${input_file} ${columns} ${notify}`

```python
import sys

input_path = sys.argv[1]                 # Upload files -> path
columns = sys.argv[2].split(",")         # Multi-select -> "a,b,c"
notify = sys.argv[3].strip().lower() in ("true", "yes", "1", "on")   # Checkbox -> yes/no value; print(sys.argv) once to see the literal

with open(input_path) as f:
    print(f.readline())
```

### Python (named arguments with argparse)

Command: `generate_report.py --start ${start_date} --end ${end_date} --region ${region}`

```python
import argparse
from datetime import date

parser = argparse.ArgumentParser()
parser.add_argument("--start", required=True)
parser.add_argument("--end", required=True)
parser.add_argument("--region", default="all")
args = parser.parse_args()

start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
if end < start:
    raise SystemExit("End date must be on or after start date")   # non-zero exit = failed run
```

### R

Command: `launcher.R ${A} ${B}`

```r
args <- commandArgs(trailingOnly = TRUE)
a <- as.integer(args[1])
b <- as.integer(args[2])
if (is.na(a) || is.na(b)) {
  stop("A and B must be integers")
} else {
  print(paste("The sum of", a, "and", b, "is:", a + b))
}
```

## Where to write results

| Project type | Results directory | `email.html` location |
|---|---|---|
| DFS (Domino File System) | anywhere under the Project root, `/mnt` | `/mnt/email.html` |
| Git-based | `/mnt/artifacts/results/` | `/mnt/artifacts/email.html` |

Pick the directory from the environment so one script works in both:

```python
import os
from pathlib import Path

if os.environ.get("DOMINO_IS_GIT_BASED", "false").lower() == "true":
    results = Path("/mnt/artifacts/results")
    email_html = Path("/mnt/artifacts/email.html")
else:
    results = Path(os.environ["DOMINO_WORKING_DIR"]) / "results"
    email_html = Path(os.environ["DOMINO_WORKING_DIR"]) / "email.html"
results.mkdir(parents=True, exist_ok=True)
```

Multiple formats:

```python
df.to_csv(results / "data.csv", index=False)
df.to_excel(results / "data.xlsx", index=False)
fig.savefig(results / "chart.png")
```

## Custom email body

```python
html = f"""
<head><title>Report {args.start} to {args.end}</title></head>
<body>
  <h1>Report {args.start} to {args.end}</h1>
  <p>Rows: {len(df)}</p>
  <img src="results/chart.png">
  {df.head(20).to_html()}
</body>
"""
email_html.write_text(html)
```

Rules: inline CSS only, tables for layout, image paths relative to the Project root, `<head><title>` becomes the subject, and if a `.dominoresults` file exists it must list `email.html`.

## Notebook reports

Run a parameterized notebook with papermill and keep the executed copy as a result:

```python
import papermill as pm

pm.execute_notebook(
    "report_template.ipynb",
    str(results / "report.ipynb"),
    parameters={"start_date": args.start, "end_date": args.end},
)
```

Or point the launcher command at the notebook itself (`report.ipynb`): Domino executes it and saves the result. For HTML or PDF output wrap `jupyter nbconvert --to html --execute report.ipynb --output-dir <results>` in a shell script and use that as the command.

## Complete example: scoring launcher

Launcher wizard settings:

| Field | Value |
|---|---|
| Name | Score customer data |
| Command | `score_data.py ${input_file} ${output_format}` |
| Control 1 | **Upload files**, label "Customer data (CSV)" |
| Control 2 | **Select**, label "Output format", options `csv`, `xlsx` |
| Notification list | the consumers' addresses |

`score_data.py`:

```python
import os
import sys
from pathlib import Path

import joblib
import pandas as pd

input_path, output_format = sys.argv[1], sys.argv[2]

git_based = os.environ.get("DOMINO_IS_GIT_BASED", "false").lower() == "true"
results = Path("/mnt/artifacts/results") if git_based else Path(os.environ["DOMINO_WORKING_DIR"]) / "results"
results.mkdir(parents=True, exist_ok=True)

model = joblib.load(("/mnt/artifacts" if git_based else os.environ["DOMINO_WORKING_DIR"]) + "/model.joblib")
df = pd.read_csv(input_path)
df["prediction"] = model.predict(df)

if output_format == "xlsx":
    df.to_excel(results / "predictions.xlsx", index=False)
else:
    df.to_csv(results / "predictions.csv", index=False)
print(f"Scored {len(df)} rows")
```

## Find a launcher run and its files from code

Each run is a Job. Inside a Domino execution:

```python
import os
import requests
from urllib.parse import quote

base = os.environ["DOMINO_API_PROXY"]          # no Authorization header needed
project_id = os.environ["DOMINO_PROJECT_ID"]

jobs = requests.get(f"{base}/api/jobs/beta/jobs",
                    params={"projectId": project_id, "limit": 50, "statusFilter": "completed"}).json()["jobs"]
runs = [j for j in jobs if j.get("runLauncherId")]
job = runs[0]
commit = job["commitDetails"]["outputCommitId"]          # files as they were after the run
path = quote("results/predictions.csv", safe="")
content = requests.get(f"{base}/api/projects/v1/projects/{project_id}/files/{commit}/{path}/content").content
```

Outside Domino: [domino-api-intro](../domino-api-intro/SKILL.md#authentication).

## Manage launchers from code

These are the Launchers page's own routes (non-public route; may change in a future Domino version; [route types](../domino-api-intro/SKILL.md#route-types)). They are scoped by the Project's owner username and name, not by id, and take a bearer token on `$DOMINO_API_HOST` (in a run, the access-token endpoint; outside, a Personal Access Token; [domino-api-intro](../domino-api-intro/SKILL.md)).

The launcher object, as sent to create and update:

```json
{
  "id": null,
  "projectId": "<project id>",
  "name": "Score customer data",
  "description": "Upload a CSV and get predictions back",
  "command": "score_data.py ${input_file} ${output_format}",
  "valuePassType": "CommandLineSubstitutionPass",
  "hardwareTierId": "small-k8s",
  "parameters": [
    {"name": "input_file", "parameterType": "File", "defaultValue": "", "allowedValues": [], "description": "Customer data (CSV)", "shouldQuoteValue": true},
    {"name": "output_format", "parameterType": "Select", "defaultValue": "csv", "allowedValues": [{"value": "csv"}, {"value": "xlsx"}], "description": "Output format", "shouldQuoteValue": true}
  ]
}
```

`parameterType` is one of `Text`, `Select`, `MultiSelect`, `Date`, `Checkbox`, `File`; `allowedValues` entries are `{"value": "..."}` objects; every parameter field is required (a missing one is an HTTP 500 with a `JsResultException` naming it). The stored object also carries `environmentId`, `capacityType`, `externalVolumeMountIds` and `netAppVolumeIds` (null until set). `hardwareTierId` may be `""` for the Project default.

```python
import os, requests

base = os.environ["DOMINO_API_HOST"]
headers = {"Authorization": f"Bearer {token}"}
u = f"{base}/u/{owner}/{project_name}/runLaunchers"

created = requests.post(u, json=launcher, headers=headers).json()      # a draft: "id" is set, "command" is the default
launcher_id = created["id"]
created["command"] = launcher["command"]
requests.put(f"{u}/{launcher_id}", json=created, headers=headers).raise_for_status()   # stores the command; the launcher is now listed
current = requests.get(f"{u}/{launcher_id}", headers=headers).json()                  # 404 once deleted; 400 for a malformed id
requests.delete(f"{u}/{launcher_id}", json={}, headers=headers).raise_for_status()    # returns the deleted launcher
```

To edit, `GET` the object, change fields, `PUT` the whole object back.

List: the Launchers page embeds the stored launchers in its mount props. A launcher created but never `PUT` is a draft and does not appear, so `PUT` it once or keep the ids you create.

```python
import html, json, re

page = requests.get(f"{base}/u/{owner}/{project_name}/endpoints/launchers",
                    headers={**headers, "Accept": "text/html"}).text
props_js = re.search(r"renderComponentByName\(\s*'LaunchersPage',\s*\"(.*?)\",\s*document", page, re.S).group(1)
props = json.loads(html.unescape(props_js).replace('\\"', '"').replace("\\/", "/"))
launchers = props["launchers"]            # full launcher objects; props also carry canCreateLaunchers and routes.editLauncher
```

Start a run (Internal API; non-public route, may change in a future Domino version): one `postParameters` entry per `${name}` in the command, values as a list (several entries for a Multi-select); a File parameter goes in `uploadedFiles` as `{"parameterName", "fileName", "tempFileBase64Encoding"}`. The response is the Job id; the Job's `runCommand` shows the substituted values and `runLauncherId` points back here.

```python
job_id = requests.post(f"{base}/v4/projects/{project_id}/launcherJob/{launcher_id}", headers=headers, json={
    "project": project_id,
    "postParameters": [{"key": "output_format", "value": ["csv"]}],
    "uploadedFiles": [],
    "notifyOnCompleteEmailAddresses": [],
    "jobTitle": "nightly scoring",
}).json()
```
