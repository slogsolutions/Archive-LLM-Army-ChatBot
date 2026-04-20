from sqlalchemy import inspect, text

from app.core.database import engine


def column_exists(columns, name):
    return any(column["name"] == name for column in columns)


with engine.begin() as connection:
    inspector = inspect(connection)
    columns = inspector.get_columns("users")

    if not column_exists(columns, "army_number"):
        connection.execute(text("ALTER TABLE users ADD COLUMN army_number VARCHAR"))

    if not column_exists(columns, "name"):
        connection.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR"))

    # Preserve old local data if it was created with the previous email-based schema.
    refreshed_columns = inspect(connection).get_columns("users")
    if column_exists(refreshed_columns, "email"):
        connection.execute(
            text(
                "UPDATE users "
                "SET army_number = COALESCE(NULLIF(army_number, ''), NULLIF(email, ''), 'ARMY-USER-' || id), "
                "name = COALESCE(NULLIF(name, ''), role, 'Army User')"
            )
        )
    else:
        connection.execute(
            text(
                "UPDATE users "
                "SET army_number = COALESCE(NULLIF(army_number, ''), 'ARMY-USER-' || id), "
                "name = COALESCE(NULLIF(name, ''), role, 'Army User')"
            )
        )

    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_army_number "
            "ON users (army_number)"
        )
    )

    connection.execute(text("ALTER TABLE users ALTER COLUMN army_number SET NOT NULL"))
    connection.execute(text("ALTER TABLE users ALTER COLUMN name SET NOT NULL"))

    if column_exists(inspect(connection).get_columns("users"), "email"):
        connection.execute(text("ALTER TABLE users DROP COLUMN email"))

print("User identity migration complete. Login now uses army_number, not email.")
