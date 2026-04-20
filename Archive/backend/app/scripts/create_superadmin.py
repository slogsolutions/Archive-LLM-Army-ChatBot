from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password

db = SessionLocal()

army_number = "ARMY-SUPER-001"
name = "Super Admin"
password = "123"

# Check if exists
existing = db.query(User).filter(User.army_number == army_number).first()

if existing:
    print("SuperAdmin already exists")
else:
    user = User(
        army_number=army_number,
        name=name,
        password=hash_password(password),
        role="super_admin",
        rank_level=1,
        hq_id=None,
        unit_id=None,
        branch_id=None
    )

    db.add(user)
    db.commit()

    print("SuperAdmin created successfully")
