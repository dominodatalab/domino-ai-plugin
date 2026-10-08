# Dataset best practices

Storage selection, directory layout, file formats, metadata, snapshot-before-change, and techniques for reading datasets larger than memory (chunking, Dask, memory mapping).

## Best Practices

### 1. Use Appropriate Storage
| Data Type | Storage |
|-----------|---------|
| Large training data | Domino Dataset |
| Model artifacts | `/mnt/artifacts/` |
| Code | Git/Project files |
| Temporary files | `/tmp/` |

### 2. Organize Data
```
/mnt/data/my-dataset/
├── raw/
│   ├── customers.csv
│   └── transactions.csv
├── processed/
│   ├── features.parquet
│   └── labels.parquet
└── metadata/
    └── schema.json
```

### 3. Use Efficient Formats
```python
# Parquet for tabular data (faster, smaller)
df.to_parquet("/mnt/data/dataset/data.parquet")

# Feather for pandas DataFrames
df.to_feather("/mnt/data/dataset/data.feather")

# HDF5 for numerical arrays
import h5py
with h5py.File("/mnt/data/dataset/data.h5", "w") as f:
    f.create_dataset("features", data=features)
```

### 4. Document Data
Include README and schema:
```python
# Write metadata
metadata = {
    "created": "2024-01-15",
    "source": "Customer database",
    "columns": {"id": "int", "name": "string", "value": "float"}
}

with open("/mnt/data/dataset/metadata.json", "w") as f:
    json.dump(metadata, f)
```

### 5. Snapshot Before Changes
```python
# Create snapshot before processing
domino.datasets_snapshot(
    dataset_name="training-data",
    tag="pre-processing"
)

# Then modify data
process_data()
```

## Reading Large Datasets

### Chunked Reading
```python
# Read in chunks
chunks = pd.read_csv(
    "/mnt/data/dataset/large_file.csv",
    chunksize=100000
)

for chunk in chunks:
    process(chunk)
```

### Lazy Loading with Dask
```python
import dask.dataframe as dd

# Read without loading into memory
df = dd.read_parquet("/mnt/data/dataset/large_data.parquet")

# Process lazily
result = df.groupby("category").mean().compute()
```

### Memory Mapping
```python
import numpy as np

# Memory-map large arrays
data = np.memmap(
    "/mnt/data/dataset/features.dat",
    dtype='float32',
    mode='r',
    shape=(1000000, 100)
)
```
