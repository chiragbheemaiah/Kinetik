# `rag_embedding_implementation`

**Approach:** Dense embedding retrieval with an LLM reranker (single query).

---

## How It Works

```
PPTX → python-pptx (text only)
     → All slides embedded via text-embedding-3-large
     → Single query → cosine similarity search → top-20 slides
     → LLM reranker scores each slide (float score)
     → Filtered slides → GPT-4o → structured use_cases.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **Semantic retrieval** | Uses OpenAI embeddings + cosine similarity instead of keyword matching |
| **Top-20 retrieval** | Fetches more candidates than `bm25` (top-5) before reranking |
| **LLM reranker** | `gpt-4o-mini` scores each candidate slide for relevance (float) |
| **Single query** | One fixed retrieval query — may miss slides not matched by that query |
| **Tracing** | Lilypad |

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
| `DATA_DIR` | `data` | |
| `ACCOUNT_PLAN_PPT` | `Citigroup FY26 Account Plan Full.pptx` | |
| `OUTPUT_JSON` | `use_cases_raw.json` | |
| `LILYPAD_PROJECT_ID` / `LILYPAD_API_KEY` | — | ✅ |

## Output Artifacts

| File | Description |
|---|---|
| `artifacts/use_cases.json` | 6 extracted use cases |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad
```

## Accuracy

Extracted **6 use cases**. The single-query retrieval + aggressive reranker filtered too heavily in practice — only 2 slides contributed to the final output, missing slides 9, 11, 12, 13, 15. Upgrade to `multi-query-rag` to improve recall.
