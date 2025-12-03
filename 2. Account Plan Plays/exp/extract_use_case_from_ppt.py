#!/usr/bin/env python
"""
extract_use_cases_from_ppt.py

Reads an account plan PowerPoint from the data folder,
calls the OpenAI API to extract use cases, and writes
them to a JSON file suitable for further mapping.

Expected env vars:
  OPENAI_API_KEY   - your OpenAI API key (required)
  OPENAI_MODEL     - optional, default "gpt-4o-2024-08-06"
  DATA_DIR         - optional, default "data"
  ACCOUNT_PLAN_PPT - optional, default "Citigroup FY26 Account Plan Full.pptx"
  OUTPUT_JSON      - optional, default "use_cases_raw.json"
"""

import json
import os
from pathlib import Path
from typing import List
import logging
import lilypad


from openai import OpenAI
from pydantic import BaseModel
from pptx import Presentation

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


lilypad.configure(
    project_id=os.environ["LILYPAD_PROJECT_ID"],
    api_key=os.environ["LILYPAD_API_KEY"],
    auto_llm=True,
)

client = OpenAI()
model_name = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")

class UseCase(BaseModel):
    """Schema for one extracted use case (LLM output)."""
    use_case_title: str
    description: str
    slide_numbers: List[int]


class UseCaseList(BaseModel):
    """Wrapper so we can parse a list of use cases."""
    use_cases: List[UseCase]


def extract_ppt_text(ppt_path: Path) -> str:
    """Flatten PPT text slide-by-slide into a single string."""
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
            slide_chunks.append(f"Slide {i}:\n" + "\n".join(shape_texts))

    return "\n\n".join(slide_chunks)

@lilypad.trace(versioning="automatic") 
def extract_use_cases(system_prompt: str, user_prompt: str):

    logger.debug("Initiating Open AI API call.")
    response = client.responses.parse(
        model=model_name,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        reasoning= {
            "effort": "high"
        },
        text_format=UseCaseList,
    )
    logger.debug("Completed Open AI API call.")
    return response.output_parsed

def main() -> None:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    logger.debug(f"Data Path - {data_dir}")
    ppt_filename = os.getenv(
        "ACCOUNT_PLAN_PPT", "Citigroup FY26 Account Plan Full.pptx"
    )

    ppt_path = data_dir / ppt_filename
    logger.debug(f"PPT Path - {ppt_path}")

    output_json = data_dir / os.getenv("OUTPUT_JSON", "use_cases_raw.json")
    logger.debug(f"Output JSON Path - {output_json}")

    if not ppt_path.exists():
        raise FileNotFoundError(f"Account plan PPT not found: {ppt_path}")

    logger.debug(f"Model Name - {model_name}")

    print(f"Reading PPT from: {ppt_path}")
    ppt_text = extract_ppt_text(ppt_path)
    logger.debug("PPT extraction complete.")

    system_prompt = (
        "You are extracting business and IT 'use cases' from a PowerPoint "
        "account plan for selling mainframe systems software into a large bank.\n\n"
        "Definition of 'use case': a concrete scenario where the bank applies "
        "technology to achieve a specific business or operational outcome.\n"
        "Examples include:\n"
        "- AI-Powered Risk Ops Automation (AML/KYC)\n"
        "- Mainframe Modernization via Broadcom Takeout\n"
        "- CA7/Autosys Replacement with Control-M\n\n"
        "Instructions:\n"
        "- Focus on use cases involving mainframe, automation, AI, observability, "
        "  DevX, security, Control-M / workload automation, data governance, "
        "  regulatory/reporting, and cloud/hybrid modernization.\n"
        "- Group duplicate or near-duplicate ideas into one use case.\n"
        "- Provide concise but specific titles and 1–3 sentence descriptions.\n"
        "- Identify slide numbers where each use case appears or is clearly implied.\n"
        "- DO NOT include generic sales motions (e.g. 'identify champions'); "
        "  only real technology use cases."
    )

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
        f"{ppt_text}"
    )

    parsed: UseCaseList = extract_use_cases(system_prompt, user_prompt)
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

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    logger.debug("Writing completed.")

    print(f"Wrote {len(records)} use cases → {output_json}")


if __name__ == "__main__":
    main()
