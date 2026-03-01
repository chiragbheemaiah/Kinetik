# `multi-query-rag-with-relevance-reasoning`

**Approach:** Multi-query embedding retrieval with a reasoned LLM reranker + full downstream pipeline.

---

## How It Works

```
PPTX → python-pptx (text only)
     → LLM generates 3 reformulated queries
     → Each query → embedding search (text-embedding-3-large, top-5)
     → Results merged & deduplicated
     → LLM reranker scores each slide + explains relevance in natural language
     → Top slides → GPT-4o → structured use_cases.json
     → map_chessboard.py → chessboard.json
     → map_innovation_themes.py → taxonomy.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **Multi-query** | LLM generates 3 paraphrased variants of the retrieval query to improve slide recall |
| **Reasoned reranker** | Returns `{score: float, relevance_reasoning: str}` — more reliable than score-only |
| **Tracing** | Lilypad (LLM calls) + LangSmith (`@traceable` decorators) |
| **Full pipeline** | Only branch with all 3 scripts + `runner.sh` orchestrator |

---

## Setup

```bash
cd exp/
uv sync
source setup_env_var.sh
```

## Run

```bash
# Step by step
uv run extract_use_case_from_ppt.py   # → artifacts/use_cases.json
uv run map_chessboard.py              # → artifacts/chessboard.json
uv run map_innovation_themes.py       # → artifacts/taxonomy.json

# Or full pipeline
bash runner.sh
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
| `LANGSMITH_PROJECT` | `kinetik-tracing-v1` | |

## Output Artifacts

| File | Description |
|---|---|
| `artifacts/use_cases.json` | Extracted use cases with slide numbers |
| `artifacts/chessboard.json` | Use cases mapped to operating units |
| `artifacts/taxonomy.json` | Use cases mapped to AI/Automation/Risk taxonomy |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad, langsmith
```

## Accuracy

Extracted **7 use cases** from the State of Texas deck. Better slide coverage than single-query branches but still text-only — misses visual content in charts/tables.
