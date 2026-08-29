import sqlite3
from pathlib import Path


# ---------------------------------------------------------
# Database location
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "rfp_evaluation.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


# ---------------------------------------------------------
# Seed data - as specified in the project brief
# ---------------------------------------------------------

CRITERIA = [
    (
        1,
        "Technical Capability",
        "Architecture, integrations, scalability, technical fit",
        30.0,
        10.0,
        1
    ),
    (
        2,
        "Implementation Plan",
        "Timeline, milestones, staffing, risk plan",
        20.0,
        10.0,
        1
    ),
    (
        3,
        "Commercial Value",
        "Pricing clarity, total cost, assumptions",
        20.0,
        10.0,
        1
    ),
    (
        4,
        "Security & Compliance",
        "Controls, certifications, privacy, auditability",
        20.0,
        10.0,
        1
    ),
    (
        5,
        "Support & Experience",
        "Support model, similar projects, references",
        10.0,
        10.0,
        1
    )
]


# ---------------------------------------------------------
# Create database and tables
# ---------------------------------------------------------

def initialize_database():
    """
    Create the SQLite database and execute schema.sql.
    """

    # Make sure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to SQLite
    connection = sqlite3.connect(DB_PATH)

    try:
        # Read schema.sql
        with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
            schema = file.read()

        # Create tables
        connection.executescript(schema)

        connection.commit()

        print("Database initialized successfully.")
        print(f"Database location: {DB_PATH}")

    finally:
        connection.close()


# ---------------------------------------------------------
# Seed evaluation criteria
# ---------------------------------------------------------

def seed_criteria():
    """
    Insert the active evaluation criteria into SQLite.
    """

    connection = sqlite3.connect(DB_PATH)

    try:
        cursor = connection.cursor()

        # Insert criteria
        cursor.executemany(
            """
            INSERT OR REPLACE INTO evaluation_criteria
            (
                criterion_id,
                name,
                description,
                weight,
                max_score,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            CRITERIA
        )

        connection.commit()

        print("\nEvaluation criteria seeded successfully.")

    finally:
        connection.close()


# ---------------------------------------------------------
# Validate active criteria
# ---------------------------------------------------------

def validate_criteria():
    """
    Validate that active criteria exist and their weights
    add up to exactly 100%.
    """

    connection = sqlite3.connect(DB_PATH)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(weight), 0)
            FROM evaluation_criteria
            WHERE is_active = 1
            """
        )

        count, total_weight = cursor.fetchone()

        print("\nActive criteria:", count)
        print("Total active weight:", total_weight)

        # Check that criteria exist
        if count == 0:
            raise ValueError(
                "No active evaluation criteria found."
            )

        # Check that weights equal 100%
        if abs(total_weight - 100.0) > 0.0001:
            raise ValueError(
                f"Active criterion weights must total 100%. "
                f"Current total: {total_weight}%"
            )

        print("✓ Criteria validation passed.")
        print("✓ Active weights total 100%.")

    finally:
        connection.close()


# ---------------------------------------------------------
# Display seeded criteria
# ---------------------------------------------------------

def display_criteria():
    """
    Display the criteria currently stored in SQLite.
    """

    connection = sqlite3.connect(DB_PATH)

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
            ORDER BY criterion_id
            """
        )

        rows = cursor.fetchall()

        print("\n" + "=" * 80)
        print("ACTIVE EVALUATION CRITERIA")
        print("=" * 80)

        for row in rows:
            criterion_id, name, description, weight, max_score, is_active = row

            print(f"\n{criterion_id}. {name}")
            print(f"   Description : {description}")
            print(f"   Weight      : {weight}%")
            print(f"   Max Score   : {max_score}")
            print(f"   Active      : {'Yes' if is_active else 'No'}")

        print("\n" + "=" * 80)

    finally:
        connection.close()


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":

    print("Starting database setup...")

    # 1. Create database/tables
    initialize_database()

    # 2. Insert criteria
    seed_criteria()

    # 3. Validate criteria
    validate_criteria()

    # 4. Display results
    display_criteria()

    print("\nDatabase setup completed successfully.")