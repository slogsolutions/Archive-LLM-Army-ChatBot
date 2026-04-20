from sqlalchemy import text

from app.core.database import engine


create_sql = """
CREATE TABLE users_reordered (
    id INTEGER PRIMARY KEY,
    army_number VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    password VARCHAR,
    role VARCHAR,
    rank_level INTEGER,
    hq_id INTEGER,
    unit_id INTEGER,
    branch_id INTEGER,
    clerk_type VARCHAR,
    task_category VARCHAR
)
"""

copy_sql = """
INSERT INTO users_reordered (
    id,
    army_number,
    name,
    password,
    role,
    rank_level,
    hq_id,
    unit_id,
    branch_id,
    clerk_type,
    task_category
)
SELECT
    id,
    army_number,
    name,
    password,
    role,
    rank_level,
    hq_id,
    unit_id,
    branch_id,
    clerk_type,
    task_category
FROM users
ORDER BY id
"""


with engine.begin() as connection:
    connection.execute(text("DROP TABLE IF EXISTS users_reordered"))
    connection.execute(text(create_sql))
    connection.execute(text(copy_sql))
    connection.execute(text("DROP TABLE users"))
    connection.execute(text("ALTER TABLE users_reordered RENAME TO users"))
    connection.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_army_number ON users (army_number)")
    )

print("Users table reordered: id, army_number, name, password, role, rank_level, ...")
