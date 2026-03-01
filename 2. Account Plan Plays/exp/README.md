# `multi-query-rag`

**Approach:** Multi-query embedding retrieval with LLM reranking (score only).

---

## How It Works

```
PPTX → python-pptx (text only)
     → LLM generates 3 reformulated queries
     → Each query → embedding search (text-embedding-3-large, top-5)
     → Results merged & deduplicated
     → LLM reranker scores each slide (float score only)
     → Top slides → GPT-4o → structured use_cases.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **Multi-query** | LLM generates 3 paraphrased query variants to improve slide recall |
| **Score-only reranker** | Returns a float relevance score (no reasoning) via `gpt-4o-mini` |
| **Tracing** | Lilypad + LangSmith `@traceable` decorators |
| **Extract only** | No downstream mapping scripts (unlike the `-with-relevance-reasoning` branch) |

---

## Setup

```bash
cd exp/
uv sync
source setup_env_var.sh
```

## Run

```bash
uv run extract_use_case_from_ppt.py   # → $OUTPUT_JSON
```

## Environment Variables

| Variable | Default | Required |
|---|---|---|
| `OPENAI_API_KEY` | — | ✅ |
| `OPENAI_MODEL` | `gpt-4o-2024-08-06` | |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` | |
| `OPENAI_RERANK_MODEL` | `gpt-4o-mini` | |
| `QUERY_GENERATION_MODEL` | `gpt-4o-mini` | |
| `DATA_DIR` | `data` | |
| `ACCOUNT_PLAN_PPT` | `Citigroup FY26 Account Plan Full.pptx` | |
| `OUTPUT_JSON` | `use_cases_raw.json` | |
| `LILYPAD_PROJECT_ID` / `LILYPAD_API_KEY` | — | ✅ |
| `LANGSMITH_API_KEY` | — | ✅ |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad, langsmith
```

## Accuracy

No committed artifact. Structurally similar to `multi-query-rag-with-relevance-reasoning` but reranker provides less signal (score only, no reasoning string). Expected ~7–10 use cases.

## Difference from `multi-query-rag-with-relevance-reasoning`

The reranker here returns a plain `float`. The `-with-relevance-reasoning` branch upgrades this to a `{score, relevance_reasoning}` struct, making the reranking step more reliable and debuggable. The `-with-relevance-reasoning` branch also adds the full downstream pipeline (`map_chessboard.py`, `map_innovation_themes.py`, `runner.sh`).
