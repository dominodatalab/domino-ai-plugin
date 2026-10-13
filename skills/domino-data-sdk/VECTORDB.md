# Vector databases: Pinecone through a Domino Data Source

`domino_data.vectordb` holds two helpers that point the official Pinecone Python client at
Domino's Data API gateway, which injects the API key stored in the Pinecone Data Source. The
key never reaches your code. Everything after initialisation is the standard Pinecone client.

Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/data-source-connectors/connect-to-pinecone
and https://docs.domino.ai/cloud/platform-capabilities/core-concepts/data/data-source-connectors/vector-databases.
Source: `domino_data/vectordb.py` (26 lines).

Qdrant has a Data Source connector too (`connect-to-qdrant` on the same docs path) but no helper
in this library; use the UI code snippet for it. The snippet is also served by
`GET /v4/datasource/{dataSourceId}/connection/string/all?dataSourceName=<name>` (Internal API,
may change between Domino versions), which returns `snippetsByLanguages` for Python, R and SAS.

## Prerequisites

1. A Pinecone Data Source (created with the Pinecone API key; environment name and project ID
   are needed only when the Data Source is used from `pinecone-client<3.0.0`), added to the
   Project.
2. The Pinecone client at a version the Domino helpers support: **3.x through 8.x**. From
   `pinecone` 9.0.0 (May 2026) `Pinecone.Index()` rejects every keyword except `pool_threads`
   with `TypeError`, and `domino_pinecone3x_index_params` passes `host` and
   `additional_headers`, so an unpinned install (10.0.0 today) breaks the recipe below. The PyPI
   package is `pinecone`; `pinecone-client` (frozen at 6.0.0, which also works) is the deprecated
   former name and must be uninstalled first because the two conflict; the Domino Standard
   Environment ships `pinecone-client` 3.0.3, so a DSE-based environment needs that uninstall
   before `pip install pinecone`. The docs page still shows `pinecone-client`.

```dockerfile
USER root
RUN python -m pip install "pinecone>=3,<9" "dominodatalab-data>=6.7.4"
USER ubuntu
```

The gRPC client (`pinecone[grpc]`) is not supported through the gateway.

## Initialise

```python
from domino_data.vectordb import domino_pinecone3x_init_params, domino_pinecone3x_index_params
from pinecone import Pinecone

datasource_name = "pinecone-ds"            # Data Source name in Domino
pc = Pinecone(**domino_pinecone3x_init_params(datasource_name))
print(pc.list_indexes())

index = pc.Index(**domino_pinecone3x_index_params(datasource_name, "embeddings"))
print(index.describe_index_stats())
```

What the helpers return:

| Helper | Returns |
|---|---|
| `domino_pinecone3x_init_params(datasource_name)` | `{"api_key": "domino", "host": <gateway>, "additional_headers": {"X-Domino-Datasource": datasource_name}}` |
| `domino_pinecone3x_index_params(datasource_name, index_name)` | `{"host": <gateway>, "additional_headers": {"X-Domino-Datasource": ..., "X-Domino-Pinecone-Index": index_name}}` |

`<gateway>` is `DOMINO_DATA_API_GATEWAY`, default `http://127.0.0.1:8766`, injected in
executions. The placeholder `api_key` satisfies the client; the gateway substitutes the real
one. Get a copy-ready version from **Data > Data Sources > Code snippet > Python**.

## Vector operations (standard Pinecone client)

```python
index.upsert(
    vectors=[
        {"id": "doc1", "values": embedding_1, "metadata": {"text": "...", "source": "wiki"}},
        {"id": "doc2", "values": embedding_2, "metadata": {"text": "...", "source": "blog"}},
    ],
    namespace="default",
)

results = index.query(vector=query_embedding, top_k=10, include_metadata=True,
                      namespace="default", filter={"source": {"$eq": "wiki"}})
for match in results.matches:
    print(match.id, match.score, match.metadata)

index.delete(ids=["doc1"], namespace="default")
index.delete(filter={"source": {"$eq": "old"}})
index.delete(delete_all=True, namespace="test")
```

## Retrieval-augmented generation sketch

```python
def embed(text: str) -> list[float]:
    ...   # your embedding model; call it through LLM Gateway 2.0 where deployed (domino-llm-gateway) or a Domino-hosted endpoint (domino-llm-access)

def retrieve(question: str, top_k: int = 5) -> list[str]:
    hits = index.query(vector=embed(question), top_k=top_k, include_metadata=True)
    return [m.metadata["text"] for m in hits.matches]

context = "\n\n".join(retrieve("What is a Domino Dataset?"))
```

Trace the pipeline with the domino-genai-tracing skill when it runs as an agent or App.

## Practices

1. Upsert in batches of about 100 vectors.
2. Use namespaces to separate corpora; store the source text or a pointer in metadata.
3. Keep vector dimensions equal to the index dimension; mismatches fail at upsert.
4. Dense and sparse index creation is done in Pinecone, not through Domino.

## Troubleshooting

| Issue | Check |
|---|---|
| Connection refused or timeout | `DOMINO_DATA_API_GATEWAY` is set and reachable; you are inside a Domino execution |
| 401 or 403 from the gateway | The Pinecone Data Source is added to the Project and its stored key is valid |
| Index not found | `index_name` matches `pc.list_indexes()`; a `pinecone-client<3.0.0` setup needs environment name and project ID on the Data Source |
| `TypeError: Pinecone.Index() got unexpected keyword arguments: ['additional_headers', 'host']` | `pinecone` 9.x or later installed; pin `pinecone>=3,<9` |
| `ImportError` for `Pinecone` | `pinecone` (3.x or later) installed and `pinecone-client` removed |
| Dimension mismatch | Embedding model output size versus index dimension |
