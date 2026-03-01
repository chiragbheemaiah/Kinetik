# 2. Account Plan Plays — Experiment Branches

Extracts structured use cases from a customer account plan PowerPoint, then maps them to an innovation taxonomy (AI / Automation / Modernization / Risk & Compliance) and a chessboard operating model.

**PPT used:** `FY26 State of Texas 10X Mindset - Jeff Ebbrecht AM 08292025.pptx`

---

## Installation

All branches use [uv](https://docs.astral.sh/uv/) for package management. Each branch has its own `exp/pyproject.toml` with branch-specific dependencies.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# After checking out a branch, install dependencies
cd exp/
uv sync
```

| Branch | Extra dependency vs. base |
|---|---|
| `bm25` | `rank-bm25` |
| all other branches | *(base: openai, pydantic, python-pptx, lilypad, langsmith)* |

---

## Environment Setup

All branches require the same environment variables. Source the shared setup file before running any script:

```bash
source exp/setup_env_var.sh
```

Required variables:
| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENAI_MODEL` | Model to use (e.g. `gpt-4o-2024-08-06`) |
| `DATA_DIR` | Absolute path to the `data/` folder |
| `ACCOUNT_PLAN_PPT` | Absolute path to the `.pptx` file |
| `OUTPUT_JSON` | Output path for `use_cases.json` |
| `LILYPAD_PROJECT_ID` / `LILYPAD_API_KEY` | Lilypad tracing credentials |

---

## Branch Overview

| Branch | Approach | Use Cases Extracted | Accuracy |
|---|---|---|---|
| `bm25` | BM25 keyword retrieval | ~5 | 🔴 Low |
| `rag_embedding_implementation` | Embedding retrieval + LLM reranker | 6 | 🟠 Medium |
| `base_implementation` | Full-text dump + GPT high reasoning | 11 | 🟢 High |
| `multi-query-rag-with-relevance-reasoning` | Multi-query embeddings + reasoned reranker | 7 | 🟡 Medium-High |
| `ppt_processing_llm` | LLM reads PDF natively (text + visuals) | 20 | 🟢 Best |

---

## Branch Details

### `bm25`
**Approach:** Extracts text from all slides using `python-pptx`, tokenizes each slide, then runs BM25Okapi (TF-IDF keyword search) to retrieve the top-5 most relevant slides. Those slides are sent to GPT-4o for use case extraction.

**Strengths:** No embedding API calls needed — fast and cheap.  
**Weaknesses:** Keyword-blind (no semantic understanding). Hardcoded top-5 cap severely limits recall. A generic BM25 query means noisy slide selection.

**Run:**
```bash
git checkout bm25
cd exp/
uv sync
source setup_env_var.sh
uv run extract_use_case_from_ppt.py
```

**Output:** `$OUTPUT_JSON` — a JSON array of use case objects.

---

### `rag_embedding_implementation`
**Approach:** Extracts slide text via `python-pptx`, embeds all slides using `text-embedding-3-large`, builds an in-memory cosine similarity index. Retrieves top-20 slides for a single query, then applies an LLM reranker (float score) to filter down before sending to GPT-4o for extraction.

**Strengths:** Semantic retrieval — understands meaning, not just keywords.  
**Weaknesses:** Single query may miss slides. Reranker sometimes filters too aggressively (only 2 slides were used in practice).

**Run:**
```bash
git checkout rag_embedding_implementation
cd exp/
uv sync
source setup_env_var.sh
uv run extract_use_case_from_ppt.py
```

**Additional env vars:**
| Variable | Default |
|---|---|
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| `OPENAI_RERANK_MODEL` | `gpt-4o-mini` |

---

### `base_implementation`
**Approach:** The simplest approach — no retrieval layer at all. Extracts all slide text with `python-pptx`, concatenates all slides into one string, and sends the full deck to GPT with `reasoning: {"effort": "high"}` (OpenAI extended thinking mode). The LLM reasons through the full context before extracting use cases.

**Strengths:** Zero information loss from retrieval. High-reasoning mode produces careful, well-grouped use cases. Simpler to debug and maintain.  
**Weaknesses:** Sends the entire deck in one prompt — will hit context limits on very large decks (100+ slides). Misses visual content (charts, images) since `python-pptx` is text-only.

**Run:**
```bash
git checkout base_implementation
cd exp/
uv sync
source setup_env_var.sh
uv run extract_use_case_from_ppt.py
```

---

### `multi-query-rag-with-relevance-reasoning`
**Approach:** Extends the embedding approach with two improvements: (1) an LLM generates 3 reformulated versions of the retrieval query, each is used independently to retrieve slides, results are merged and deduplicated; (2) the reranker returns both a relevance score and a natural-language reasoning string explaining why each slide is or isn't relevant.

**Strengths:** Best retrieval architecture. Multi-query covers more of the slide deck. Reasoned reranker is more reliable than score-only.  
**Weaknesses:** Most expensive to run (multiple LLM + embedding calls). Still text-only PPT parsing.

**Run (step by step):**
```bash
git checkout multi-query-rag-with-relevance-reasoning
cd exp/
uv sync
source setup_env_var.sh
uv run extract_use_case_from_ppt.py   # → artifacts/use_cases.json
uv run map_innovation_themes.py       # → artifacts/taxonomy.json
uv run map_chessboard.py              # → artifacts/chessboard.json
```

**Run (full pipeline):**
```bash
cd exp/
uv sync && source setup_env_var.sh
bash runner.sh
```

**Additional env vars:**
| Variable | Default |
|---|---|
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| `OPENAI_RERANK_MODEL` | `gpt-4o-mini` |
| `QUERY_GENERATION_MODEL` | `gpt-4o-mini` |
| `LANGSMITH_TRACING` | `true` |
| `LANGSMITH_API_KEY` | *(your key)* |
| `LANGSMITH_PROJECT` | `kinetik-tracing-v1` |

---

### `ppt_processing_llm` ⭐ Best Accuracy
**Approach:** Converts the PPTX to PDF using LibreOffice, uploads the PDF to the OpenAI Files API, then prompts `gpt-4o-mini` to read the PDF slide-by-slide and produce a structured text representation — including summaries of any images, charts, or tables it sees. The resulting slide strings are then sent to the main model for use case extraction.

**Strengths:** Only approach that sees visual content (charts, tables, diagrams). Produces 20 use cases including per-agency breakdowns that are entirely invisible to text-only parsers. Highest coverage.  
**Weaknesses:** Requires LibreOffice installed on the machine. Two-step LLM call adds latency.

**System dependency:**
```bash
# LibreOffice is required for PPTX→PDF conversion (not managed by uv)
sudo apt install libreoffice   # Ubuntu/Debian
brew install --cask libreoffice  # macOS
```

**Run (full pipeline):**
```bash
git checkout ppt_processing_llm
cd exp/
uv sync && source setup_env_var.sh
bash runner.sh
```

**Run (extract only):**
```bash
uv run extract_use_case_from_ppt.py
```

**Additional env vars:**
| Variable | Default |
|---|---|
| `PPT_EXTRACTION_MODEL` | `gpt-4o-mini` |

---

## Artifacts

Committed `use_cases.json` outputs are available in `exp/artifacts/` on:
- `base_implementation` — 11 use cases
- `rag_embedding_implementation` — 6 use cases
- `ppt_processing_llm` — 20 use cases
- `multi-query-rag-with-relevance-reasoning` — 7 use cases + chessboard + taxonomy

---

## Recommended Path Forward

For maximum accuracy, combine the two best-performing approaches:
1. Use `ppt_processing_llm`'s **LLM-native PDF reader** to capture visual slide content
2. Feed the resulting slide strings into the `multi-query-rag-with-relevance-reasoning` **downstream pipeline** (`map_chessboard.py` + `map_innovation_themes.py`) for full classification
