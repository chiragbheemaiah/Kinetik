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
from typing import Any, List, Optional

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

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
RERANK_MODEL = os.getenv("OPENAI_RERANK_MODEL", "gpt-4o-mini")
QUERY_GENERATION_MODEL = os.getenv("QUERY_GENERATION_MODEL", "gpt-4o-mini")

client = OpenAI()


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


class RerankingModel(BaseModel):
    score: float
    relevance_reasoning: str


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
                text = (shape.text or "").strip()  # type: ignore
                if text:
                    shape_texts.append(text)
        if shape_texts:
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

        self.embeddings = [item.embedding for item in response.data]

        if self.embeddings:
            logger.debug(
                "Embedding index built. Dimensions: %d", len(self.embeddings[0])
            )
        else:
            logger.warning("No embeddings returned from API")

    def search(self, query: str, top_n: int = 5) -> dict:
        """
        Returns top_n most similar documents for the query.
        Structure:
        {
            "documents": [
                {
                    "slide_id" : int
                    "rank": int,
                    "similarity_score": str,
                    "document": str,
                },...
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
                "slide_id": i + 1,
                "rank": rank,
                "similarity_score": f"{similarities[i]:.4f}",
                "document": self.documents[i],
            }
            relevant_documents["documents"].append(document)
        return relevant_documents


# -------------------------------------------------------------------
# Simple OpenAI call for reranking scores
# -------------------------------------------------------------------
def openai_rerank(model: str, prompt: str) -> RerankingModel | None:
    """
    Call OpenAI with a prompt that is supposed to return a single number along with reasoning as to why the document is relevant.
    Returns 0.0 on failure so reranking can still proceed.
    """
    try:
        response = client.responses.parse(
            model=model, input=prompt, text_format=RerankingModel
        )
        rerank_relevance = response.output_parsed
        if not rerank_relevance:
            return None
        logger.debug(
            f"Returned relevance score - {rerank_relevance.score}, with reasoning - {rerank_relevance.relevance_reasoning}"
        )
        return rerank_relevance
    except Exception as e:
        logger.error("openai_call failed: %s", e)
        return None


def openai_multi_query_generator(model: str, prompt: str) -> list[str]:
    """Call OpenAI to generate multiple queries for the a given prompt"""
    try:
        response = client.responses.create(model=model, input=prompt)
        query_response = response.output_text
        queries = json.loads(query_response)
        logger.debug(f"Generated query: {queries}")
        return queries["queries"]

    except Exception as e:
        logger.error("Open AI call failed: %s", e)
        return []


# -------------------------------------------------------------------
# LLM-based reranking
# -------------------------------------------------------------------
def llm_rerank(
    query: str,
    candidates: list[dict],
    model: str = RERANK_MODEL,
    thresh: float = 5.0,
) -> List[dict] | None:
    """
    Rerank candidate slides using an LLM. Each candidate is a dict:
    {
        "rank": int,
        "score": str,        # embedding similarity as string
        "document": str,     # slide text
    }

    We add a 'rerank_score' field and filter by threshold.
    Returns a list of dicts sorted by rerank_score descending.
    """
    reranked: List[dict] = []

    for candidate in candidates:
        slide_text = candidate["document"]

        prompt = f"""
        Query: {query}

        Slide Text:
        {slide_text}

        Rate how relevant this slide is to the query from 1 (irrelevant)
        to 10 (highly relevant) Add the reasoning as to why this document is relevant to the query as well.
        """.strip()

        relevance = openai_rerank(model, prompt)
        if not relevance:
            return None

        candidate = candidate.copy()
        candidate["rerank_score"] = relevance.score
        candidate["reasoning"] = relevance.relevance_reasoning
        reranked.append(candidate)

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
            model=MODEL_NAME,
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


def retrieval_reranking_pipeline(
    retrieval_query, embed_search: EmbeddingSearch, top_n: int = 5
) -> list[dict] | None:
    # Retrieve a reasonably large candidate set (e.g., 80% of slides, min 5, max all)
    TOP_N = min(len(embed_search.documents), top_n)
    retrievals = embed_search.search(retrieval_query, top_n=TOP_N)
    candidates = retrievals["documents"]

    logger.debug("Embedding retrieval returned %d candidates", len(candidates))
    logger.debug(f"The candidates are: {candidates}")

    # 2) LLM reranking
    logger.info("Performing LLM-based reranking")
    reranked_documents = llm_rerank(retrieval_query, candidates)
    if not reranked_documents:
        return None
    logger.debug("After reranking, %d documents selected", len(reranked_documents))

    return reranked_documents


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

    if not ppt_path.exists():
        raise FileNotFoundError(f"Account plan PPT not found: {ppt_path}")

    logger.debug("Model Name - %s", MODEL_NAME)

    # 1) Extract slide texts
    logger.info("Extract documents from pptx")
    documents = extract_ppt_text(ppt_path)

    if not documents:
        logger.error("No text extracted from PPT. Exiting.")
        return

    logger.info("Performing embedding-based retrieval")
    embed_search = EmbeddingSearch(documents)
    embed_search.build_index()

    # Multi query approach
    MULTI_QUERY_CNT = 3
    retrieval_query = """
        Find the slides that describe concrete technology-driven scenarios, 
        problems, or opportunities. Focus on any part of the deck that explains 
        how an agency or organization uses technology to improve operations, 
        modernize systems, automate workflows, strengthen security, enhance 
        developer experience, improve data reliability, or support regulatory 
        and reporting needs. Ignore slides about sales motions, organizational 
        structure, budgeting, or internal strategy.
        """

    relevant_documents = set()
    query_generation_prompt = (
        f"Given the retrieval prompt: '{retrieval_query}', generate "
        f"{MULTI_QUERY_CNT} alternative search queries. Each must preserve the "
        "meaning of the original prompt while varying phrasing and including all "
        "major subject angles. Output valid JSON only, using the schema:\n"
        "{\n"
        '  "queries": ["query1", "query2", ...]\n'
        "}\n"
        "Do not include anything outside the JSON object."
    )

    retrieval_queries: list[str] = openai_multi_query_generator(
        QUERY_GENERATION_MODEL, query_generation_prompt
    )

    retrieval_queries.append(retrieval_query)
    for retrieval_query in retrieval_queries:
        # Retrieve relevant document indexes
        retrieved_docs = retrieval_reranking_pipeline(retrieval_query, embed_search)

        if not retrieved_docs:
            logger.error("Relevant documents could not be retrieved. ")
            return None
        for document in retrieved_docs:
            doc_id = document["slide_id"]
            relevant_documents.add(doc_id)

    context = ""

    for doc_id in relevant_documents:
        context_doc = None
        for retr_doc in retrieved_docs:
            if retr_doc["slide_id"] == doc_id:
                context_doc = retr_doc
                break

        logger.debug(f"Retrieving document with id - {doc_id - 1}")

        if context_doc is None:
            logger.warning(f"No retrieved document found for slide_id={doc_id}")
            continue

        document_content = context_doc.get("document", "")
        document_reasoning = context_doc.get("reasoning", "")

        # Add both content and reasoning into the context string
        context += (
            f"\n\n[CONTENT - SLIDE {doc_id}]\n{document_content}"
            f"\n\n[REASONING - SLIDE {doc_id}]\n{document_reasoning}"
        )

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
        "Extract all distinct use cases from the following account plan text. \n\n"
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


if __name__ == "__main__":
    main()
