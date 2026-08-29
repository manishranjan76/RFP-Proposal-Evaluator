import sqlite3

connection = sqlite3.connect(
    "data/rfp_evaluation.db"
)

cursor = connection.cursor()

# Delete the dummy supplier result
cursor.execute(
    """
    DELETE FROM supplier_results
    WHERE supplier_name = ?
    """,
    ("Database Test Supplier",)
)

# Delete orphaned completed test runs
cursor.execute(
    """
    DELETE FROM rfp_runs
    WHERE status = ?
      AND rfp_run_id NOT IN (
          SELECT DISTINCT rfp_run_id
          FROM supplier_results
      )
    """,
    ("COMPLETED",)
)

connection.commit()

print(
    f"Deleted supplier test rows: "
    f"{cursor.rowcount}"
)

connection.close()

print("Cleanup completed.")