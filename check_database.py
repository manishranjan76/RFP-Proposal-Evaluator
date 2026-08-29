import sqlite3
from pathlib import Path


DB_PATH = Path("data/rfp_evaluation.db")


connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row

cursor = connection.cursor()


# ---------------------------------------------------------
# Show tables
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("DATABASE TABLES")
print("=" * 80)

cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""")

tables = cursor.fetchall()

for table in tables:
    print(table["name"])


# ---------------------------------------------------------
# Show evaluation criteria
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("EVALUATION CRITERIA")
print("=" * 80)

cursor.execute("""
    SELECT *
    FROM evaluation_criteria
    ORDER BY criterion_id
""")

rows = cursor.fetchall()

for row in rows:
    print(dict(row))


# ---------------------------------------------------------
# Show RFP runs
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("RFP RUNS")
print("=" * 80)

cursor.execute("""
    SELECT *
    FROM rfp_runs
    ORDER BY created_at
""")

rows = cursor.fetchall()

for row in rows:
    print(dict(row))


# ---------------------------------------------------------
# Show supplier results
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("SUPPLIER RESULTS")
print("=" * 80)

cursor.execute("""
    SELECT *
    FROM supplier_results
    ORDER BY id
""")

rows = cursor.fetchall()

for row in rows:
    print(dict(row))


connection.close()