import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from tools.document_tool import extract_pdf_text


# =========================================================
# Environment / Configuration
# =========================================================

load_dotenv()

MODEL_NAME = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-4o-mini"
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


if not OPENROUTER_API_KEY:
    raise ValueError(
        "OPENROUTER_API_KEY is not set. "
        "Please add it to your .env file."
    )


# =========================================================
# Evaluation Agent
# =========================================================

class EvaluationAgent:
    """
    LLM-based Evaluation Agent.

    Responsibility:
        - Evaluate one supplier proposal
        - Use active evaluation criteria
        - Assign criterion-level scores
        - Provide justification
        - Provide supporting evidence
        - Identify proposal risks
        - Provide overall summary

    The Evaluation Agent does NOT:
        - Calculate weighted scores
        - Calculate peer benchmarks
        - Calculate criterion gaps
        - Calculate relative performance
        - Calculate PPI
        - Rank suppliers
        - Apply tie-break rules

    Those responsibilities belong to deterministic
    Python components later in the workflow.
    """

    def __init__(self):

        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=1000,
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    # =====================================================
    # Build Prompt
    # =====================================================

    def build_prompt(
        self,
        supplier_name: str,
        criteria: list[dict],
        document_text: str
    ) -> str:
        """
        Build the evaluation prompt dynamically from the
        criteria loaded from SQLite.
        """

        criteria_text = "\n\n".join(
            [
                f"""
Criterion ID: {criterion["criterion_id"]}
Name: {criterion["name"]}
Description: {criterion["description"]}
Weight: {criterion["weight"]}%
Maximum Score: {criterion["max_score"]}
""".strip()
                for criterion in criteria
            ]
        )

        prompt = f"""
You are the Evaluation Agent in an AI-assisted supplier
RFP evaluation system.

Evaluate ONE supplier proposal against the ACTIVE evaluation
criteria provided below.

SUPPLIER
--------
{supplier_name}

ACTIVE EVALUATION CRITERIA
--------------------------
{criteria_text}

SCORING SCALE
-------------
0 = No evidence / completely unresponsive
1-2 = Very weak
3-4 = Below expectations
5-6 = Meets basic expectations
7-8 = Strong
9-10 = Exceptional

EVALUATION RULES
----------------
1. Use ONLY information present in the supplier proposal.
2. Do NOT invent facts or evidence.
3. Return exactly one result for EVERY active criterion.
4. Use the exact criterion_id provided.
5. Score must be between 0 and the criterion's max_score.
6. Evidence must be based on the supplier document.
7. Mention the relevant page where possible.
8. Keep justification concise.
9. Keep evidence concise.
10. Do NOT calculate weighted scores.
11. Do NOT calculate peer benchmarks.
12. Do NOT calculate criterion gaps.
13. Do NOT calculate relative percentages.
14. Do NOT calculate PPI.
15. Do NOT rank suppliers.
16. Return JSON only.

OUTPUT LENGTH
------------
For each criterion:
- justification: maximum 20 words
- evidence: maximum 30 words

Risks:
- Keep each risk concise.

Overall summary:
- Maximum 40 words.

SUPPLIER PROPOSAL
-----------------
{document_text}

REQUIRED JSON FORMAT
--------------------

{{
  "supplier_name": "{supplier_name}",
  "criteria": [
    {{
      "criterion_id": 1,
      "score": 8,
      "max_score": 10,
      "justification": "Brief reason for the score.",
      "evidence": "Specific evidence from the supplier proposal."
    }}
  ],
  "risks": [
    "Brief risk identified from the proposal."
  ],
  "overall_summary": "Brief overall assessment of the supplier proposal."
}}

IMPORTANT:
- Return one object in criteria for EVERY active criterion.
- Do not omit any active criterion.
- Do not add criteria that are not active.
- Do not include markdown.
- Do not include ```json.
- Return ONLY the JSON object.
"""

        return prompt

    # =====================================================
    # Evaluate Supplier
    # =====================================================

    def evaluate(
        self,
        supplier_name: str,
        criteria: list[dict],
        document_text: str
    ) -> dict:
        """
        Evaluate one supplier proposal using the LLM.
        """

        # -------------------------------------------------
        # Build prompt
        # -------------------------------------------------

        prompt = self.build_prompt(
            supplier_name=supplier_name,
            criteria=criteria,
            document_text=document_text
        )

        # -------------------------------------------------
        # Call OpenRouter LLM
        # -------------------------------------------------

        response = self.llm.invoke(prompt)

        # -------------------------------------------------
        # Diagnostic information
        # -------------------------------------------------

        print("\n" + "=" * 80)
        print("MODEL")
        print("=" * 80)
        print(MODEL_NAME)

        print("\n" + "=" * 80)
        print("RESPONSE METADATA")
        print("=" * 80)
        print(response.response_metadata)

        print("\n" + "=" * 80)
        print("USAGE METADATA")
        print("=" * 80)
        print(response.usage_metadata)

        # -------------------------------------------------
        # Extract response content
        # -------------------------------------------------

        raw_content = response.content

        # -------------------------------------------------
        # Handle possible content object
        # -------------------------------------------------

        if not isinstance(raw_content, str):

            raw_content = str(raw_content)

        raw_content = raw_content.strip()

        print("\n" + "=" * 80)
        print("RAW LLM RESPONSE")
        print("=" * 80)
        print(raw_content)
        print("=" * 80)

        # -------------------------------------------------
        # Parse JSON
        # -------------------------------------------------

        try:

            result = json.loads(raw_content)

        except json.JSONDecodeError as exc:

            print("\n" + "=" * 80)
            print("JSON PARSING ERROR")
            print("=" * 80)

            print(f"Error    : {exc}")
            print(f"Position : {exc.pos}")
            print(f"Line     : {exc.lineno}")
            print(f"Column   : {exc.colno}")

            start = max(
                0,
                exc.pos - 300
            )

            end = min(
                len(raw_content),
                exc.pos + 300
            )

            print("\nContent around error:")
            print(raw_content[start:end])

            print("=" * 80)

            raise ValueError(
                "Evaluation Agent returned invalid JSON."
            ) from exc

        # -------------------------------------------------
        # Basic structural checks
        #
        # Full validation belongs to the Validation Tool.
        # -------------------------------------------------

        if not isinstance(result, dict):

            raise ValueError(
                "Evaluation Agent output must be a JSON object."
            )

        if "supplier_name" not in result:

            raise ValueError(
                "Evaluation Agent output is missing "
                "'supplier_name'."
            )

        if "criteria" not in result:

            raise ValueError(
                "Evaluation Agent output is missing "
                "'criteria'."
            )

        if not isinstance(result["criteria"], list):

            raise ValueError(
                "'criteria' must be a list."
            )

        return result


# =========================================================
# Convenience Function
# =========================================================

def evaluate_supplier(
    supplier_name: str,
    criteria: list[dict],
    document_text: str
) -> dict:
    """
    Convenience wrapper for EvaluationAgent.
    """

    agent = EvaluationAgent()

    return agent.evaluate(
        supplier_name=supplier_name,
        criteria=criteria,
        document_text=document_text
    )


# =========================================================
# Standalone Test
# =========================================================

if __name__ == "__main__":

    print("\nStarting Evaluation Agent test...")

    # -----------------------------------------------------
    # Test criteria
    #
    # These mirror the criteria in the project brief.
    # Later these will come directly from SQLite.
    # -----------------------------------------------------

    test_criteria = [

        {
            "criterion_id": 1,
            "name": "Technical Capability",
            "description": (
                "Architecture, integrations, scalability, "
                "technical fit"
            ),
            "weight": 30,
            "max_score": 10
        },

        {
            "criterion_id": 2,
            "name": "Implementation Plan",
            "description": (
                "Timeline, milestones, staffing, risk plan"
            ),
            "weight": 20,
            "max_score": 10
        },

        {
            "criterion_id": 3,
            "name": "Commercial Value",
            "description": (
                "Pricing clarity, total cost, assumptions"
            ),
            "weight": 20,
            "max_score": 10
        },

        {
            "criterion_id": 4,
            "name": "Security & Compliance",
            "description": (
                "Controls, certifications, privacy, auditability"
            ),
            "weight": 20,
            "max_score": 10
        },

        {
            "criterion_id": 5,
            "name": "Support & Experience",
            "description": (
                "Support model, similar projects, references"
            ),
            "weight": 10,
            "max_score": 10
        }
    ]

    # -----------------------------------------------------
    # Test supplier
    # -----------------------------------------------------

    supplier_name = "Apex Systems"

    pdf_path = "rfps/apex_systems.pdf"

    # -----------------------------------------------------
    # Check PDF
    # -----------------------------------------------------

    if not Path(pdf_path).exists():

        raise FileNotFoundError(
            f"Could not find supplier PDF: {pdf_path}"
        )

    # -----------------------------------------------------
    # Extract PDF text using Document Tool
    # -----------------------------------------------------

    print("\nExtracting PDF text...")

    document_text = extract_pdf_text(pdf_path)

    print(
        f"Extracted {len(document_text)} characters."
    )

    # -----------------------------------------------------
    # Run Evaluation Agent
    # -----------------------------------------------------

    print("\nCalling Evaluation Agent...")

    result = evaluate_supplier(
        supplier_name=supplier_name,
        criteria=test_criteria,
        document_text=document_text
    )

    # -----------------------------------------------------
    # Display final parsed result
    # -----------------------------------------------------

    print("\n" + "=" * 80)
    print("PARSED EVALUATION RESULT")
    print("=" * 80)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\nEvaluation Agent test completed.")