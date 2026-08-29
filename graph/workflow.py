from typing import Literal
from langgraph.graph import StateGraph, START, END
from graph.state import RFPState

from tools.document_tool import extract_pdf_text, DocumentExtractionError
from agents.evaluation_agent import evaluate_supplier
from tools.validation_tool import validate_evaluation
from tools.ranking_tool import rank_suppliers

from scoring.scoring_engine import calculate_supplier_score
from scoring.benchmark_engine import calculate_peer_benchmarks

from database.database import (create_rfp_run, save_supplier_result,  update_rfp_run_status)


import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "rfp_evaluation.db"

# =========================================================
# 1. Pre-Setup Integrate with SQLite
# =========================================================


def load_active_criteria() -> list[dict]:
    """
    Load the latest active evaluation criteria from SQLite.
    """

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                criterion_id,
                name,
                description,
                weight,
                max_score,
                is_active
            FROM evaluation_criteria
            WHERE is_active = 1
            ORDER BY criterion_id
            """
        )

        rows = cursor.fetchall()

        criteria = [
            dict(row)
            for row in rows
        ]

        if not criteria:
            raise ValueError(
                "No active evaluation criteria found."
            )

        total_weight = sum(
            float(c["weight"])
            for c in criteria
        )

        if abs(total_weight - 100.0) > 0.0001:
            raise ValueError(
                f"Active criterion weights must total "
                f"100%. Current total: {total_weight}%"
            )

        return criteria

    finally:
        connection.close()


# =========================================================
# 1. SETUP
# =========================================================

def setup_node(state: RFPState) -> dict:
    """
    Setup stage. 
    Load the latest active evaluation criteria from SQLite.

    """

    print("[SETUP] Loading active criteria from SQLite...")
    criteria = load_active_criteria()

    print(
        f"[SETUP] Loaded {len(criteria)} active criteria."
    )

    return {
        "criteria": criteria,
        "status": "SETUP_COMPLETE"
    }


# =========================================================
# 2. INPUT
# =========================================================

def input_node(state: RFPState) -> dict:
    """
    Input stage.

    Streamlit will eventually provide:
    - Supplier PDFs
    - Supplier name
    - Submission date
    - Historical experience rating
    """

    print("[INPUT] Supplier inputs received...")

    return {
        "status": "INPUT_COMPLETE"
    }


# =========================================================
# 3. BATCH
# =========================================================

def batch_node(state: RFPState) -> dict:
    """
    Batch stage.

    Creates one RFP_RUN_ID for the entire supplier batch,
    creates a permanent run-specific folder, and moves/copies
    uploaded supplier PDFs into that folder.

    The supplier pdf_path values are then updated so that
    the downstream Document Tool reads from the permanent
    run-specific location.
    """

    print("[BATCH] Creating RFP batch...")

    # -----------------------------------------------------
    # Create RFP_RUN_ID
    # -----------------------------------------------------

    rfp_run_id = create_rfp_run(
        status="IN_PROGRESS"
    )

    print(
        f"[BATCH] RFP_RUN_ID: {rfp_run_id}"
    )

    # -----------------------------------------------------
    # Create run-specific PDF folder
    # -----------------------------------------------------

    run_folder = (
        BASE_DIR
        / "rfps"
        / rfp_run_id
    )

    run_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        f"[BATCH] PDF folder: {run_folder}"
    )

    # -----------------------------------------------------
    # Get suppliers supplied by Streamlit / test run
    # -----------------------------------------------------

    suppliers = state.get(
        "suppliers",
        []
    )

    if not suppliers:

        return {
            "rfp_run_id": rfp_run_id,
            "current_supplier_index": 0,
            "supplier_scores": [],
            "benchmark_results": {},
            "ranked_results": [],
            "warnings": [],
            "errors": [
                "No suppliers were provided for the RFP batch."
            ],
            "status": "BATCH_FAILED"
        }

    # -----------------------------------------------------
    # Copy PDFs into permanent run folder
    # -----------------------------------------------------

    updated_suppliers = []
    batch_errors = []

    for supplier in suppliers:

        source_path = Path(
            supplier["pdf_path"]
        )

        # -------------------------------------------------
        # Check source PDF
        # -------------------------------------------------

        if not source_path.is_absolute():

            source_path = (
                BASE_DIR / source_path
            )

        if not source_path.exists():

            batch_errors.append(
                f"{supplier['supplier_name']}: "
                f"PDF not found: {source_path}"
            )

            continue

        # -------------------------------------------------
        # Destination
        # -------------------------------------------------

        destination_path = (
            run_folder / source_path.name
        )

        try:

            # copy rather than move
            # so original uploaded/test PDFs remain available

            import shutil

            shutil.copy2(
                source_path,
                destination_path
            )

        except Exception as exc:

            batch_errors.append(
                f"{supplier['supplier_name']}: "
                f"Could not copy PDF: {str(exc)}"
            )

            continue

        # -------------------------------------------------
        # Update supplier path
        # -------------------------------------------------

        updated_supplier = {
            **supplier,
            "pdf_path": str(
                destination_path
            )
        }

        updated_suppliers.append(
            updated_supplier
        )

        print(
            f"[BATCH] "
            f"{supplier['supplier_name']} → "
            f"{destination_path}"
        )

    # -----------------------------------------------------
    # Make sure all suppliers were processed
    # -----------------------------------------------------

    if batch_errors:

        print(
            "[BATCH] Errors encountered:"
        )

        for error in batch_errors:
            print(
                f"[BATCH] ERROR: {error}"
            )

    if not updated_suppliers:

        try:

            update_rfp_run_status(
                rfp_run_id=rfp_run_id,
                status="FAILED"
            )

        except Exception:
            pass

        return {
            "rfp_run_id": rfp_run_id,
            "current_supplier_index": 0,
            "supplier_scores": [],
            "benchmark_results": {},
            "ranked_results": [],
            "warnings": [],
            "errors": batch_errors or [
                "No supplier PDFs could be prepared."
            ],
            "status": "BATCH_FAILED"
        }

    # -----------------------------------------------------
    # Return updated state
    # -----------------------------------------------------

    return {
        "rfp_run_id": rfp_run_id,
        "suppliers": updated_suppliers,
        "current_supplier_index": 0,
        "supplier_scores": [],
        "benchmark_results": {},
        "ranked_results": [],
        "warnings": [],
        "errors": batch_errors,
        "status": "BATCH_CREATED"
    }


# =========================================================
# 4. EVALUATE
# =========================================================

def evaluate_node(state: RFPState) -> dict:
    """
    Evaluate the current supplier.

    Flow:

    1. Get current supplier
    2. Extract PDF using Document Tool
    3. Reload active criteria from SQLite
    4. Call Evaluation Agent
    5. Store raw LLM result in state
    """

    suppliers = state.get("suppliers", [])

    current_index = state.get(
        "current_supplier_index",
        0
    )

    # -----------------------------------------------------
    # Check suppliers
    # -----------------------------------------------------

    if not suppliers:
        return {
            "errors": state.get("errors", []) + [
                "No suppliers available."
            ],
            "status": "EVALUATION_FAILED"
        }

    # -----------------------------------------------------
    # Check index
    # -----------------------------------------------------

    if current_index >= len(suppliers):

        return {
            "status": "ALL_SUPPLIERS_PROCESSED"
        }

    # -----------------------------------------------------
    # Current supplier
    # -----------------------------------------------------

    supplier = suppliers[current_index]

    supplier_name = supplier["supplier_name"]
    pdf_path = supplier["pdf_path"]

    print(
        f"\n[EVALUATE] "
        f"Supplier: {supplier_name}"
    )

    # -----------------------------------------------------
    # Reload latest criteria
    # -----------------------------------------------------

    criteria = load_active_criteria()

    # -----------------------------------------------------
    # Extract PDF
    # -----------------------------------------------------

    print(
        f"[DOCUMENT TOOL] "
        f"Extracting: {pdf_path}"
    )

    try:

        document_text = extract_pdf_text(
            pdf_path
        )

    except DocumentExtractionError as exc:

        return {
            "errors": state.get("errors", []) + [
                f"{supplier_name}: {str(exc)}"
            ],
            "status": "DOCUMENT_EXTRACTION_FAILED"
        }

    print(
        f"[DOCUMENT TOOL] "
        f"Extracted {len(document_text)} characters."
    )

    # -----------------------------------------------------
    # Call Evaluation Agent
    # -----------------------------------------------------

    print(
        f"[EVALUATION AGENT] "
        f"Evaluating {supplier_name}..."
    )

    try:

        llm_result = evaluate_supplier(
            supplier_name=supplier_name,
            criteria=criteria,
            document_text=document_text
        )

    except Exception as exc:

        return {
            "errors": state.get("errors", []) + [
                f"{supplier_name}: "
                f"Evaluation Agent failed: {str(exc)}"
            ],
            "status": "EVALUATION_FAILED"
        }

    print(
        f"[EVALUATION AGENT] "
        f"Completed {supplier_name}."
    )

    # -----------------------------------------------------
    # Update current supplier with extracted text
    # -----------------------------------------------------

    updated_supplier = {
        **supplier,
        "extracted_text": document_text
    }

    return {
        "criteria": criteria,
        "current_supplier": updated_supplier,
        "extracted_text": document_text,
        "llm_result": llm_result,
        "status": "EVALUATION_COMPLETE"
    }


# =========================================================
# 5. VALIDATE
# =========================================================

def validate_node(state: RFPState) -> dict:
    """
    Validate and normalize the Evaluation Agent output.
    """

    print("[VALIDATE] Validating LLM result...")

    llm_result = state.get(
        "llm_result"
    )

    criteria = state.get(
        "criteria"
    )

    if not llm_result:

        return {
            "errors": state.get("errors", []) + [
                "No LLM result available for validation."
            ],
            "status": "VALIDATION_FAILED"
        }

    if not criteria:

        return {
            "errors": state.get("errors", []) + [
                "No active criteria available for validation."
            ],
            "status": "VALIDATION_FAILED"
        }

    try:

        validated_result, warnings = (
            validate_evaluation(
                llm_result=llm_result,
                active_criteria=criteria
            )
        )

    except Exception as exc:

        return {
            "errors": state.get("errors", []) + [
                f"Validation failed: {str(exc)}"
            ],
            "status": "VALIDATION_FAILED"
        }

    # -----------------------------------------------------
    # Add warnings to existing warnings
    # -----------------------------------------------------

    existing_warnings = state.get(
        "warnings",
        []
    )

    all_warnings = (
        existing_warnings + warnings
    )

    print(
        f"[VALIDATE] "
        f"Validation complete. "
        f"Warnings: {len(warnings)}"
    )

    return {
        "validated_result": validated_result,
        "warnings": all_warnings,
        "status": "VALIDATION_COMPLETE"
    }


# =========================================================
# 6. SCORE
# =========================================================

def score_node(state: RFPState) -> dict:
    """
    Calculate deterministic supplier scoring.
    """

    print("[SCORE] Calculating absolute weighted score...")

    validated_result = state.get(
        "validated_result"
    )

    criteria = state.get(
        "criteria"
    )

    if not validated_result:

        return {
            "errors": state.get("errors", []) + [
                "No validated result available for scoring."
            ],
            "status": "SCORING_FAILED"
        }

    if not criteria:

        return {
            "errors": state.get("errors", []) + [
                "No active criteria available for scoring."
            ],
            "status": "SCORING_FAILED"
        }

    try:

        score_result = calculate_supplier_score(
            validated_result=validated_result,
            active_criteria=criteria
        )

    except Exception as exc:

        return {
            "errors": state.get("errors", []) + [
                f"Scoring failed: {str(exc)}"
            ],
            "status": "SCORING_FAILED"
        }

    print(
        f"[SCORE] "
        f"{score_result['supplier_name']} = "
        f"{score_result['absolute_score']}"
    )

    # -----------------------------------------------------
    # Add current supplier's score to results
    # -----------------------------------------------------

    supplier_scores = state.get(
        "supplier_scores",
        []
    )

    supplier_score_record = {
        **score_result,
        "submission_date": state[
            "current_supplier"
        ].get("submission_date"),

        "experience_rating": state[
            "current_supplier"
        ].get("experience_rating")
    }

    updated_supplier_scores = (
        supplier_scores
        + [supplier_score_record]
    )

    return {
        "supplier_scores": updated_supplier_scores,
        "status": "SCORING_COMPLETE"
    }


# =========================================================
# 7. BENCHMARK
# =========================================================

def benchmark_node(state: RFPState) -> dict:
    """
    Calculate peer benchmarks, criterion gaps,
    relative percentages, and PPI after all
    suppliers have been scored.
    """

    print("[BENCHMARK] Calculating peer benchmarks and PPI...")

    supplier_scores = state.get(
        "supplier_scores",
        []
    )

    criteria = state.get(
        "criteria",
        []
    )

    if not supplier_scores:
        return {
            "errors": state.get("errors", []) + [
                "No supplier scores available for benchmarking."
            ],
            "status": "BENCHMARK_FAILED"
        }

    if not criteria:
        return {
            "errors": state.get("errors", []) + [
                "No active criteria available for benchmarking."
            ],
            "status": "BENCHMARK_FAILED"
        }

    try:

        benchmark_results = calculate_peer_benchmarks(
            supplier_scores=supplier_scores,
            active_criteria=criteria
        )

    except Exception as exc:

        return {
            "errors": state.get("errors", []) + [
                f"Benchmarking failed: {str(exc)}"
            ],
            "status": "BENCHMARK_FAILED"
        }

    print("[BENCHMARK] Benchmarking complete.")

    for supplier in benchmark_results:

        print(
            f"[BENCHMARK] "
            f"{supplier['supplier_name']} | "
            f"Absolute Score: {supplier['absolute_score']} | "
            f"PPI: {supplier['ppi']}"
        )

    return {
        "benchmark_results": benchmark_results,
        "status": "BENCHMARK_COMPLETE"
    }


# =========================================================
# 8. RANK
# =========================================================

def rank_node(state: RFPState) -> dict:
    """
    Apply deterministic ranking to all benchmarked suppliers.
    """

    print("[RANK] Applying deterministic ranking...")

    benchmark_results = state.get(
        "benchmark_results",
        []
    )

    if not benchmark_results:
        return {
            "errors": state.get("errors", []) + [
                "No benchmark results available for ranking."
            ],
            "status": "RANKING_FAILED"
        }

    try:
        ranked_results = rank_suppliers(
            benchmark_results
        )

    except Exception as exc:
        return {
            "errors": state.get("errors", []) + [
                f"Ranking failed: {str(exc)}"
            ],
            "status": "RANKING_FAILED"
        }

    print("[RANK] Ranking complete.")

    for supplier in ranked_results:
        print(
            f"[RANK] "
            f"{supplier['final_rank']}. "
            f"{supplier['supplier_name']} | "
            f"PPI: {supplier['ppi']}"
        )

    return {
        "ranked_results": ranked_results,
        "status": "RANKING_COMPLETE"
    }


# =========================================================
# 9. PERSIST
# =========================================================

def persist_node(state: RFPState) -> dict:
    """
    Persist the complete ranked evaluation results
    for the current RFP run.
    """

    print("[PERSIST] Saving results to SQLite...")

    rfp_run_id = state.get(
        "rfp_run_id"
    )

    ranked_results = state.get(
        "ranked_results",
        []
    )

    if not rfp_run_id:

        return {
            "errors": state.get("errors", []) + [
                "No RFP_RUN_ID available for persistence."
            ],
            "status": "PERSIST_FAILED"
        }

    if not ranked_results:

        return {
            "errors": state.get("errors", []) + [
                "No ranked suppliers available for persistence."
            ],
            "status": "PERSIST_FAILED"
        }

    try:

        # -------------------------------------------------
        # Save every supplier under the SAME RFP_RUN_ID
        # -------------------------------------------------

        saved_ids = []

        for supplier in ranked_results:

            row_id = save_supplier_result(
                rfp_run_id=rfp_run_id,
                supplier_result=supplier
            )

            saved_ids.append(
                row_id
            )

        # -------------------------------------------------
        # Mark complete
        # -------------------------------------------------

        update_rfp_run_status(
            rfp_run_id=rfp_run_id,
            status="COMPLETED"
        )

    except Exception as exc:

        # ---------------------------------------------
        # Mark run as failed
        # ---------------------------------------------

        try:

            update_rfp_run_status(
                rfp_run_id=rfp_run_id,
                status="FAILED"
            )

        except Exception:
            pass

        return {
            "errors": state.get("errors", []) + [
                f"Persistence failed: {str(exc)}"
            ],
            "status": "PERSIST_FAILED"
        }

    print(
        f"[PERSIST] Saved "
        f"{len(saved_ids)} supplier results."
    )

    print(
        f"[PERSIST] RFP_RUN_ID: "
        f"{rfp_run_id}"
    )

    return {
        "persisted_result_ids": saved_ids,
        "status": "PERSIST_COMPLETE"
    }


# =========================================================
# 10. PRESENT
# =========================================================

def present_node(state: RFPState) -> dict:
    """
    Present stage.

    Streamlit will use the final state to display:

    - Leaderboard
    - Detailed scorecards
    - Evidence
    - Justifications
    - Warnings
    - Tie-break explanation
    - JSON download
    """

    print("[PRESENT] Preparing results for Streamlit...")

    return {
        "status": "COMPLETE"
    }


# =========================================================
# SUPPLIER LOOP
# =========================================================

def should_process_next_supplier(
    state: RFPState
) -> Literal["evaluate", "benchmark"]:
    """
    Decide whether another supplier needs to be evaluated.

    If suppliers remain:
        → Evaluate

    If all suppliers are complete:
        → Benchmark
    """

    suppliers = state.get("suppliers", [])

    current_index = state.get(
        "current_supplier_index",
        0
    )

    if current_index < len(suppliers):
        return "evaluate"

    return "benchmark"


# =========================================================
# ADVANCE SUPPLIER
# =========================================================

def advance_supplier_node(state: RFPState) -> dict:
    """
    Move to the next supplier after scoring/validation.

    This node will eventually sit between Score and Evaluate.
    """

    current_index = state.get(
        "current_supplier_index",
        0
    )

    return {
        "current_supplier_index": current_index + 1
    }


# =========================================================
# BUILD LANGGRAPH
# =========================================================

def build_rfp_graph():

    graph = StateGraph(RFPState)

    # -----------------------------------------------------
    # Register nodes
    # -----------------------------------------------------

    graph.add_node("setup", setup_node)
    graph.add_node("input", input_node)
    graph.add_node("batch", batch_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("score", score_node)
    graph.add_node("benchmark", benchmark_node)
    graph.add_node("rank", rank_node)
    graph.add_node("advance_supplier", advance_supplier_node)
    graph.add_node("persist", persist_node)
    graph.add_node("present", present_node)

    # -----------------------------------------------------
    # Main workflow
    # -----------------------------------------------------

    graph.add_edge(START, "setup")
    graph.add_edge("setup", "input")
    graph.add_edge("input", "batch")
    graph.add_edge("batch","evaluate")
    graph.add_edge("evaluate","validate")
    graph.add_edge("validate", "score")
    graph.add_edge("score", "advance_supplier")

    # -----------------------------------------------------
    # Supplier loop
    # -----------------------------------------------------

    graph.add_conditional_edges(
        "advance_supplier",
        should_process_next_supplier,
        {
            "evaluate": "evaluate",
            "benchmark": "benchmark"
        }
    )

    # -----------------------------------------------------
    # Final workflow
    # -----------------------------------------------------

    graph.add_edge("benchmark","rank")
    graph.add_edge("rank","persist")
    graph.add_edge("persist","present")
    graph.add_edge("present",END    )

    return graph.compile()


# =========================================================
# TEST RUN
# =========================================================

if __name__ == "__main__":

    app = build_rfp_graph()

    test_suppliers = [
        {
            "supplier_id": "SUP001",
            "supplier_name": "Apex Systems",
            "submission_date": "2026-08-20",
            "experience_rating": 8,
            "pdf_path": "rfps/apex_systems.pdf"
        },
        {
            "supplier_id": "SUP002",
            "supplier_name": "BrightPath Tech",
            "submission_date": "2026-08-21",
            "experience_rating": 6,
            "pdf_path": "rfps/brightpath_tech.pdf"
        },
        {
            "supplier_id": "SUP003",
            "supplier_name": "NexaWorks",
            "submission_date": "2026-08-19",
            "experience_rating": 9,
            "pdf_path": "rfps/nexaworks.pdf"
        },
        {
            "supplier_id": "SUP004",
            "supplier_name": "Orbit Digital",
            "submission_date": "2026-08-22",
            "experience_rating": 10,
            "pdf_path": "rfps/orbit_digital.pdf"
        }
    ]

    initial_state: RFPState = {
        "rfp_run_id": "TEST_RUN_001",
        "criteria": [],
        "suppliers": test_suppliers,
        "current_supplier_index": 0,
        "status": "STARTING",
        "warnings": [],
        "errors": [],
        "supplier_scores": []
    }

    result = app.invoke(initial_state)

    print("\n====================================")
    print("FINAL STATE")
    print("====================================")

    print(result)