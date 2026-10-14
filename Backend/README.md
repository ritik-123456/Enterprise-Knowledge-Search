# Enterprise Knowledge Search (EKS) — Backend Service

FastAPI service powering the Enterprise Knowledge Search platform. Supports dense vector search via Qdrant, corpus-wide BM25 keyword matching, Reciprocal Rank Fusion, query decomposition, and small-to-big parent-child retrieval.

## Quick Links
- **Full Architecture & Benchmarks**: Refer to the root [README.md](../README.md).
- **Evaluation Benchmark**: Run `python tests/eval_cross_questions.py improved`
- **Interactive API Docs (Swagger)**: `http://localhost:8000/docs`

## Quick Start
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Start backend server
uvicorn app.main:app --reload --port 8000
```

## Running Tests & Benchmark
```bash
# Unit & integration tests
pytest tests/

# Baseline vs Improved evaluation
python tests/eval_cross_questions.py improved

# Ablation test (e.g. testing effect of disabling BM25 keyword search)
python tests/eval_cross_questions.py ablation ENABLE_HYBRID_BM25
```
