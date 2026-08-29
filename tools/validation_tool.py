import json
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


# =========================================================
# Pydantic Models
# =========================================================

class CriterionEvaluation(BaseModel):
    """
    Validated representation of one criterion evaluation.
    """

    model_config = ConfigDict(extra="ignore")

    criterion_id: int
    score: float
    max_score: float
    justification: str = ""
    evidence: str = ""


class EvaluationResult(BaseModel):
    """
    Validated representation of the complete LLM response.
    """

    model_config = ConfigDict(extra="ignore")

    supplier_name: str
    criteria: list[CriterionEvaluation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    overall_summary: str = ""


# =========================================================
# Validation Tool
# =========================================================

class ValidationTool:
    """
    Validates and normalizes Evaluation Agent output.

    Responsibilities:
        - Validate JSON structure
        - Check active criteria
        - Detect missing criteria
        - Detect duplicate criteria
        - Normalize score values
        - Handle out-of-range scores
        - Fill missing criterion results
        - Record warnings

    This tool does NOT:
        - Calculate weighted scores
        - Calculate benchmarks
        - Calculate PPI
        - Rank suppliers
    """

    def validate(
        self,
        llm_result: dict,
        active_criteria: list[dict]
    ) -> tuple[dict, list[str]]:

        warnings = []

        # -------------------------------------------------
        # 1. Basic input validation
        # -------------------------------------------------

        if not isinstance(llm_result, dict):
            raise ValueError(
                "LLM result must be a JSON object."
            )

        if not isinstance(active_criteria, list):
            raise ValueError(
                "Active criteria must be a list."
            )

        if not active_criteria:
            raise ValueError(
                "No active evaluation criteria supplied."
            )

        # -------------------------------------------------
        # 2. Supplier name
        # -------------------------------------------------

        supplier_name = llm_result.get(
            "supplier_name",
            ""
        )

        if not isinstance(supplier_name, str):
            supplier_name = str(supplier_name)

            warnings.append(
                "Supplier name was converted to string."
            )

        supplier_name = supplier_name.strip()

        if not supplier_name:
            warnings.append(
                "Supplier name was missing."
            )

            supplier_name = "Unknown Supplier"

        # -------------------------------------------------
        # 3. Get LLM criterion results
        # -------------------------------------------------

        raw_criteria = llm_result.get(
            "criteria",
            []
        )

        if raw_criteria is None:
            raw_criteria = []

            warnings.append(
                "Criteria field was missing or null; "
                "treated as empty."
            )

        if not isinstance(raw_criteria, list):

            warnings.append(
                "Criteria field was not a list; "
                "treated as empty."
            )

            raw_criteria = []

        # -------------------------------------------------
        # 4. Build active criteria lookup
        # -------------------------------------------------

        criteria_lookup = {}

        for criterion in active_criteria:

            criterion_id = int(
                criterion["criterion_id"]
            )

            criteria_lookup[criterion_id] = criterion

        # -------------------------------------------------
        # 5. Process LLM criteria
        # -------------------------------------------------

        validated_criteria = {}

        for item in raw_criteria:

            # ---------------------------------------------
            # Make sure item is an object
            # ---------------------------------------------

            if not isinstance(item, dict):

                warnings.append(
                    "Ignored malformed criterion result "
                    "because it was not an object."
                )

                continue

            # ---------------------------------------------
            # Get criterion ID
            # ---------------------------------------------

            raw_id = item.get("criterion_id")

            try:

                criterion_id = int(raw_id)

            except (TypeError, ValueError):

                warnings.append(
                    f"Ignored criterion with invalid "
                    f"criterion_id: {raw_id}"
                )

                continue

            # ---------------------------------------------
            # Check whether criterion is active
            # ---------------------------------------------

            if criterion_id not in criteria_lookup:

                warnings.append(
                    f"Criterion {criterion_id} is not an "
                    f"active criterion and was ignored."
                )

                continue

            # ---------------------------------------------
            # Detect duplicate
            # ---------------------------------------------

            if criterion_id in validated_criteria:

                warnings.append(
                    f"Duplicate result for criterion "
                    f"{criterion_id}; first valid result "
                    f"was retained."
                )

                continue

            criterion_config = criteria_lookup[
                criterion_id
            ]

            max_score = float(
                criterion_config["max_score"]
            )

            # ---------------------------------------------
            # Score normalization
            # ---------------------------------------------

            raw_score = item.get("score")

            score = self._normalize_score(
                raw_score,
                max_score,
                criterion_id,
                warnings
            )

            # ---------------------------------------------
            # max_score
            #
            # Always trust the database configuration,
            # not the LLM.
            # ---------------------------------------------

            llm_max_score = item.get(
                "max_score"
            )

            if llm_max_score is not None:

                try:

                    llm_max_score = float(
                        llm_max_score
                    )

                    if llm_max_score != max_score:

                        warnings.append(
                            f"Criterion {criterion_id}: "
                            f"LLM max_score "
                            f"{llm_max_score} did not match "
                            f"database max_score "
                            f"{max_score}; database value "
                            f"was used."
                        )

                except (TypeError, ValueError):

                    warnings.append(
                        f"Criterion {criterion_id}: invalid "
                        f"LLM max_score; database value "
                        f"was used."
                    )

            # ---------------------------------------------
            # Justification
            # ---------------------------------------------

            justification = item.get(
                "justification",
                ""
            )

            if justification is None:
                justification = ""

                warnings.append(
                    f"Criterion {criterion_id}: "
                    f"missing justification."
                )

            elif not isinstance(justification, str):

                justification = str(
                    justification
                )

                warnings.append(
                    f"Criterion {criterion_id}: "
                    f"justification converted to string."
                )

            # ---------------------------------------------
            # Evidence
            # ---------------------------------------------

            evidence = item.get(
                "evidence",
                ""
            )

            if evidence is None:
                evidence = ""

                warnings.append(
                    f"Criterion {criterion_id}: "
                    f"missing evidence."
                )

            elif not isinstance(evidence, str):

                evidence = str(evidence)

                warnings.append(
                    f"Criterion {criterion_id}: "
                    f"evidence converted to string."
                )

            # ---------------------------------------------
            # Create validated criterion
            # ---------------------------------------------

            validated_criteria[criterion_id] = {
                "criterion_id": criterion_id,
                "score": score,
                "max_score": max_score,
                "justification": justification.strip(),
                "evidence": evidence.strip()
            }

        # -------------------------------------------------
        # 6. Fill missing active criteria
        # -------------------------------------------------

        for criterion_id, criterion_config in criteria_lookup.items():

            if criterion_id not in validated_criteria:

                max_score = float(
                    criterion_config["max_score"]
                )

                validated_criteria[criterion_id] = {
                    "criterion_id": criterion_id,
                    "score": 0.0,
                    "max_score": max_score,
                    "justification": (
                        "No valid evaluation was returned "
                        "for this criterion."
                    ),
                    "evidence": ""
                }

                warnings.append(
                    f"Criterion {criterion_id} was missing "
                    f"from LLM output; score set to 0."
                )

        # -------------------------------------------------
        # 7. Sort criteria according to active criteria
        # -------------------------------------------------

        ordered_criteria = []

        for criterion in active_criteria:

            criterion_id = int(
                criterion["criterion_id"]
            )

            ordered_criteria.append(
                validated_criteria[criterion_id]
            )

        # -------------------------------------------------
        # 8. Validate risks
        # -------------------------------------------------

        risks = llm_result.get(
            "risks",
            []
        )

        if risks is None:
            risks = []

        if not isinstance(risks, list):

            warnings.append(
                "Risks field was not a list; "
                "converted to a single-item list."
            )

            risks = [str(risks)]

        clean_risks = []

        for risk in risks:

            if risk is None:
                continue

            if not isinstance(risk, str):
                risk = str(risk)

            risk = risk.strip()

            if risk:
                clean_risks.append(risk)

        # -------------------------------------------------
        # 9. Overall summary
        # -------------------------------------------------

        overall_summary = llm_result.get(
            "overall_summary",
            ""
        )

        if overall_summary is None:
            overall_summary = ""

        if not isinstance(overall_summary, str):

            overall_summary = str(
                overall_summary
            )

            warnings.append(
                "Overall summary was converted "
                "to string."
            )

        # -------------------------------------------------
        # 10. Create final validated object
        # -------------------------------------------------

        validated_result = {
            "supplier_name": supplier_name,
            "criteria": ordered_criteria,
            "risks": clean_risks,
            "overall_summary": overall_summary.strip()
        }

        # -------------------------------------------------
        # 11. Pydantic schema validation
        # -------------------------------------------------

        try:

            validated_model = EvaluationResult.model_validate(
                validated_result
            )

        except Exception as exc:

            raise ValueError(
                f"Validation failed after normalization: {exc}"
            ) from exc

        # -------------------------------------------------
        # 12. Return JSON-compatible dictionary
        # -------------------------------------------------

        return (
            validated_model.model_dump(),
            warnings
        )

    # =====================================================
    # Score normalization helper
    # =====================================================

    @staticmethod
    def _normalize_score(
        raw_score: Any,
        max_score: float,
        criterion_id: int,
        warnings: list[str]
    ) -> float:
        """
        Convert malformed scores to numeric values and
        clip values outside the permitted range.
        """

        # -------------------------------------------------
        # Missing score
        # -------------------------------------------------

        if raw_score is None:

            warnings.append(
                f"Criterion {criterion_id}: "
                f"missing score; score set to 0."
            )

            return 0.0

        # -------------------------------------------------
        # Convert to float
        # -------------------------------------------------

        try:

            score = float(raw_score)

        except (TypeError, ValueError):

            warnings.append(
                f"Criterion {criterion_id}: invalid score "
                f"'{raw_score}'; score set to 0."
            )

            return 0.0

        # -------------------------------------------------
        # Handle NaN / infinity
        # -------------------------------------------------

        if score != score:

            warnings.append(
                f"Criterion {criterion_id}: score was NaN; "
                f"score set to 0."
            )

            return 0.0

        if score == float("inf") or score == float("-inf"):

            warnings.append(
                f"Criterion {criterion_id}: score was "
                f"infinite; score set to 0."
            )

            return 0.0

        # -------------------------------------------------
        # Clip below zero
        # -------------------------------------------------

        if score < 0:

            warnings.append(
                f"Criterion {criterion_id}: score {score} "
                f"was below 0; clipped to 0."
            )

            score = 0.0

        # -------------------------------------------------
        # Clip above maximum
        # -------------------------------------------------

        if score > max_score:

            warnings.append(
                f"Criterion {criterion_id}: score {score} "
                f"exceeded maximum {max_score}; "
                f"clipped to {max_score}."
            )

            score = max_score

        return score


# =========================================================
# Convenience Function
# =========================================================

def validate_evaluation(
    llm_result: dict,
    active_criteria: list[dict]
) -> tuple[dict, list[str]]:
    """
    Convenience wrapper for ValidationTool.
    """

    validator = ValidationTool()

    return validator.validate(
        llm_result=llm_result,
        active_criteria=active_criteria
    )


# =========================================================
# Standalone Test
# =========================================================

if __name__ == "__main__":

    # -----------------------------------------------------
    # Active criteria
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
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 2,
            "name": "Implementation Plan",
            "description": (
                "Timeline, milestones, staffing, risk plan"
            ),
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 3,
            "name": "Commercial Value",
            "description": (
                "Pricing clarity, total cost, assumptions"
            ),
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 4,
            "name": "Security & Compliance",
            "description": (
                "Controls, certifications, privacy, "
                "auditability"
            ),
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 5,
            "name": "Support & Experience",
            "description": (
                "Support model, similar projects, references"
            ),
            "weight": 10,
            "max_score": 10,
            "is_active": 1
        }
    ]

    # -----------------------------------------------------
    # Deliberately malformed LLM response
    #
    # This demonstrates the validation/error case required
    # by the project brief.
    # -----------------------------------------------------

    bad_llm_result = {
        "supplier_name": "Apex Systems",

        "criteria": [

            # Valid
            {
                "criterion_id": 1,
                "score": 8,
                "max_score": 10,
                "justification": "Strong architecture.",
                "evidence": "Page 1."
            },

            # Score above maximum
            {
                "criterion_id": 2,
                "score": 15,
                "max_score": 10,
                "justification": "Strong implementation.",
                "evidence": "Page 2."
            },

            # Score as string
            {
                "criterion_id": 3,
                "score": "7",
                "max_score": 10,
                "justification": "Clear pricing.",
                "evidence": "Page 3."
            },

            # Criterion 4 deliberately missing

            # Duplicate criterion
            {
                "criterion_id": 3,
                "score": 9,
                "max_score": 10,
                "justification": "Duplicate.",
                "evidence": "Duplicate."
            },

            # Invalid criterion
            {
                "criterion_id": 99,
                "score": 8,
                "max_score": 10,
                "justification": "Invalid criterion.",
                "evidence": "Unknown."
            }
        ],

        "risks": [
            "Higher price"
        ],

        "overall_summary": "Strong proposal."
    }

    # -----------------------------------------------------
    # Run validation
    # -----------------------------------------------------

    validated_result, warnings = validate_evaluation(
        llm_result=bad_llm_result,
        active_criteria=test_criteria
    )

    # -----------------------------------------------------
    # Display results
    # -----------------------------------------------------

    print("\n" + "=" * 80)
    print("VALIDATED RESULT")
    print("=" * 80)

    print(
        json.dumps(
            validated_result,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n" + "=" * 80)
    print("VALIDATION WARNINGS")
    print("=" * 80)

    if warnings:

        for number, warning in enumerate(
            warnings,
            start=1
        ):
            print(f"{number}. {warning}")

    else:

        print("No validation warnings.")

    print("\nValidation test completed.")