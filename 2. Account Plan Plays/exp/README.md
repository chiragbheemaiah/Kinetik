# `bm25`

**Approach:** BM25 keyword retrieval — the fastest and cheapest approach.

---

## How It Works

```
PPTX → python-pptx (text only, all slides)
     → Slides tokenized and indexed with BM25Okapi
     → Single keyword query → top-5 scoring slides retrieved
     → Top-5 slides → GPT-4o → structured use_cases.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **BM25Okapi** | TF-IDF style keyword ranking via `rank-bm25` library — no API calls for retrieval |
| **Top-5 cap** | Only the 5 highest-scoring slides are sent to the LLM |
| **Single query** | Static keyword query: `"technology use case business problem solution architecture..."` |
| **No reranking** | Slides fed directly to the extraction LLM |
| **Tracing** | Lilypad |

---

## Setup

```bash
cd exp/
uv sync          # installs rank-bm25 (unique to this branch)
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
| `DATA_DIR` | `data` | |
| `ACCOUNT_PLAN_PPT` | `Citigroup FY26 Account Plan Full.pptx` | |
| `OUTPUT_JSON` | `use_cases_raw.json` | |
| `LILYPAD_PROJECT_ID` / `LILYPAD_API_KEY` | — | ✅ |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad, rank-bm25
```
> `rank-bm25` is the only extra dependency vs. other branches.

## Accuracy

No committed artifact. Structurally limited to ~5 use cases due to the top-5 slide cap. BM25 keyword matching is semantic-blind — slides scored by exact word frequency, not meaning. Slides 9, 11, 12, 13, 14, 15 are likely missed. Lowest accuracy of all branches.

## When to Use

Use `bm25` if you need a quick, low-cost prototype with no embedding API calls. For production or higher quality, prefer `base_implementation` (full-text) or `ppt_processing_llm` (LLM-native).
