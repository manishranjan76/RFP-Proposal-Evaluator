from typing import TypedDict, Any, Optional


class Supplier(TypedDict, total=False):
    """
    Information related to one supplier/RFP submission.
    """

    supplier_id: str
    supplier_name: str
    submission_date: str
    experience_rating: float
    pdf_path: str

    # Generated during the workflow
    extracted_text: str
    llm_result: dict
    validated_result: dict
    warnings: list[str]

    # Calculated by Python
    absolute_score: float
    criterion_results: list[dict]
    ppi: float
    final_rank: int


class RFPState(TypedDict, total=False):
    """
    Shared state passed between LangGraph nodes.
    """

    # -----------------------------------------------------
    # Run information
    # -----------------------------------------------------

    rfp_run_id: str
    created_at: str
    status: str

    # -----------------------------------------------------
    # Evaluation criteria loaded from SQLite
    # -----------------------------------------------------

    criteria: list[dict]

    # -----------------------------------------------------
    # Suppliers being evaluated
    # -----------------------------------------------------

    suppliers: list[Supplier]

    # Index used by the supplier-processing loop
    current_supplier_index: int

    # -----------------------------------------------------
    # Current supplier processing state
    # -----------------------------------------------------

    current_supplier: Optional[Supplier]

    extracted_text: str

    llm_result: dict

    validated_result: dict

    warnings: list[str]

    # -----------------------------------------------------
    # Scoring / benchmarking / ranking
    # -----------------------------------------------------

    supplier_scores: list[dict]

    benchmark_results: dict

    ranked_results: list[dict]

    # -----------------------------------------------------
    # Final result
    # -----------------------------------------------------

    final_results: dict

    # -----------------------------------------------------
    # General workflow messages
    # -----------------------------------------------------

    errors: list[str]