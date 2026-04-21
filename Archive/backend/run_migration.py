import os

print("🚀 Creating migration...")
os.system('python -m alembic -c app/data_migration/alembic.ini revision --autogenerate -m "auto"')

print("🚀 Applying migration...")
os.system('python -m alembic -c app/data_migration/alembic.ini upgrade head')

print("✅ Done")