#!/usr/bin/env python
"""
extract_use_cases_from_ppt.py

Reads an account plan PowerPoint from the data folder,
runs embedding-based retrieval + LLM reranking, calls the OpenAI API
to extract use cases, and writes them to a JSON file suitable for further mapping.

Expected env vars:
  OPENAI_API_KEY        - your OpenAI API key (required)
  OPENAI_MODEL          - optional, default "gpt-4o-2024-08-06"
  OPENAI_EMBEDDING_MODEL- optional, default "text-embedding-3-large"
  DATA_DIR              - optional, default "data"
  ACCOUNT_PLAN_PPT      - optional, default "Citigroup FY26 Account Plan Full.pptx"
  OUTPUT_JSON           - optional, default "use_cases_raw.json"
  LILYPAD_PROJECT_ID    - required for lilypad
  LILYPAD_API_KEY       - required for lilypad
"""

import json
import os
import math
import logging
from pathlib import Path
from typing import List, Optional

import lilypad
from openai import OpenAI
from pydantic import BaseModel
from pptx import Presentation

# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
logger = logging.getLogger("extract_use_case")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

# console handler
ch = logging.StreamHandler()
ch.setFormatter(formatter)

# file handler
fh = logging.FileHandler("extract_use_cases.log")
fh.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh)

# -------------------------------------------------------------------
# Lilypad + OpenAI client config
# -------------------------------------------------------------------
lilypad.configure(
    project_id=os.environ["LILYPAD_PROJECT_ID"],
    api_key=os.environ["LILYPAD_API_KEY"],
    auto_llm=True,
)

client = OpenAI()
model_name = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")  # for extraction
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
RERANK_MODEL = os.getenv("OPENAI_RERANK_MODEL", "gpt-4o-mini")  # for reranking


# -------------------------------------------------------------------
# Pydantic models for structured output
# -------------------------------------------------------------------
class UseCase(BaseModel):
    """Schema for one extracted use case (LLM output)."""

    use_case_title: str
    description: str
    slide_numbers: List[int]


class UseCaseList(BaseModel):
    """Wrapper so we can parse a list of use cases."""

    use_cases: List[UseCase]


# -------------------------------------------------------------------
# PPT text extraction
# -------------------------------------------------------------------
def extract_ppt_text(ppt_path: Path) -> List[str]:
    """
    Flatten PPT text slide-by-slide into a string.
    Returns list of slide strings, one per slide.
    """
    prs = Presentation(str(ppt_path))
    logger.debug("Presentation accessed successfully!")
    slide_chunks: List[str] = []

    for i, slide in enumerate(prs.slides, start=1):
        logger.debug(f"Processing slide {i}")

        shape_texts: List[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = (shape.text or "").strip()
                if text:
                    shape_texts.append(text)
        if shape_texts:
            # Include slide number inside the text for extra context
            slide_chunks.append(f"Slide {i}:\n" + "\n".join(shape_texts))

    logger.debug("Extracted text from %d slides", len(slide_chunks))
    return slide_chunks


# -------------------------------------------------------------------
# Embedding-based retrieval
# -------------------------------------------------------------------
class EmbeddingSearch:
    def __init__(self, documents: List[str]):
        """
        documents: list of slide texts, one per slide.
        """
        self.documents = documents
        self.embeddings: List[List[float]] = []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot = 0.0
        norm1 = 0.0
        norm2 = 0.0
        for a, b in zip(v1, v2):
            dot += a * b
            norm1 += a * a
            norm2 += b * b
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (math.sqrt(norm1) * math.sqrt(norm2))

    def build_index(self) -> None:
        """
        Calls the embeddings API once for all documents and stores the vectors.
        """
        logger.info("Building embedding index for %d documents", len(self.documents))

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=self.documents,
        )

        # response.data is a list of objects with .embedding
        self.embeddings = [item.embedding for item in response.data]

        if self.embeddings:
            logger.debug(
                "Embedding index built. Dimensions: %d", len(self.embeddings[0])
            )
        else:
            logger.warning("No embeddings returned from API")

    def search(self, query: str, top_n: int = 20) -> dict:
        """
        Returns top_n most similar documents for the query.
        Structure:
        {
            "documents": [
                {
                    "rank": int,
                    "slide": int,
                    "score": str,
                    "document": str,
                },
                ...
            ]
        }
        """
        if not self.embeddings:
            raise RuntimeError("Embeddings index is empty. Call build_index() first.")

        # Embed the query
        logger.debug("Embedding query for retrieval")
        q_response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[query],
        )
        query_embedding = q_response.data[0].embedding

        # Compute cosine similarity to each document
        similarities: List[float] = []
        for emb in self.embeddings:
            similarities.append(self._cosine_similarity(query_embedding, emb))

        # Rank by similarity
        ranked_indices = sorted(
            range(len(similarities)),
            key=lambda i: similarities[i],
            reverse=True,
        )[:top_n]

        relevant_documents = {"documents": []}
        for rank, i in enumerate(ranked_indices, start=1):
            document = {
                "rank": rank,
                "slide": i + 1,
                "score": f"{similarities[i]:.4f}",
                "document": self.documents[i],
            }
            relevant_documents["documents"].append(document)

        return relevant_documents


# -------------------------------------------------------------------
# Simple OpenAI call for reranking scores
# -------------------------------------------------------------------
def openai_rerank(model: str, prompt: str) -> float:
    """
    Call OpenAI with a prompt that is supposed to return a single number.
    Returns 0.0 on failure so reranking can still proceed.
    """
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
        )
        text = response.output_text.strip()
        score = float(text)
        return score
    except Exception as e:
        logger.error("openai_call failed: %s", e)
        return 0.0


# -------------------------------------------------------------------
# LLM-based reranking
# -------------------------------------------------------------------
def llm_rerank(
    query: str,
    candidates: List[dict],
    model: str = RERANK_MODEL,
    thresh: float = 2.0,
) -> List[dict]:
    """
    Rerank candidate slides using an LLM. Each candidate is a dict:
    {
        "rank": int,
        "slide": int,
        "score": str,        # embedding similarity as string
        "document": str,     # slide text
    }

    We add a 'rerank_score' field and filter by threshold.
    Returns a list of dicts sorted by rerank_score descending.
    """
    reranked: List[dict] = []

    for cand in candidates:
        slide_text = cand["document"]

        prompt = f"""
        Query: {query}

        Slide Text:
        {slide_text}

        Rate how relevant the slide text is to the query provided from 1 (irrelevant)
        to 10 (highly relevant). Output ONLY the number.
        """.strip()

        score = openai_rerank(model, prompt)
        cand = cand.copy()
        cand["rerank_score"] = score
        reranked.append(cand)
        logger.debug(f"Slide text: {slide_text}, Rerank Score: {score}")

    # Sort by rerank_score descending (higher = more relevant)
    reranked.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)

    # Filter by threshold
    filtered = [c for c in reranked if c.get("rerank_score", 0.0) >= thresh]

    # If everything got filtered out, fall back to top few reranked
    if not filtered and reranked:
        logger.warning(
            "No documents passed rerank threshold %.2f, falling back to top 5", thresh
        )
        filtered = reranked[:5]

    return filtered


# -------------------------------------------------------------------
# LLM use-case extraction
# -------------------------------------------------------------------
@lilypad.trace(versioning="automatic")
def extract_use_cases(system_prompt: str, user_prompt: str) -> Optional[UseCaseList]:
    logger.debug("Initiating OpenAI API call for use-case extraction.")
    try:
        response = client.responses.parse(
            model=model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            reasoning={"effort": "high"},
            text_format=UseCaseList,
        )
        logger.debug("Completed OpenAI API call for use-case extraction.")
        return response.output_parsed
    except Exception as e:
        logger.error("extract_use_cases failed: %s", e)
        return None


# -------------------------------------------------------------------
# Main pipeline
# -------------------------------------------------------------------
def main() -> None:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    logger.debug("Data Path - %s", data_dir)

    ppt_filename = os.getenv(
        "ACCOUNT_PLAN_PPT", "Citigroup FY26 Account Plan Full.pptx"
    )
    ppt_path = data_dir / ppt_filename
    logger.debug("PPT Path - %s", ppt_path)

    # output_json = data_dir / os.getenv("OUTPUT_JSON", "use_cases_raw.json")
    # logger.debug("Output JSON Path - %s", output_json)

    if not ppt_path.exists():
        raise FileNotFoundError(f"Account plan PPT not found: {ppt_path}")

    logger.debug("Model Name - %s", model_name)

    # 1) Extract slide texts
    logger.info("Extract documents from pptx")
    documents = extract_ppt_text(ppt_path)

    if not documents:
        logger.error("No text extracted from PPT. Exiting.")
        return

    logger.info("Performing embedding-based retrieval")
    embed_search = EmbeddingSearch(documents)
    embed_search.build_index()

    # Retrieval query should be keyword-heavy, not the whole system prompt
    retrieval_query = """
        Find the slides that describe concrete technology-driven scenarios, 
        problems, or opportunities. Focus on any part of the deck that explains 
        how an agency or organization uses technology to improve operations, 
        modernize systems, automate workflows, strengthen security, enhance 
        developer experience, improve data reliability, or support regulatory 
        and reporting needs. Ignore slides about sales motions, organizational 
        structure, budgeting, or internal strategy.
        """

    # Retrieve a reasonably large candidate set (e.g., 80% of slides, min 5, max all)
    TOP_N = min(len(documents), max(5, int(len(documents) * 0.8)))
    retrievals = embed_search.search(retrieval_query, top_n=TOP_N)
    candidates = retrievals["documents"]

    logger.debug("Embedding retrieval returned %d candidates", len(candidates))

    # 2) LLM reranking
    logger.info("Performing LLM-based reranking")
    reranking_query = """
        Rank passages by how well they describe a concrete technology use case.

        A relevant passage should:
        - State a specific problem or need.
        - Describe a technology-based solution or workflow.
        - Describe a clear outcome or improvement.

        Competitive content is relevant only if it explains a migration or replacement that includes a real technical workflow.

        Downrank passages that focus on sales strategy, procurement mechanics, generic value statements, or organizational details.

        Give the highest score to passages containing all three elements:
        problem + technology approach + outcome.


    """
    reranked_documents = llm_rerank(reranking_query, candidates)

    logger.debug("After reranking, %d documents selected", len(reranked_documents))

    # Build context from reranked docs
    context = "\n\n".join(f"\n{doc['document']}" for doc in reranked_documents)

    logger.debug("Retrieved context length: %d characters - %s", len(context), context)

    # 3) System + user prompts for extraction
    system_prompt = """You are an expert public-sector solutions architect analyzing an account plan
    PowerPoint for the State of Texas. Your job is to extract concrete business and IT
    *use cases* where State of Texas agencies apply technology to achieve a specific
    public-sector outcome.

    DEFINITION OF USE CASE:
    - A use case describes how a Texas agency uses technology to deliver a measurable
    operational, service, compliance, or security improvement.
    - It must contain a specific problem, a technology-enabled approach, and a clear
    benefit to an agency, citizen service, compliance requirement, or operational
    unit.

    EXAMPLES OF VALID USE CASES:
    - Automating Medicaid, SNAP, and TANF eligibility workflows using enterprise
    workload automation (Control-M).
    - Improving mainframe DevX, CI/CD, debugging, and operational maturity for
    HHSC, TxDOT, or DIR-run systems.
    - Modernizing legacy COBOL-based systems for unemployment insurance or benefit
    payment programs.
    - Strengthening security, audit, identity, and regulatory compliance across
    state mainframes and hybrid environments.
    - Implementing statewide observability and APM for cross-agency batch jobs,
    data pipelines, and benefit systems.
    - Risk analytics, fraud detection, and anomaly monitoring for health, human
    services, transportation, or taxation workloads.

    WHAT TO IGNORE (NOT USE CASES):
    - Sales motions such as “identify champions”, “expand stakeholders”, “exec
    alignment”, or QBR/EBR language.
    - Pure procurement mechanics, RFP timelines, budget tables, or account strategy
    notes without a technology scenario.
    - Generic statements like “optimize operations” without a concrete workflow or
    system context.
    - Slides about team structure, org charts, internal quotas, partner lists, or
    deal mechanics.

    SCOPE / DOMAINS OF INTEREST FOR STATE OF TEXAS:
    - Mainframe operations, modernization, and performance (DIR, HHSC, TxDOT).
    - Automation of benefits systems, case management, eligibility, taxation, and
    transportation logistics.
    - Workload automation, job scheduling, and batch modernization (Control-M, CA7).
    - Developer experience (DevX) and code pipelines for legacy and hybrid systems.
    - Observability, APM, logging, and monitoring for statewide systems.
    - Security, compliance, FISMA/NIST, auditability, identity, and access control.
    - Data governance, lineage, reporting, and regulatory/statutory workloads.
    - Hybrid/multi-cloud integration while maintaining mainframe/system-of-record
    stability.

    ABOUT THE INPUT TEXT:
    - Slide text is extracted and often prefixed with “Slide N:”.
    - Multiple slides may describe the same underlying use case with different
    wording—these should be merged.

    INSTRUCTIONS:
    - Identify all distinct technology use cases in the text.
    - Merge duplicates into a single canonical use case.
    - For each use case, produce:
    - A short, specific title.
    - A 1–3 sentence description.
    - All slide numbers where the use case appears.
    - Only include real technology scenarios; ignore sales strategy content.
    """

    user_prompt = (
        "Extract all distinct use cases from the following account plan text.\n\n"
        "Return JSON ONLY, conforming to this structure:\n"
        "{\n"
        '  "use_cases": [\n'
        "    {\n"
        '      "use_case_title": str,\n'
        '      "description": str,\n'
        '      "slide_numbers": [int, ...]\n'
        "    },\n"
        "    ...\n"
        "  ]\n"
        "}\n\n"
        "Account plan text follows:\n\n"
        f"{context}"
    )

    # 4) Call LLM to extract use cases
    parsed: Optional[UseCaseList] = extract_use_cases(system_prompt, user_prompt)
    if parsed is None:
        print("OpenAI API not reachable or parsing failed, please try again later")
        return

    logger.debug("Writing generated JSON to disk")

    records = []
    for idx, uc in enumerate(parsed.use_cases, start=1):
        records.append(
            {
                "id": idx,
                "use_case_title": uc.use_case_title,
                "description": uc.description,
                "slide_numbers": uc.slide_numbers,
                "ppt_source_file": ppt_path.name,
                "source": "Account Plan PPT",
            }
        )

    ARTIFACTS_PATH = "/home/blitz/Desktop/Kinetik/code/chapter-100-experiments/2. Account Plan Plays/exp/artifacts"
    output_json = os.path.join(ARTIFACTS_PATH, "use_cases.json")

    logger.debug("Output JSON Path - %s", output_json)

    # Create directory if it does not exist
    output_dir = os.path.dirname(output_json)
    os.makedirs(output_dir, exist_ok=True)

    # Write file
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    logger.debug("Writing completed.")
    print(f"Wrote {len(records)} use cases → {output_json}")
    # output_json.parent.mkdir(parents=True, exist_ok=True)
    # with output_json.open("w", encoding="utf-8") as f:
    #     json.dump(records, f, indent=2, ensure_ascii=False)

    # logger.debug("Writing completed.")
    # print(f"Wrote {len(records)} use cases → {output_json}")


if __name__ == "__main__":
    main()
