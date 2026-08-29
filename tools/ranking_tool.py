from datetime import datetime
from typing import Any


class RankingTool:
    """
    Deterministic supplier ranking tool.

    Ranking order:
        1. Higher PPI
        2. Earlier submission date
        3. Higher historical experience rating
        4. Supplier name ascending

    Ranking is performed entirely in Python.
    No LLM is used.
    """

    # =====================================================
    # Rank suppliers
    # =====================================================

    def rank_suppliers(
        self,
        benchmark_results: list[dict]
    ) -> list[dict]:
        """
        Apply the required deterministic ranking rules
        to benchmarked supplier results.

        Returns suppliers sorted in final ranking order
        with sequential final_rank values.
        """

        if not benchmark_results:

            raise ValueError(
                "No benchmark results available for ranking."
            )

        # -------------------------------------------------
        # Validate ranking inputs
        # -------------------------------------------------

        for supplier in benchmark_results:

            self._validate_supplier(
                supplier
            )

        # -------------------------------------------------
        # Deterministic sort
        #
        # 1. PPI                  DESC
        # 2. Submission date      ASC
        # 3. Experience rating    DESC
        # 4. Supplier name        ASC
        # -------------------------------------------------

        sorted_suppliers = sorted(
            benchmark_results,
            key=lambda supplier: (
                -float(supplier["ppi"]),

                self._parse_submission_date(
                    supplier["submission_date"]
                ),

                -float(
                    supplier["experience_rating"]
                ),

                supplier["supplier_name"]
                .strip()
                .lower()
            )
        )

        # -------------------------------------------------
        # Assign sequential ranks AFTER sorting
        # -------------------------------------------------

        ranked_results = []

        for rank, supplier in enumerate(
            sorted_suppliers,
            start=1
        ):

            ranked_supplier = {
                **supplier,
                "final_rank": rank
            }

            ranked_results.append(
                ranked_supplier
            )

        return ranked_results

    # =====================================================
    # Validate supplier
    # =====================================================

    @staticmethod
    def _validate_supplier(
        supplier: dict
    ) -> None:
        """
        Validate all fields required for ranking.
        """

        required_fields = [
            "supplier_name",
            "ppi",
            "submission_date",
            "experience_rating"
        ]

        missing_fields = [
            field
            for field in required_fields
            if field not in supplier
        ]

        if missing_fields:

            raise ValueError(
                f"Supplier result for "
                f"'{supplier.get('supplier_name', 'Unknown')}' "
                f"is missing required ranking fields: "
                f"{missing_fields}"
            )

        # -------------------------------------------------
        # Validate PPI
        # -------------------------------------------------

        try:

            float(
                supplier["ppi"]
            )

        except (TypeError, ValueError):

            raise ValueError(
                f"Invalid PPI for supplier "
                f"'{supplier['supplier_name']}'."
            )

        # -------------------------------------------------
        # Validate experience rating
        # -------------------------------------------------

        try:

            float(
                supplier["experience_rating"]
            )

        except (TypeError, ValueError):

            raise ValueError(
                f"Invalid experience rating for supplier "
                f"'{supplier['supplier_name']}'."
            )

        # -------------------------------------------------
        # Validate submission date
        # -------------------------------------------------

        RankingTool._parse_submission_date(
            supplier["submission_date"]
        )

    # =====================================================
    # Parse submission date
    # =====================================================

    @staticmethod
    def _parse_submission_date(
        value: Any
    ) -> datetime:
        """
        Convert supported submission date formats into
        datetime objects for deterministic comparison.
        """

        if isinstance(
            value,
            datetime
        ):

            return value

        if value is None:

            raise ValueError(
                "Submission date cannot be None."
            )

        value = str(value).strip()

        supported_formats = [

            "%Y-%m-%d",

            "%Y-%m-%dT%H:%M:%S",

            "%Y-%m-%d %H:%M:%S",

            "%d-%m-%Y",

            "%d/%m/%Y"
        ]

        for date_format in supported_formats:

            try:

                return datetime.strptime(
                    value,
                    date_format
                )

            except ValueError:
                continue

        raise ValueError(
            f"Unsupported submission date format: "
            f"{value}"
        )


# =========================================================
# Convenience function
# =========================================================

def rank_suppliers(
    benchmark_results: list[dict]
) -> list[dict]:
    """
    Convenience wrapper for RankingTool.
    """

    tool = RankingTool()

    return tool.rank_suppliers(
        benchmark_results
    )


# =========================================================
# Standalone test
# =========================================================

if __name__ == "__main__":

    import json

    benchmark_results = [

        {
            "supplier_name": "Apex Systems",
            "absolute_score": 75.0,
            "ppi": 92.5,
            "submission_date": "2026-08-21",
            "experience_rating": 8,

            "criterion_results": []
        },

        {
            "supplier_name": "BrightPath Tech",
            "absolute_score": 70.0,
            "ppi": 92.5,
            "submission_date": "2026-08-22",
            "experience_rating": 7,

            "criterion_results": []
        },

        {
            "supplier_name": "NexaWorks",
            "absolute_score": 81.0,
            "ppi": 96.0,
            "submission_date": "2026-08-23",
            "experience_rating": 9,

            "criterion_results": []
        },

        {
            "supplier_name": "Orbit Digital",
            "absolute_score": 79.0,
            "ppi": 92.5,
            "submission_date": "2026-08-21",
            "experience_rating": 9,

            "criterion_results": []
        }
    ]

    # -----------------------------------------------------
    # Execute ranking
    # -----------------------------------------------------

    ranked_results = rank_suppliers(
        benchmark_results
    )

    # -----------------------------------------------------
    # Display ranking
    # -----------------------------------------------------

    print("\n" + "=" * 80)
    print("FINAL SUPPLIER RANKING")
    print("=" * 80)

    for supplier in ranked_results:

        print(
            f"Rank {supplier['final_rank']}: "
            f"{supplier['supplier_name']} | "
            f"PPI: {supplier['ppi']} | "
            f"Submission: {supplier['submission_date']} | "
            f"Experience: {supplier['experience_rating']}"
        )

    # -----------------------------------------------------
    # Display JSON
    # -----------------------------------------------------

    print("\n" + "=" * 80)
    print("RANKED RESULTS JSON")
    print("=" * 80)

    print(
        json.dumps(
            ranked_results,
            indent=2,
            ensure_ascii=False
        )
    )