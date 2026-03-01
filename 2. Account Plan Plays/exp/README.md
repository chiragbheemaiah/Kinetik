# `base_implementation`

**Approach:** Full-text dump + GPT with extended reasoning. The simplest approach — no retrieval layer.

---

## How It Works

```
PPTX → python-pptx (text only, all slides)
     → All slide text concatenated into one string
     → GPT (reasoning: high effort) → structured use_cases.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **No retrieval** | All 17 slides sent directly — zero information loss from filtering |
| **`reasoning: high`** | OpenAI extended thinking mode; model reasons carefully before extracting |
| **Single LLM call** | Simpler, cheaper, and easier to debug than RAG pipelines |
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
uv run extract_use_case_from_ppt.py   # → artifacts/use_cases.json
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

## Output Artifacts

| File | Description |
|---|---|
| `artifacts/use_cases.json` | 11 extracted use cases |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad
```

## Accuracy

Extracted **11 use cases** — second highest among all branches. Gets strong results because it sends the full deck with no filtering. Scored 🥈 in overall evaluation. Main limitation: text-only parsing misses visual content; will hit context limits on large decks (100+ slides).
