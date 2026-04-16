from app.core.database import engine

conn = engine.connect()
print("DB Connected")