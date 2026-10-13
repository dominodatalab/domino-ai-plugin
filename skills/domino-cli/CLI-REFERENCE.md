# Domino CLI command reference

Source: https://docs.domino.ai/cloud/reference/cli/cli-reference and
https://docs.domino.ai/cloud/reference/cli/download-files-with-the-cli (6.3 pages identical).
`domino help` prints the same list; `domino help run` prints one command.

The file and run commands act on the project folder you run them in; the CLI records the link in
`.domino/config.json`. `create` and `get` make that folder, `init` and `restore` link the current
one, and the Dataset commands name their target as `owner/project/dataset`.

## Run

```text
run [--direct] [--wait] [--no-sync] [--tier <name>] [--local] [--title <text>] <file> [args...]
```

Uploads every changed file in the project folder, then executes `<file>` with the arguments on
Domino as a Job.

| Flag | Effect |
|---|---|
| `--wait` | block until the Job finishes |
| `--direct` | run the quoted string as a shell command instead of a file |
| `--no-sync` | run the server's current version of the code; upload nothing |
| `--tier "<name>"` | hardware tier by display name |
| `--local` | commit a snapshot, run the command on this machine, commit the produced files back as results |
| `--title "<text>"` | title shown in the Jobs dashboard |

```bash
domino run calculateStats.R
domino run runModel.m model1 .05
domino run --wait runModel.m model1 .05
domino run --direct "pip freeze | grep pandas"
domino run --tier "Large" calculateStats.R
domino run --local "python main.py"
```

If `run` fails with "blob file not found", `domino sync` first.

## Projects

| Command | Effect |
|---|---|
| `create [projectName]` | new folder plus new project; prompts for the name if omitted; `--owner <org>` for an organisation |
| `init [projectName]` | new project rooted at the current folder; uploads nothing until `upload` or `run`; `--owner <org>` |
| `get [username/]projectName` | first local copy of an existing project (yours, or a collaborator's with the username) |
| `restore` | reconnect the current folder to its project; reads `.domino/config.json` or prompts for the project name (after a `git clone`, after deleting `.domino`) |

```bash
domino create --owner myOrg myProject
domino init
domino get otherUser/someProject
domino restore
```

## Files

| Command | Effect |
|---|---|
| `sync` | download then upload |
| `download` | pull the latest server files; conflicts leave both versions side by side |
| `upload [-m "message"]` | push local files without starting a run; the message shows on the **Code** tab |
| `download-results [--filter '<glob>'] <run id or run number>` | pull a run's output files into `results/run-<id or number>` |

```bash
domino sync
domino download
domino upload -m "upload data files"
domino download-results --filter 'myfolder/*' 548fda01e4b0a8f06b7e8d99
domino download-results --filter 'myfolder/*' 1
```

Notes: an `upload` of more than 1,000 files at once can hit a timeout
(split it); `sync` failing with "too many open files" is solved by an empty `.noLock` file at the
project root; `.dominoignore` lists files and folders (with `*` wildcards) that sync skips.

## Datasets

```text
upload-dataset [--fileUploadSetting Ignore|Overwrite|Rename] [--targetRelativePath <path>] <project-owner>/<project-name>/<dataset-name> <local folder>
create-snapshot <project-owner>/<project-name>/<dataset-name>
create-dataset-from-snapshot <project-owner>/<project-name>/<dataset-name> <snapshot-number> <new-dataset-name>
```

- `upload-dataset` uploads every file in the folder to an existing Dataset and **overwrites**
  matches unless `--fileUploadSetting` says `Ignore` (keep the existing file) or `Rename` (new
  file gets `_1`). `--targetRelativePath` chooses a subfolder relative to the Dataset root. Both
  option names and values are case-sensitive.
- `create-snapshot` returns before the copy finishes; do not modify the Dataset until the
  snapshot is visible and populated.
- `create-dataset-from-snapshot` takes the snapshot **number**; the new Dataset can take time to
  populate.
- Admin quotas apply: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/datasets/manage-large-data#dataset-quotas-and-limits

```bash
domino upload-dataset --fileUploadSetting Overwrite --targetRelativePath Experiments/Run1/Analysis jsmith/global-predictions/global-data /Users/myUser/data
```

Parallel upload tuning (environment variables; `export` on Linux and macOS, `set` in PowerShell):

| Variable | Default | Meaning |
|---|---|---|
| `DOMINO_UPLOAD_CHUNK_BYTES` | `3145728` (3 MB) | chunk size; larger chunks cut per-chunk setup on fast networks |
| `DOMINO_UPLOAD_THREADS` | `8` | parallel upload threads; scale with cores |

## Help and version

```bash
domino help
domino help run
domino --version
```
