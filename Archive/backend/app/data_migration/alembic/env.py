from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.core.database import Base
from app.core.config import DATABASE_URL

# 🔥 FORCE LOAD ALL MODELS
from app.models.document import Document
from app.models.document_chunks import DocumentChunk
from app.models.audit_logs import AuditLog
from app.models.branch import Branch
from app.models.hq import HeadQuarter
from app.models.unit import Unit
from app.models.user import User

# Alembic config
config = context.config

# 🔥 Set DB URL dynamically
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata
target_metadata = Base.metadata

print("🔥 DB URL:", DATABASE_URL)
print("🔥 TABLES DETECTED:", Base.metadata.tables.keys())


# -----------------------------
# OFFLINE MODE
# -----------------------------
def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# -----------------------------
# ONLINE MODE (IMPORTANT)
# -----------------------------
def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# Entry
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()