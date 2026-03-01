# Account Plan Plays — Experiment Suite

Extracts structured use cases from a customer account plan PowerPoint, then maps them to an innovation taxonomy and a chessboard operating model. This repo contains **5 experimental branches**, each testing a different approach to the extraction problem.

**Input:** `FY26 State of Texas 10X Mindset - Jeff Ebbrecht AM 08292025.pptx`  
**Output:** `use_cases.json` → `taxonomy.json` → `chessboard.json`

---

## Branches at a Glance

| Branch | Approach | Use Cases | Accuracy |
|---|---|---|---|
| [`base_implementation`](#base_implementation) | Full-text + GPT high reasoning | 11 | 🟢 High |
| [`bm25`](#bm25) | BM25 keyword retrieval | ~5 | 🔴 Low |
| [`rag_embedding_implementation`](#rag_embedding_implementation) | Embedding retrieval + LLM reranker | 6 | 🟠 Medium |
| [`multi-query-rag`](#multi-query-rag) | Multi-query embeddings + reranker | ~7–10 | 🟡 Medium-High |
| [`multi-query-rag-with-relevance-reasoning`](#multi-query-rag-with-relevance-reasoning) | Multi-query + reasoned reranker | 7 | 🟡 Medium-High |
| [`ppt_processing_llm`](#ppt_processing_llm) | LLM reads PDF natively (text + visuals) | 20 | 🟢 Best |

---

## Branch Details

### `base_implementation`
**Default branch.** Simplest approach — no retrieval layer. All slide text is concatenated and sent to GPT with `reasoning: {"effort": "high"}` (extended thinking mode). Strong results because zero information is lost to filtering.

📖 **README:** [`exp/README.md`](exp/README.md)  
🏃 **Run:** `cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

---

### `bm25`
Uses BM25Okapi (TF-IDF keyword search) to select the top-5 most relevant slides before extraction. Fastest and cheapest — no embedding API calls. Limited by keyword-blind retrieval and a hard 5-slide cap.

📖 **README:** Switch to branch → `exp/README.md`  
🏃 **Run:** `git checkout bm25 && cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

---

### `rag_embedding_implementation`
Embeds all slides with `text-embedding-3-large`, retrieves top-20 by cosine similarity, then applies an LLM reranker (float score). Single query limits recall.

📖 **README:** Switch to branch → `exp/README.md`  
🏃 **Run:** `git checkout rag_embedding_implementation && cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

---

### `multi-query-rag`
Extends `rag_embedding_implementation` — LLM generates 3 reformulated queries, each retrieves slides independently, results are merged and reranked (score only). Better recall than single-query.

📖 **README:** Switch to branch → `exp/README.md`  
🏃 **Run:** `git checkout multi-query-rag && cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

---

### `multi-query-rag-with-relevance-reasoning`
Same multi-query approach, but the reranker returns `{score, relevance_reasoning}` — natural language explanation for each decision. Most transparent and debuggable retrieval pipeline.

📖 **README:** Switch to branch → `exp/README.md`  
🏃 **Run:** `git checkout multi-query-rag-with-relevance-reasoning && cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

---

### `ppt_processing_llm`
Converts PPTX → PDF via LibreOffice, uploads to OpenAI Files API, and has `gpt-4o-mini` read each slide including charts, tables, and images. The only approach that sees visual content — produces 20 use cases vs. 6–11 for text-only branches.

📖 **README:** Switch to branch → `exp/README.md`  
🏃 **Run:** `git checkout ppt_processing_llm && cd exp/ && uv sync && source setup_env_var.sh && bash runner.sh`

> **Requires:** LibreOffice — `sudo apt install libreoffice`

---

## Pipeline (all branches)

```
extract_use_case_from_ppt.py   →   use_cases.json
map_innovation_themes.py       →   taxonomy.json
map_chessboard.py              →   chessboard.json
```

Run the full pipeline on any branch:
```bash
cd exp/
uv sync && source setup_env_var.sh
bash runner.sh
```

## Setup

```bash
# Install uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up
git clone git@github.com:chiragbheemaiah/Kinetik.git
cd Kinetik
git checkout <branch>
cd "chapter-100-experiments/2. Account Plan Plays/exp/"
uv sync
cp setup_env_var.sh.example setup_env_var.sh  # fill in your API keys
source setup_env_var.sh
bash runner.sh
```

## Key Findings

> The biggest accuracy gap isn't between RAG strategies — it's between **text-only PPT parsing** (all RAG branches) vs. **LLM-native PDF reading** (`ppt_processing_llm`). Agency-specific use cases embedded in visual tables are completely invisible to `python-pptx` but fully captured when the LLM reads the PDF directly.

**Best hybrid approach:** Use `ppt_processing_llm`'s PDF reader for extraction, feed into `multi-query-rag-with-relevance-reasoning`'s downstream pipeline for mapping.
