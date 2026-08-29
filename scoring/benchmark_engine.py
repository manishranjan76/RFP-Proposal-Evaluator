from typing import Any


class BenchmarkEngine:
    """
    Deterministic peer benchmarking and PPI engine.

    Responsibilities:
        1. Find the best supplier score for each criterion
        2. Calculate criterion gap
        3. Calculate relative performance %
        4. Calculate weighted Peer Performance Index (PPI)

    Does NOT:
        - Call the LLM
        - Change supplier scores
        - Rank suppliers
        - Apply tie-break rules
    """

    # =====================================================
    # Benchmark suppliers
    # =====================================================

    def calculate_benchmarks(
        self,
        supplier_scores: list[dict],
        active_criteria: list[dict]
    ) -> list[dict]:
        """
        Calculate peer benchmark metrics for every supplier.

        Returns one complete benchmarked result per supplier.
        """

        if not supplier_scores:
            raise ValueError(
                "No supplier scores available for benchmarking."
            )

        if not active_criteria:
            raise ValueError(
                "No active evaluation criteria available."
            )

        # -------------------------------------------------
        # Find best score for every criterion
        # -------------------------------------------------

        best_scores = self._find_best_scores(
            supplier_scores
        )

        # -------------------------------------------------
        # Create criteria lookup
        # -------------------------------------------------

        criteria_lookup = {
            int(c["criterion_id"]): c
            for c in active_criteria
        }

        benchmarked_suppliers = []

        # -------------------------------------------------
        # Process every supplier
        # -------------------------------------------------

        for supplier in supplier_scores:

            supplier_name = supplier[
                "supplier_name"
            ]

            benchmarked_criteria = []

            weighted_relative_sum = 0.0
            total_weight = 0.0

            # ---------------------------------------------
            # Process each criterion
            # ---------------------------------------------

            for criterion_result in supplier.get(
                "criterion_results",
                []
            ):

                criterion_id = int(
                    criterion_result["criterion_id"]
                )

                # Ignore scores for criteria that are no
                # longer part of the active configuration.
                if criterion_id not in criteria_lookup:
                    continue

                criterion_config = criteria_lookup[
                    criterion_id
                ]

                score = float(
                    criterion_result["score"]
                )

                max_score = float(
                    criterion_result["max_score"]
                )

                weight = float(
                    criterion_config["weight"]
                )

                # -----------------------------------------
                # Peer best score
                # -----------------------------------------

                peer_best_score = best_scores[
                    criterion_id
                ]

                # -----------------------------------------
                # Criterion Gap
                #
                # Formula:
                #
                # Supplier Score - Peer Best Score
                #
                # Leader = 0
                # Below leader = negative value
                # -----------------------------------------

                criterion_gap = (
                    score - peer_best_score
                )

                # -----------------------------------------
                # Relative Performance %
                #
                # Formula:
                #
                # Supplier Score
                # ---------------- × 100
                # Peer Best Score
                # -----------------------------------------

                if peer_best_score == 0:

                    # Avoid division by zero.
                    #
                    # If everyone scored zero, everyone is
                    # considered to be performing at 100%
                    # relative to the peer benchmark.

                    if score == 0:
                        relative_percentage = 100.0
                    else:
                        relative_percentage = 0.0

                else:

                    relative_percentage = (
                        score / peer_best_score
                    ) * 100

                # -----------------------------------------
                # Weighted relative performance
                # -----------------------------------------

                weighted_relative = (
                    relative_percentage * weight
                )

                weighted_relative_sum += (
                    weighted_relative
                )

                total_weight += weight

                # -----------------------------------------
                # Store criterion benchmark result
                # -----------------------------------------

                benchmarked_criteria.append(
                    {
                        "criterion_id": criterion_id,

                        "criterion_name": criterion_config[
                            "name"
                        ],

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

                        "peer_best_score": round(
                            peer_best_score,
                            4
                        ),

                        "criterion_gap": round(
                            criterion_gap,
                            4
                        ),

                        "relative_percentage": round(
                            relative_percentage,
                            4
                        ),

                        "weighted_relative": round(
                            weighted_relative,
                            4
                        ),

                        "justification": criterion_result.get(
                            "justification",
                            ""
                        ),

                        "evidence": criterion_result.get(
                            "evidence",
                            ""
                        )
                    }
                )

            # ---------------------------------------------
            # Calculate PPI
            #
            # Weighted average of relative performance
            # across active criteria.
            # ---------------------------------------------

            if total_weight == 0:

                ppi = 0.0

            else:

                ppi = (
                    weighted_relative_sum
                    / total_weight
                )

            # ---------------------------------------------
            # Build complete supplier benchmark result
            # ---------------------------------------------

            benchmarked_supplier = {
                "supplier_name": supplier_name,

                "absolute_score": supplier.get(
                    "absolute_score",
                    0
                ),

                "criterion_results": benchmarked_criteria,

                "ppi": round(
                    ppi,
                    4
                )
            }

            # ---------------------------------------------
            # Preserve supplier metadata
            # ---------------------------------------------

            if "submission_date" in supplier:

                benchmarked_supplier[
                    "submission_date"
                ] = supplier[
                    "submission_date"
                ]

            if "experience_rating" in supplier:

                benchmarked_supplier[
                    "experience_rating"
                ] = supplier[
                    "experience_rating"
                ]

            benchmarked_suppliers.append(
                benchmarked_supplier
            )

        return benchmarked_suppliers

    # =====================================================
    # Find best score per criterion
    # =====================================================

    @staticmethod
    def _find_best_scores(
        supplier_scores: list[dict]
    ) -> dict[int, float]:
        """
        Find the highest supplier score for each criterion.
        """

        best_scores = {}

        for supplier in supplier_scores:

            for criterion in supplier.get(
                "criterion_results",
                []
            ):

                criterion_id = int(
                    criterion["criterion_id"]
                )

                score = float(
                    criterion["score"]
                )

                if criterion_id not in best_scores:

                    best_scores[criterion_id] = score

                else:

                    best_scores[criterion_id] = max(
                        best_scores[criterion_id],
                        score
                    )

        return best_scores


# =========================================================
# Convenience Function
# =========================================================

def calculate_peer_benchmarks(
    supplier_scores: list[dict],
    active_criteria: list[dict]
) -> list[dict]:
    """
    Convenience wrapper around BenchmarkEngine.
    """

    engine = BenchmarkEngine()

    return engine.calculate_benchmarks(
        supplier_scores=supplier_scores,
        active_criteria=active_criteria
    )


# =========================================================
# Standalone Test
# =========================================================

if __name__ == "__main__":

    import json

    active_criteria = [

        {
            "criterion_id": 1,
            "name": "Technical Capability",
            "description": "Architecture and technical fit",
            "weight": 30,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 2,
            "name": "Implementation Plan",
            "description": "Timeline and delivery approach",
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 3,
            "name": "Commercial Value",
            "description": "Pricing and commercial assumptions",
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 4,
            "name": "Security & Compliance",
            "description": "Security and compliance controls",
            "weight": 20,
            "max_score": 10,
            "is_active": 1
        },

        {
            "criterion_id": 5,
            "name": "Support & Experience",
            "description": "Support and relevant experience",
            "weight": 10,
            "max_score": 10,
            "is_active": 1
        }
    ]

    supplier_scores = [

        {
            "supplier_name": "Apex Systems",
            "absolute_score": 75.0,

            "criterion_results": [
                {
                    "criterion_id": 1,
                    "score": 8,
                    "max_score": 10,
                    "weight": 30,
                    "weighted_contribution": 24
                },
                {
                    "criterion_id": 2,
                    "score": 7,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 14
                },
                {
                    "criterion_id": 3,
                    "score": 6,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 12
                },
                {
                    "criterion_id": 4,
                    "score": 9,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 18
                },
                {
                    "criterion_id": 5,
                    "score": 7,
                    "max_score": 10,
                    "weight": 10,
                    "weighted_contribution": 7
                }
            ]
        },

        {
            "supplier_name": "BrightPath Tech",
            "absolute_score": 70.0,

            "criterion_results": [
                {
                    "criterion_id": 1,
                    "score": 6,
                    "max_score": 10,
                    "weight": 30,
                    "weighted_contribution": 18
                },
                {
                    "criterion_id": 2,
                    "score": 9,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 18
                },
                {
                    "criterion_id": 3,
                    "score": 9,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 18
                },
                {
                    "criterion_id": 4,
                    "score": 6,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 12
                },
                {
                    "criterion_id": 5,
                    "score": 4,
                    "max_score": 10,
                    "weight": 10,
                    "weighted_contribution": 4
                }
            ]
        },

        {
            "supplier_name": "NexaWorks",
            "absolute_score": 81.0,

            "criterion_results": [
                {
                    "criterion_id": 1,
                    "score": 9,
                    "max_score": 10,
                    "weight": 30,
                    "weighted_contribution": 27
                },
                {
                    "criterion_id": 2,
                    "score": 7,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 14
                },
                {
                    "criterion_id": 3,
                    "score": 5,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 10
                },
                {
                    "criterion_id": 4,
                    "score": 10,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 20
                },
                {
                    "criterion_id": 5,
                    "score": 10,
                    "max_score": 10,
                    "weight": 10,
                    "weighted_contribution": 10
                }
            ]
        },

        {
            "supplier_name": "Orbit Digital",
            "absolute_score": 79.0,

            "criterion_results": [
                {
                    "criterion_id": 1,
                    "score": 8,
                    "max_score": 10,
                    "weight": 30,
                    "weighted_contribution": 24
                },
                {
                    "criterion_id": 2,
                    "score": 8,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 16
                },
                {
                    "criterion_id": 3,
                    "score": 8,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 16
                },
                {
                    "criterion_id": 4,
                    "score": 8,
                    "max_score": 10,
                    "weight": 20,
                    "weighted_contribution": 16
                },
                {
                    "criterion_id": 5,
                    "score": 7,
                    "max_score": 10,
                    "weight": 10,
                    "weighted_contribution": 7
                }
            ]
        }
    ]

    results = calculate_peer_benchmarks(
        supplier_scores=supplier_scores,
        active_criteria=active_criteria
    )

    print("\n" + "=" * 80)
    print("BENCHMARK + PPI RESULTS")
    print("=" * 80)

    print(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        )
    )