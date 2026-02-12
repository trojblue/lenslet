# Embedding Similarity Search


## Purpose / Big Picture


Lenslet can run cosine similarity search against fixed-size list embedding columns stored in `items.parquet`. Embeddings are loaded on demand into a float32 matrix, optional caching keeps startup and repeated searches fast, and FAISS acceleration is enabled automatically when installed.


## Usage


### Auto-detection and CLI overrides

- Fixed-size list columns (float16/float32/float64/bfloat16) are auto-detected.
- Use `--embedding-column` to force a column (repeatable or comma-separated).
- Use `--embedding-metric name:metric` to override (currently only `cosine`).


### API calls

Search by image path:

```bash
curl -X POST http://127.0.0.1:7070/embeddings/search \
  -H "Content-Type: application/json" \
  -d '{"embedding":"clip","query_path":"/images/cat.jpg","top_k":50,"min_score":0.2}'
```

Search by base64 vector:

```bash
curl -X POST http://127.0.0.1:7070/embeddings/search \
  -H "Content-Type: application/json" \
  -d '{"embedding":"clip","query_vector_b64":"BASE64_FLOAT32","top_k":50}'
```


### Vector format

- Standard base64 encoding
- Little-endian float32
- Byte length must equal `dimension * 4`

Example encoding snippet:

```python
import base64
import numpy as np

vec = np.asarray([0.1, 0.2, 0.3], dtype="<f4")
payload = base64.b64encode(vec.tobytes()).decode("ascii")
```


## Cache and Preload


- Cache files are stored under `.lenslet/embeddings_cache/` or `<parquet>.cache/embeddings_cache/`.
- Cache keys include dataset path, column name, dtype, dimension, and Parquet mtime/size.
- Use `--embedding-cache-dir` to override the location.
- Use `--no-embedding-cache` to disable cache writes (also disabled by `--no-write`).
- Use `--embedding-preload` to build embedding indexes at startup.


## Optional FAISS Acceleration


Install FAISS to speed up top-K searches:

```bash
pip install "lenslet[embeddings-faiss]"
```

When FAISS is available, Lenslet uses it automatically; otherwise it falls back to NumPy.
