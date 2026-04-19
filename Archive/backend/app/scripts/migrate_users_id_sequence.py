from sqlalchemy import text
from app.core.database import engine

with engine.begin() as connection:
    connection.execute(text(
        "CREATE SEQUENCE IF NOT EXISTS users_id_seq"
    ))
    connection.execute(text(
        "SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)"
    ))
    connection.execute(text(
        "ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq')"
    ))
    connection.execute(text(
        "ALTER SEQUENCE users_id_seq OWNED BY users.id"
    ))

print("Migration complete: users.id now has an auto-increment sequence.")
