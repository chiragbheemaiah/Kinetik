#!/usr/bin/env python
"""
map_chessboard.py

Maps each use case to a chessboard row (operating unit),
e.g., Infrastructure & Operations, US Personal Banking, etc.

Traceability fields (ppt_source_file, source) are preserved.

Expected env vars:
  OPENAI_API_KEY   - your OpenAI API key (required)
  OPENAI_MODEL     - optional, default "gpt-4o-2024-08-06"
  INPUT_JSON       - optional, default "data/use_cases_with_themes.json"
  OUTPUT_JSON      - optional, default "data/use_cases_with_themes_and_chessboard.json"

LangSmith tracing:
  LANGSMITH_TRACING - "true" to enable tracing
  LANGSMITH_API_KEY - your LangSmith API key
  LANGSMITH_PROJECT - optional project name
"""

import json
import os
from pathlib import Path
from typing import List, Any, Optional
import logging

from openai import OpenAI
from pydantic import BaseModel

from langsmith import traceable
from langsmith.wrappers import wrap_openai

logger = logging.getLogger("map_chessboard")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("\n %(asctime)s | %(levelname)s | %(message)s")

# console handler
ch = logging.StreamHandler()
ch.setFormatter(formatter)

# file handler
fh = logging.FileHandler("map_chessboard.log")
fh.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh)


# Allowed chessboard rows / operating units.
# Extend this list to match your full operating matrix.
CHESSBOARD_ROWS = [
    "Infrastructure & Operations",
    "US Personal Banking (incl. Wealth)",
    "Banking",
    "Regions / Other",
    "Other / Unclear",
]


class ChessboardAssignment(BaseModel):
    """Chessboard mapping for a single use case (LLM output)."""

    id: int
    chessboard_row: str


class ChessboardAssignments(BaseModel):
    assignments: List[ChessboardAssignment]


@traceable(name="BuildChessboardText", metadata={"component": "map_chessboard"})
def build_chessboard_text(rows: List[str]) -> str:
    """Build a textual list of allowed chessboard rows for the prompt."""
    text = "\n".join(f"- {row}" for row in rows)
    logger.debug("Chessboard text built with %d rows.", len(rows))
    return text


@traceable(name="BuildUseCasesText", metadata={"component": "map_chessboard"})
def build_use_cases_text(use_cases: List[dict]) -> str:
    """Flatten use cases into id. title :: description (tier_1, tier_2) lines."""
    use_case_lines: List[str] = []
    for uc in use_cases:
        uc_id = uc.get("id")
        if uc_id is None:
            uc_id = len(use_case_lines) + 1
            uc["id"] = uc_id

        title = uc.get("use_case_title", "")
        desc = uc.get("description", "")
        tier1 = uc.get("tier_1", "")
        tier2 = uc.get("tier_2", "")

        use_case_lines.append(
            f"{uc_id}. {title} :: {desc} (tier_1={tier1}, tier_2={tier2})"
        )

    text = "\n".join(use_case_lines)
    logger.debug("Use cases text built for %d use cases.", len(use_case_lines))
    return text


@traceable(
    run_type="llm",
    name="ClassifyUseCasesToChessboard",
    metadata={"component": "map_chessboard"},
)
def classify_use_cases_with_llm(
    client: Any, model_name: str, system_prompt: str, user_prompt: str
) -> ChessboardAssignments:
    """
    Call the OpenAI Responses API to map use cases to chessboard rows.

    This function is traced as an LLM run in LangSmith. The wrapped
    OpenAI client also emits nested LLM spans for the model call.
    """
    logger.debug("Calling OpenAI model %s for chessboard mapping.", model_name)
    response = client.responses.parse(
        model=model_name,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        reasoning={"effort": "high"},
        text_format=ChessboardAssignments,
    )
    parsed: ChessboardAssignments = response.output_parsed
    logger.debug(
        "Received chessboard assignments for %d use cases.",
        len(parsed.assignments),
    )
    return parsed


@traceable(
    name="MapChessboardPipeline",
    metadata={"component": "map_chessboard", "script": "map_chessboard"},
)
def main() -> None:
    ARTIFACTS_PATH = Path(
        "/home/blitz/Desktop/Kinetik/code/chapter-100-experiments/2. Account Plan Plays/exp/artifacts"
    )
    INPUT_FILENAME = "use_cases.json"
    input_path = ARTIFACTS_PATH / INPUT_FILENAME

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")

    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")
    logger.debug("Loading use cases from %s", input_path)

    with input_path.open("r", encoding="utf-8") as f:
        use_cases = json.load(f)

    # Wrap the OpenAI client with LangSmith so all model calls are traced.
    client = wrap_openai(OpenAI())

    chessboard_text = build_chessboard_text(CHESSBOARD_ROWS)
    use_cases_text = build_use_cases_text(use_cases)

    system_prompt = (
        "You are mapping banking IT use cases onto an account plan chessboard. "
        "Each row corresponds to a high-level operating unit.\n\n"
        "Rules:\n"
        "- For EACH use case, choose exactly ONE chessboard row.\n"
        "- Only use values from the allowed list below.\n"
        "- Base your choice on the use-case title, description, and (if present) "
        "  its innovation theme (tier_1/tier_2).\n"
        "- If it obviously spans several areas, select the primary one. "
        "  If unclear, use 'Other / Unclear'."
    )

    user_prompt = (
        "Allowed chessboard rows (operating-unit rows):\n"
        f"{chessboard_text}\n\n"
        "Use cases to classify (id. title :: description (tier_1, tier_2)):\n"
        f"{use_cases_text}\n\n"
        "Return JSON ONLY in this structure:\n"
        "{\n"
        '  "assignments": [\n'
        '    {"id": int, "chessboard_row": str},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
    )

    try:
        parsed: Optional[ChessboardAssignments] = classify_use_cases_with_llm(
            client=client,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as e:
        logger.error("OpenAI call for chessboarding failed. Error: %s", e)
        return

    if not parsed:
        logger.error("No parsed assignments returned from OpenAI.")
        return

    chessboard_by_id = {a.id: a.chessboard_row for a in parsed.assignments}

    for uc in use_cases:
        uc_id = uc.get("id")
        if uc_id in chessboard_by_id:
            uc["chessboard_row"] = chessboard_by_id[uc_id]

    OUTPUT_FILENAME = "chessboard.json"
    output_path = ARTIFACTS_PATH / OUTPUT_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(use_cases, f, indent=2, ensure_ascii=False)

    logger.debug(
        "Mapped %d use cases to chessboard rows → %s",
        len(chessboard_by_id),
        output_path,
    )
    print(
        f"Mapped {len(chessboard_by_id)} use cases to chessboard rows → {output_path}"
    )


if __name__ == "__main__":
    main()
