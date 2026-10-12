# Data Sources with DataSourceClient

Docs: https://docs.domino.ai/cloud/reference/api/data_api/datasource_usecases (query, object
store, write to file, configuration override, custom authentication) and
https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/data-source-connectors/use-data-sources.
Source: `domino_data/data_sources.py` and `domino_data/configuration_gen.py` in
https://github.com/dominodatalab/domino-data.

## Client and Datasource objects

```python
from domino_data.data_sources import DataSourceClient

client = DataSourceClient()          # kwargs api_key, token_file, token_url, token; all default from env
ds = client.get_datasource("analytics-db")   # the name under Data > Data Sources; must be added to the Project
```

`get_datasource` returns a `TabularDatasource` or an `ObjectStoreDatasource` depending on the
connector. Attributes on either:

| Attribute | Meaning |
|---|---|
| `name`, `identifier` | Display name and ID |
| `datasource_type` | Connector type, for example `SnowflakeConfig`, `RedshiftConfig`, `S3Config`, `GenericS3Config`, `ADLSConfig`, `BigQueryConfig`, `DatabricksConfig`, `PostgreSQLConfig`, `MySQLConfig`, `SQLServerConfig`, `OracleConfig`, `GCSConfig`, `AzureBlobStorageConfig`, `DatasetConfig` |
| `auth_type` | How the Data Source authenticates, for example `Basic`, `AWSIAMRole`, `OAuth`, `NoAuth`, `GCPBasic`, `AzureBasic`, `PersonalToken`, `KeyPair` |
| `owner` | Owner's username |
| `config` | Connection settings as a dict (no secrets) |

## Tabular (SQL) Data Sources

```python
res = ds.query("""
    SELECT customer_id, revenue, region
    FROM sales
    WHERE sale_date >= '2026-01-01'
    LIMIT 10000
""")
df = res.to_pandas()              # pandas DataFrame
res.to_parquet("sales.parquet")   # path or file-like object; the whole result is written once
```

The result travels as Arrow over the Data Source proxy's Flight endpoint. Write CSV through
pandas (`res.to_pandas().to_csv(...)`) because CSV serialisation is lossy.

Nested columns are not queryable; flatten in SQL, for example
`SELECT account_id, t1 FROM sample.transactions CROSS JOIN UNNEST (transactions) AS t(t1, t2)`.

## Object-store Data Sources (S3, Generic S3, GCS, ADLS, Azure Blob)

```python
s3 = client.get_datasource("s3-datalake")

objects = s3.list_objects(prefix="raw/2026/", page_size=1000)   # list of _Object; obj.key
content = s3.get("raw/2026/config.json")                        # bytes
s3.download_file("raw/2026/events.parquet", "/tmp/events.parquet")
s3.download("raw/2026/big.parquet", "/tmp/big.parquet", max_workers=8)   # ranged, parallel
with open("/tmp/out.bin", "wb") as f:
    s3.download_fileobj("raw/2026/blob.bin", f)

s3.put("outputs/summary.json", b'{"rows": 1000}')
s3.upload_file("outputs/model.pkl", "/tmp/model.pkl")
with open("/tmp/results.csv", "rb") as f:
    s3.upload_fileobj("outputs/results.csv", f)

url = s3.get_key_url("raw/2026/events.parquet", is_read_write=False)   # signed URL
```

The same operations exist on an object handle: `obj = s3.Object("raw/2026/events.parquet")`
then `obj.get()`, `obj.download_file(path)`, `obj.download(path, max_workers=8)`,
`obj.download_fileobj(f)`, `obj.put(bytes)`, `obj.upload_file(path)`, `obj.upload_fileobj(f)`.

## Configuration override

Change connection settings or credentials for this session only; Domino's stored configuration
is untouched. Every connector has a `*Config` class in `domino_data.data_sources` (importable
by name); the docs page "Configuration override" lists all of them with their fields.

```python
from domino_data.data_sources import SnowflakeConfig, RedshiftConfig

sf = client.get_datasource("snowflake-prod")
sf.update(SnowflakeConfig(warehouse="compute-xxl", database="dev"))
res = sf.query("SELECT COUNT(*) FROM very_large_table")
sf.reset_config()                                   # back to the stored settings
```

Common classes and fields (all optional keyword arguments):

| Class | Configuration fields | Credential fields |
|---|---|---|
| `SnowflakeConfig` | `database`, `schema`, `warehouse`, `role`, `datetime_precision` | `username`, `password`, `private_key`, `passphrase` |
| `RedshiftConfig` | `database`, `datetime_precision`, `region` | `username`, `password`, `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token` |
| `PostgreSQLConfig`, `MySQLConfig` | `database`, `datetime_precision`, `region` | `username`, `password`, AWS keys, (Postgres) `client_cert`, `client_key`, `ca_cert` |
| `S3Config` | `bucket`, `subfolder`, `region` | `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token` |
| `GenericS3Config` | `bucket`, `subfolder`, `host`, `region` | `aws_access_key_id`, `aws_secret_access_key` |
| `ADLSConfig`, `AzureBlobStorageConfig` | `container` | `access_key` |
| `GCSConfig` | `bucket` | `private_key_json` |
| `BigQueryConfig` | `gcp_project_id`, `datetime_precision` | `private_key_json` |
| `DatabricksConfig` | `catalog`, `schema`, `datetime_precision` | `personal_access_token` |
| `DatasetConfig` | `snapshot_id`, `subfolder` | none |

Credential fields take their values from a Domino user or Project environment variable
(`os.environ`), never a literal in code; prefer fixing the Data Source's stored credentials over
overriding them.

`datetime_precision` (relational sources, Domino 6.3 and later) is `seconds`, `milliseconds`,
`microseconds` or `nanoseconds` (default); lower it when extreme datetimes overflow.

## Authentication override

```python
client = DataSourceClient(token="<personal-access-token>")        # explicit bearer
client = DataSourceClient(token_file="/path/to/token")            # alternate token file
```

`DataSourceClient(api_key=...)` and `DOMINO_USER_API_KEY` still exist but use the legacy user
API key, which is deprecated; do not recommend them. Data Sources with Individual credentials
need the current user to have entered theirs under **Data > Data Sources**.

Credential precedence in 6.7.4 differs per call path: Domino API calls (`get_datasource`) use
`token`, then the `DOMINO_API_PROXY` JWT, then `DOMINO_TOKEN_FILE`, then the API key; Data
Source proxy HTTP calls (listing, signed URLs) use `token`, then the API key, then the proxy
JWT, then the token file; Flight queries send the API key and the JWT together when both
exist. In a run that still injects `DOMINO_USER_API_KEY`, listing and signing therefore go out
with the legacy key.

## Errors

```python
import httpx
from domino_data.data_sources import DominoError, UnauthenticatedError

try:
    df = ds.query("SELECT * FROM sales LIMIT 10").to_pandas()
except DominoError as e:
    print(f"query failed: {e}")     # any Flight/Arrow failure, SQL errors and auth included

try:
    keys = s3.list_objects(prefix="raw/")
    data = s3.get("raw/missing.csv")
except UnauthenticatedError:
    print("401 from the Data Source proxy for 60 seconds")
except httpx.HTTPStatusError as e:
    print(f"HTTP {e.response.status_code} on transfer")   # 404 for a missing key
except Exception as e:
    print(f"listing or signing failed: {e}")              # the library raises bare Exception here
```

`get_datasource` raises a bare `Exception` for an unknown name or no access, and the client
constructor raises one when no credential source exists. `query` never raises
`UnauthenticatedError`; it retries 401s for up to 60 seconds and then raises `DominoError`.

## Performance

1. One client per process; each `get_datasource` is an API call.
2. `page_size` on `list_objects` (default 1000) and `max_workers` on `download` for large files.
3. `to_parquet` for large results; filter and project in SQL rather than in pandas.
4. Session overrides (`update`) instead of extra Data Sources for warehouse or schema switches.
