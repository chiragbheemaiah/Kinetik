#!/usr/bin/env python
"""
map_innovation_themes.py

Takes raw use cases JSON and maps each use case to:
  - tier_1 (e.g. AI, Automation, Risk & Compliance)
  - tier_2 (sub-theme from your taxonomy)

Traceability fields like ppt_source_file and source are preserved.

Expected env vars:
  OPENAI_API_KEY - your OpenAI API key (required)
  OPENAI_MODEL   - optional, default "gpt-4o-2024-08-06"
  INPUT_JSON     - optional, default "data/use_cases_raw.json"
  OUTPUT_JSON    - optional, default "data/use_cases_with_themes.json"
"""

import json
import os
from pathlib import Path
from typing import List
import logging


from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger("map_innovation_theme")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("\n %(asctime)s | %(levelname)s | %(message)s")

# console handler
ch = logging.StreamHandler()
ch.setFormatter(formatter)

# file handler
fh = logging.FileHandler("extract_use_cases.log")
fh.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh)

# ---------------------------------------------------------------------------
# Replace / extend this with your taxonomy, or load it from Excel/CSV.
# ---------------------------------------------------------------------------
INNOVATION_TAXONOMY = [
    {
        "tier_1": "AI",
        "tier_2": "AI for Data & Analytics",
        "definition": "ML/GenAI for analytics, fraud, forecasting, natural language insights, etc.",
    },
    {
        "tier_1": "AI",
        "tier_2": "AI Risk & Governance",
        "definition": "Model risk, governance, fairness, compliance, auditability for AI/ML.",
    },
    {
        "tier_1": "Automation",
        "tier_2": "Data Pipeline Management",
        "definition": "End-to-end orchestration and automation of data flows and pipelines.",
    },
    {
        "tier_1": "Automation",
        "tier_2": "Dev & Platform Automation",
        "definition": "CI/CD, infrastructure-as-code, platform automation.",
    },
    {
        "tier_1": "Modernization",
        "tier_2": "Mainframe Modernization",
        "definition": "Modernize and extend mainframe into hybrid cloud, replace legacy tooling.",
    },
    {
        "tier_1": "Risk & Compliance",
        "tier_2": "Regulatory Reporting & Evidence",
        "definition": "Automated reporting, ESG, audit evidence, regulator-facing outputs.",
    },
    {
        "tier_1": "Risk & Compliance",
        "tier_2": "Operational Risk & Controls",
        "definition": "Controls automation, dashboards, operational risk in IT and business processes.",
    },
    # ...drop in the rest of your taxonomy as needed...
]


class ThemeAssignment(BaseModel):
    """Theme mapping for a single use case (LLM output)."""

    id: int
    tier_1: str
    tier_2: str


class ThemeAssignments(BaseModel):
    """Wrapper Pydantic model for structured outputs."""

    assignments: List[ThemeAssignment]


def main() -> None:
    # input_path = Path(os.getenv("INPUT_JSON", "data/use_cases_raw.json"))
    # output_path = Path(os.getenv("OUTPUT_JSON", "data/use_cases_with_themes.json"))

    ARTIFACTS_PATH = Path(
        "/home/blitz/Desktop/Kinetik/code/chapter-100-experiments/2. Account Plan Plays/exp/artifacts"
    )
    INPUT_FILENAME = "use_cases.json"
    input_path = ARTIFACTS_PATH / INPUT_FILENAME

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")

    # validate file exists
    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    # load JSON
    use_cases = None
    with input_path.open("r", encoding="utf-8") as f:
        use_cases = json.load(f)

    client = OpenAI()

    # Build taxonomy text block for the prompt
    taxonomy_lines = []
    for t in INNOVATION_TAXONOMY:
        taxonomy_lines.append(
            f"- Tier 1: {t['tier_1']} | Tier 2: {t['tier_2']} | {t['definition']}"
        )
    taxonomy_text = "\n".join(taxonomy_lines)
    logger.debug(f"Taxonomy text: {taxonomy_text}")

    # Build list of use cases to classify
    use_case_lines = []
    for uc in use_cases:
        # The extractor assigns "id"; if absent, fall back to list index.
        uc_id = uc.get("id")
        if uc_id is None:
            uc_id = len(use_case_lines) + 1
            uc["id"] = uc_id
        title = uc.get("use_case_title", "")
        desc = uc.get("description", "")
        use_case_lines.append(f"{uc_id}. {title} :: {desc}")

    use_cases_text = "\n".join(use_case_lines)

    system_prompt = (
        "You are mapping banking & mainframe-related use cases to a 2-level "
        "innovation theme taxonomy (Tier 1, Tier 2).\n\n"
        "Rules:\n"
        "- For EACH use case, choose exactly ONE Tier 1 and ONE Tier 2.\n"
        "- Only use combinations from the allowed taxonomy below.\n"
        "- Prefer the most specific Tier 2 based on the description.\n"
        "- If multiple could apply, choose the best primary fit.\n"
    )

    user_prompt = (
        "Allowed innovation taxonomy (Tier 1 / Tier 2):\n"
        f"{taxonomy_text}\n\n"
        "Use cases to classify (id. title :: description):\n"
        f"{use_cases_text}\n\n"
        "Return JSON ONLY in this structure:\n"
        "{\n"
        '  "assignments": [\n'
        '    {"id": int, "tier_1": str, "tier_2": str},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
    )

    try:
        response = client.responses.parse(
            model=model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=ThemeAssignments,
        )
    except Exception as e:
        logger.error("Open AI call to classify use cases into taxonomy failed!")
        return

    parsed: ThemeAssignments = response.output_parsed

    # Build lookup {id -> ThemeAssignment}
    theme_by_id = {a.id: a for a in parsed.assignments}

    # Merge themes back into the original records
    for uc in use_cases:
        uc_id = uc.get("id")
        if uc_id in theme_by_id:
            assignment = theme_by_id[uc_id]
            uc["tier_1"] = assignment.tier_1
            uc["tier_2"] = assignment.tier_2

    OUTPUT_FILENAME = "taxonomy.json"
    output_path = ARTIFACTS_PATH / OUTPUT_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(use_cases, f, indent=2, ensure_ascii=False)

    print(f"Mapped {len(theme_by_id)} use cases to innovation themes -> {output_path}")


if __name__ == "__main__":
    main()
