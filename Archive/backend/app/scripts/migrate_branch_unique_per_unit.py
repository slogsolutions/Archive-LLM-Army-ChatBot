from sqlalchemy import text

from app.core.database import engine


with engine.begin() as connection:
    # Remove the earlier wrong uniqueness rule if it was applied.
    connection.execute(text("DROP INDEX IF EXISTS ix_branches_unit_id_unique"))

    # Keep the earliest branch for each unit/name pair and remove later duplicates.
    connection.execute(
        text(
            """
            DELETE FROM branches
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY unit_id, LOWER(TRIM(name))
                            ORDER BY id ASC
                        ) AS row_number
                    FROM branches
                    WHERE unit_id IS NOT NULL
                      AND name IS NOT NULL
                ) duplicates
                WHERE duplicates.row_number > 1
            )
            """
        )
    )

    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_branches_unit_name_unique "
            "ON branches (unit_id, LOWER(TRIM(name)))"
        )
    )

print("Branch migration complete: each unit can have Q, A, G, but no duplicate branch name.")
