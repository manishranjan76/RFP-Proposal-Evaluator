import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime


# =========================================================
# Database paths
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "rfp_evaluation.db"

SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


# =========================================================
# Connection
# =========================================================

def get_connection() -> sqlite3.Connection:
    """
    Create a SQLite connection.

    Row factory allows rows to be accessed like dictionaries.
    """

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    # Enable foreign key enforcement
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# =========================================================
# Initialize database
# =========================================================

def initialize_database() -> None:
    """
    Create database tables using schema.sql.
    """

    connection = get_connection()

    try:

        with open(
            SCHEMA_PATH,
            "r",
            encoding="utf-8"
        ) as file:

            schema = file.read()

        connection.executescript(
            schema
        )

        connection.commit()

    finally:

        connection.close()


# =========================================================
# Create RFP Run
# =========================================================

def create_rfp_run(
    status: str = "CREATED"
) -> str:
    """
    Create one RFP evaluation run.

    A single RFP_RUN_ID will be shared by all suppliers
    evaluated in that batch.
    """

    rfp_run_id = str(
        uuid.uuid4()
    )

    created_at = datetime.now().isoformat(
        timespec="seconds"
    )

    connection = get_connection()

    try:

        connection.execute(
            """
            INSERT INTO rfp_runs (
                rfp_run_id,
                created_at,
                status
            )
            VALUES (?, ?, ?)
            """,
            (
                rfp_run_id,
                created_at,
                status
            )
        )

        connection.commit()

    finally:

        connection.close()

    return rfp_run_id


# =========================================================
# Update RFP Run Status
# =========================================================

def update_rfp_run_status(
    rfp_run_id: str,
    status: str
) -> None:
    """
    Update the status of an RFP run.
    """

    connection = get_connection()

    try:

        cursor = connection.execute(
            """
            UPDATE rfp_runs
            SET status = ?
            WHERE rfp_run_id = ?
            """,
            (
                status,
                rfp_run_id
            )
        )

        if cursor.rowcount == 0:

            raise ValueError(
                f"RFP run not found: {rfp_run_id}"
            )

        connection.commit()

    finally:

        connection.close()


# =========================================================
# Save Supplier Result
# =========================================================

def save_supplier_result(
    rfp_run_id: str,
    supplier_result: dict
) -> int:
    """
    Persist the complete supplier result.

    The entire result is stored as JSON so that evidence,
    criterion scores, benchmark metrics, PPI and rank are
    retained without losing detail.
    """

    required_fields = [
        "supplier_name",
        "submission_date",
        "experience_rating"
    ]

    for field in required_fields:

        if field not in supplier_result:

            raise ValueError(
                f"Supplier result missing required field: "
                f"{field}"
            )

    supplier_name = supplier_result[
        "supplier_name"
    ]

    submission_date = supplier_result[
        "submission_date"
    ]

    experience_rating = float(
        supplier_result[
            "experience_rating"
        ]
    )

    absolute_score = supplier_result.get(
        "absolute_score"
    )

    if absolute_score is not None:

        absolute_score = float(
            absolute_score
        )

    ppi = supplier_result.get(
        "ppi"
    )

    if ppi is not None:

        ppi = float(
            ppi
        )

    final_rank = supplier_result.get(
        "final_rank"
    )

    if final_rank is not None:

        final_rank = int(
            final_rank
        )

    result_json = json.dumps(
        supplier_result,
        ensure_ascii=False
    )

    connection = get_connection()

    try:

        # -------------------------------------------------
        # Confirm run exists
        # -------------------------------------------------

        run = connection.execute(
            """
            SELECT rfp_run_id
            FROM rfp_runs
            WHERE rfp_run_id = ?
            """,
            (rfp_run_id,)
        ).fetchone()

        if run is None:

            raise ValueError(
                f"RFP run does not exist: "
                f"{rfp_run_id}"
            )

        # -------------------------------------------------
        # Insert supplier result
        # -------------------------------------------------

        cursor = connection.execute(
            """
            INSERT INTO supplier_results (
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:

        connection.close()


# =========================================================
# Get Supplier Results
# =========================================================

def get_supplier_results(
    rfp_run_id: str
) -> list[dict]:
    """
    Retrieve all supplier results for an RFP run.
    """

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT *
            FROM supplier_results
            WHERE rfp_run_id = ?
            ORDER BY final_rank ASC
            """,
            (rfp_run_id,)
        ).fetchall()

        results = []

        for row in rows:

            result = dict(row)

            # Convert JSON back into dictionary
            result["result_json"] = json.loads(
                result["result_json"]
            )

            results.append(
                result
            )

        return results

    finally:

        connection.close()


# =========================================================
# Get RFP Run
# =========================================================

def get_rfp_run(
    rfp_run_id: str
) -> dict | None:
    """
    Retrieve metadata for one RFP run.
    """

    connection = get_connection()

    try:

        row = connection.execute(
            """
            SELECT *
            FROM rfp_runs
            WHERE rfp_run_id = ?
            """,
            (rfp_run_id,)
        ).fetchone()

        if row is None:

            return None

        return dict(row)

    finally:

        connection.close()


# =========================================================
# Get Completed RFP Runs
# =========================================================

def get_completed_rfp_runs() -> list[dict]:
    """
    Retrieve completed RFP evaluation runs,
    newest first, along with supplier count
    and top supplier information.
    """

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                r.rfp_run_id,
                r.created_at,
                r.status,
                COUNT(s.id) AS supplier_count,
                MIN(s.final_rank) AS top_rank
            FROM rfp_runs r
            LEFT JOIN supplier_results s
                ON r.rfp_run_id = s.rfp_run_id
            WHERE r.status = 'COMPLETED'
            GROUP BY
                r.rfp_run_id,
                r.created_at,
                r.status
            ORDER BY
                r.created_at DESC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


# =========================================================
# Get Active Criteria
# =========================================================

def get_active_criteria() -> list[dict]:
    """
    Retrieve active evaluation criteria.
    """

    connection = get_connection()

    try:

        rows = connection.execute(
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
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


# =========================================================
# Standalone Test
# =========================================================

if __name__ == "__main__":

    print("\n" + "=" * 80)
    print("DATABASE TEST")
    print("=" * 80)

    # -----------------------------------------------------
    # 1. Initialize database
    # -----------------------------------------------------

    initialize_database()

    print(
        f"Database: {DB_PATH}"
    )

    # -----------------------------------------------------
    # 2. Load active criteria
    # -----------------------------------------------------

    criteria = get_active_criteria()

    print(
        f"\nActive criteria: {len(criteria)}"
    )

    for criterion in criteria:

        print(
            f"{criterion['criterion_id']}. "
            f"{criterion['name']} | "
            f"Weight: {criterion['weight']}%"
        )

    # -----------------------------------------------------
    # 3. Create test run
    # -----------------------------------------------------

    run_id = create_rfp_run()

    print(
        f"\nCreated RFP Run: {run_id}"
    )

    # -----------------------------------------------------
    # 4. Create test supplier result
    # -----------------------------------------------------

    test_supplier = {

        "supplier_name": "Database Test Supplier",

        "submission_date": "2026-08-21",

        "experience_rating": 8,

        "absolute_score": 78.5,

        "ppi": 94.25,

        "final_rank": 1,

        "criterion_results": [

            {
                "criterion_id": 1,
                "criterion_name": "Technical Capability",
                "score": 8,
                "max_score": 10,
                "weight": 30,
                "peer_best_score": 9,
                "criterion_gap": -1,
                "relative_percentage": 88.89,
                "weighted_relative": 2666.67,
                "justification": "Strong architecture.",
                "evidence": "Cloud-native platform."
            }
        ]
    }

    # -----------------------------------------------------
    # 5. Save
    # -----------------------------------------------------

    row_id = save_supplier_result(
        rfp_run_id=run_id,
        supplier_result=test_supplier
    )

    print(
        f"Saved supplier result. "
        f"Database row ID: {row_id}"
    )

    # -----------------------------------------------------
    # 6. Retrieve
    # -----------------------------------------------------

    results = get_supplier_results(
        run_id
    )

    print(
        f"\nRetrieved {len(results)} supplier result(s)."
    )

    print(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        )
    )

    # -----------------------------------------------------
    # 7. Complete run
    # -----------------------------------------------------

    update_rfp_run_status(
        run_id,
        "COMPLETED"
    )

    run = get_rfp_run(
        run_id
    )

    print(
        "\nRun status:",
        run["status"]
    )

    print("\nDatabase test completed.")