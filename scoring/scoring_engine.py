from typing import Any


class ScoringEngine:
    """
    Deterministic scoring engine for supplier RFP evaluation.

    Responsibilities:
        1. Calculate absolute weighted score
        2. Calculate criterion-level weighted contribution

    Does NOT:
        - Ask the LLM for scores
        - Modify LLM evidence
        - Perform peer benchmarking
        - Calculate PPI
        - Rank suppliers
    """

    # =====================================================
    # Calculate one supplier's absolute weighted score
    # =====================================================

    def calculate_absolute_score(
        self,
        validated_result: dict,
        active_criteria: list[dict]
    ) -> dict:
        """
        Calculate the supplier's absolute weighted score.

        Formula:

        Criterion Contribution =
            (Score / Max Score) × Criterion Weight

        Absolute Score =
            Sum of all criterion contributions

        Since criterion weights total 100%, the final
        absolute score is on a 0-100 scale.
        """

        supplier_name = validated_result.get(
            "supplier_name",
            "Unknown Supplier"
        )

        criterion_results = []

        total_score = 0.0

        # -------------------------------------------------
        # Create criteria lookup
        # -------------------------------------------------

        criteria_lookup = {
            int(c["criterion_id"]): c
            for c in active_criteria
        }

        # -------------------------------------------------
        # Process each validated criterion
        # -------------------------------------------------

        for criterion in validated_result.get(
            "criteria",
            []
        ):

            criterion_id = int(
                criterion["criterion_id"]
            )

            # ---------------------------------------------
            # Make sure criterion exists in configuration
            # ---------------------------------------------

            if criterion_id not in criteria_lookup:

                continue

            config = criteria_lookup[criterion_id]

            score = float(
                criterion["score"]
            )

            max_score = float(
                config["max_score"]
            )

            weight = float(
                config["weight"]
            )

            # ---------------------------------------------
            # Weighted contribution
            # ---------------------------------------------

            contribution = (
                score / max_score
            ) * weight

            total_score += contribution

            criterion_results.append(
                {
                    "criterion_id": criterion_id,

                    "criterion_name": config["name"],

                    "score": round(
                        score,
                        4
                    ),

                    "max_score": round(
                        max_score,
                        4
                    ),

                    "weight": round(
                        weight,
                        4
                    ),

                    "weighted_contribution": round(
                        contribution,
                        4
                    ),

                    "justification": criterion.get(
                        "justification",
                        ""
                    ),

                    "evidence": criterion.get(
                        "evidence",
                        ""
                    )
                }
            )

        # -------------------------------------------------
        # Return scorecard
        # -------------------------------------------------

        return {
            "supplier_name": supplier_name,

            "absolute_score": round(
                total_score,
                4
            ),

            "criterion_results": criterion_results
        }


# =========================================================
# Convenience Function
# =========================================================

def calculate_supplier_score(
    validated_result: dict,
    active_criteria: list[dict]
) -> dict:
    """
    Convenience wrapper around ScoringEngine.
    """

    engine = ScoringEngine()

    return engine.calculate_absolute_score(
        validated_result=validated_result,
        active_criteria=active_criteria
    )


# =========================================================
# Standalone Test
# =========================================================

if __name__ == "__main__":

    import json

    # -----------------------------------------------------
    # Active criteria
    # -----------------------------------------------------

    active_criteria = [

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
    # Example validated LLM result
    # -----------------------------------------------------

    validated_result = {

        "supplier_name": "Apex Systems",

        "criteria": [

            {
                "criterion_id": 1,
                "score": 8,
                "max_score": 10,
                "justification": (
                    "Strong technical architecture."
                ),
                "evidence": (
                    "Modular cloud architecture."
                )
            },

            {
                "criterion_id": 2,
                "score": 7,
                "max_score": 10,
                "justification": (
                    "Well structured implementation."
                ),
                "evidence": (
                    "Five phased delivery plan."
                )
            },

            {
                "criterion_id": 3,
                "score": 6,
                "max_score": 10,
                "justification": (
                    "Clear pricing breakdown."
                ),
                "evidence": (
                    "Detailed cost table."
                )
            },

            {
                "criterion_id": 4,
                "score": 9,
                "max_score": 10,
                "justification": (
                    "Strong security controls."
                ),
                "evidence": (
                    "RBAC, encryption and audit logging."
                )
            },

            {
                "criterion_id": 5,
                "score": 7,
                "max_score": 10,
                "justification": (
                    "Good support model."
                ),
                "evidence": (
                    "Named service manager and support model."
                )
            }
        ],

        "risks": [
            "Higher proposed cost."
        ],

        "overall_summary": (
            "Technically strong proposal."
        )
    }

    # -----------------------------------------------------
    # Calculate
    # -----------------------------------------------------

    result = calculate_supplier_score(
        validated_result=validated_result,
        active_criteria=active_criteria
    )

    # -----------------------------------------------------
    # Display
    # -----------------------------------------------------

    print("\n" + "=" * 80)
    print("SCORING RESULT")
    print("=" * 80)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )