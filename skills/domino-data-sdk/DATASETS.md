# Dataset files with DatasetClient

`DatasetClient` reads files from a Domino Dataset through the Data Source proxy, with the
caller's permissions. It is read-only: list, fetch, download and signed URLs. To write, use the
Dataset's mount path inside an execution, the UI, `domino upload-dataset`
([domino-cli](../domino-cli/SKILL.md)), or the `/api/datasetrw` routes (domino-datasets skill).

Docs: https://docs.domino.ai/cloud/reference/api/data_api/datasource_usecases/access-datasets-via-proxy.
Source: `domino_data/datasets.py`.

## When to use it instead of the mount

- Code that runs where the Dataset is not mounted: an App serving many users, an endpoint, or
  an execution in another Project.
- Reading a specific snapshot by ID without relying on mount paths, including a snapshot
  taken in the current execution, which is not mounted until a later execution starts.
- Otherwise read the mount (`/domino/datasets/local/<name>` or `/mnt/data/<name>`); it is
  faster and simpler.

## Client

```python
from domino_data.datasets import DatasetClient, DatasetConfig

client = DatasetClient()     # kwargs api_key, token_file, token_url, token; defaults from env
dataset = client.get_dataset("dataset-training-data-6503324fa1eb367359734bfd")
```

`get_dataset` takes the Dataset's unique identifier, which the UI prints in the code snippet
on the Dataset's page (**Data > Datasets** > the Dataset > **Code snippet**); it is not simply
the display name. From code, `GET /v4/datasetrw/dataset/{datasetId}/connection-snippets`
(non-public route; may change in a future Domino version, see [route types](../domino-api-intro/SKILL.md#route-types)) returns the same
snippets as `[{"language": "Python", "snippet": "..."}, ...]`, with the identifier of the form
`dataset-<name>-<datasetId>` inside. Authentication follows the same order as
`DataSourceClient` (see SKILL.md).

## Reading files

```python
files = dataset.list_files(prefix="images/train/", page_size=500)   # list of _File
for f in files:
    print(f.name)

content = dataset.get("config.json")                     # bytes
dataset.download_file("model.pkl", "/tmp/model.pkl")     # streamed to disk
dataset.download("huge.parquet", "/tmp/huge.parquet", max_workers=16)   # ranged, parallel

import io
buf = io.BytesIO()
dataset.download_fileobj("data.json", buf)               # any object with write(bytes)
buf.seek(0)

url = dataset.get_file_url("large_file.zip")             # signed, read-only URL
```

Per-file handles carry the same operations:

```python
f = dataset.File("path/to/file.csv")
f.get(); f.download_file("local.csv"); f.download("local.csv", max_workers=4)
with open("out.csv", "wb") as out:
    f.download_fileobj(out)
```

## Read a snapshot or a subfolder

`DatasetConfig` has two fields, `snapshot_id` and `subfolder`. Without an override the
read-write (live) snapshot is used.

```python
dataset.update(DatasetConfig(snapshot_id="649cb4dedeb75c31b6e7dafb"))
baseline = dataset.get("features.parquet")
dataset.reset_config()                                     # back to live data
```

Snapshot IDs come from `GET /api/datasetrw/v1/datasets/{datasetId}/snapshots` or the Dataset's
snapshot list in the UI.

## Patterns

Parquet without touching disk:

```python
import io
import pandas as pd

df = pd.read_parquet(io.BytesIO(dataset.get("data/features.parquet")))
```

Concatenate CSVs under a prefix:

```python
parts = [pd.read_csv(io.BytesIO(dataset.get(f.name)))
         for f in dataset.list_files(prefix="data/", page_size=1000) if f.name.endswith(".csv")]
df = pd.concat(parts, ignore_index=True)
```

App reading on behalf of the signed-in user (Domino passes the user's bearer token on each
request to the App):

```python
auth = request.headers.get("Authorization", "")
token = auth[7:].strip() if auth.startswith("Bearer ") else ""
if not token:
    abort(401)            # never DatasetClient(token=None): that falls back to the publisher's identity
dataset = DatasetClient(token=token).get_dataset("dataset-training-data-6503324fa1eb367359734bfd")
```

## Errors

`domino_data.datasets` defines `DominoError` and `UnauthenticatedError` but raises neither;
the errors come from the underlying `data_sources` client and from `httpx`:

```python
import httpx
from domino_data.data_sources import UnauthenticatedError

try:
    dataset = client.get_dataset("dataset-training-data-6503324fa1eb367359734bfd")
except Exception as e:
    print(f"unknown Dataset or no access: {e}")            # bare Exception from the library

try:
    files = dataset.list_files(prefix="data/")
    content = dataset.get("data/missing.txt")
except UnauthenticatedError:
    print("401 from the Data Source proxy for 60 seconds")
except httpx.HTTPStatusError as e:
    print(f"HTTP {e.response.status_code} fetching the file")   # 404 for a missing path
```

## Practices

1. Prefer the mount path when the Dataset is mounted; use the client for Apps, endpoints and
   cross-Project reads.
2. `max_workers` on `download` for files over a few hundred MB; `page_size` on `list_files`.
3. Pin `snapshot_id` in anything that must be reproducible.
4. Cache downloads under `/tmp` within an execution instead of fetching twice.
