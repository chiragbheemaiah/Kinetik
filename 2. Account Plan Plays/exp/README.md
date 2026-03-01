# `ppt_processing_llm` ⭐ Best Accuracy

**Approach:** LLM reads the full deck natively from a PDF — the only branch that sees charts, tables, and visual content.

---

## How It Works

```
PPTX → LibreOffice → PDF
     → Upload PDF to OpenAI Files API
     → gpt-4o-mini reads each slide (text + image/chart summaries)
     → Returns structured List[str] — one string per slide
     → GPT-4o → structured use_cases.json
```

### Key Design Decisions
| Decision | Detail |
|---|---|
| **LLM-native PDF reading** | Uploads the PDF via Files API; LLM sees visual layout, charts, tables |
| **Two-model pipeline** | `PPT_EXTRACTION_MODEL` (`gpt-4o-mini`) reads slides; `OPENAI_MODEL` (`gpt-4o`) extracts use cases |
| **No retrieval** | All slides sent; no embedding or BM25 filtering needed |
| **Tracing** | Lilypad only |

---

## Setup

```bash
# LibreOffice is required for PPTX→PDF conversion (system dependency, not managed by uv)
sudo apt install libreoffice   # Ubuntu/Debian
brew install --cask libreoffice  # macOS

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
| `PPT_EXTRACTION_MODEL` | `gpt-4o-mini` | |
| `DATA_DIR` | `data` | |
| `ACCOUNT_PLAN_PPT` | `Citigroup FY26 Account Plan Full.pptx` | |
| `OUTPUT_JSON` | `use_cases_raw.json` | |
| `LILYPAD_PROJECT_ID` / `LILYPAD_API_KEY` | — | ✅ |

## Output Artifacts

| File | Description |
|---|---|
| `artifacts/use_cases.json` | 20 extracted use cases including per-agency breakdowns |

## Dependencies

```toml
openai, pydantic, python-pptx, lilypad
# + libreoffice (system)
```

## Accuracy

Extracted **20 use cases** — highest of all branches. Uniquely captures per-agency use cases (TRS, ERS, TWC, DPS, DSHS, TxDOT, TxDMV, HHSC) that appear in visual tables on slides 8–9, invisible to all text-only parsers.
