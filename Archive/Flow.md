# 🚀 ARCHIVE PROJECT - COMPLETE BACKEND FLOW (RBAC + API TESTING)

---

# 🔐 GLOBAL LOGIN (USE EVERYWHERE)

```
Email: super@army.com  
Password: 123
```

👉 Login once → use token in all APIs:

```
Authorization: Bearer {{token}}
```

---

# 🧠 SYSTEM HIERARCHY

```
Super Admin
   ↓
HeadQuarter (2STC, 3STC)
   ↓
Unit (3TTR, 5TTR)
   ↓
Branch (A, Q, G)
   ↓
Users (roles)
```

---

# 🔐 STEP 1 — LOGIN

### POST `/auth/login`

```json
{
  "email": "super@army.com",
  "password": "123"
}
```

### Response:

```json
{
  "access_token": "TOKEN"
}
```

---

# 👤 STEP 2 — CURRENT USER

### GET `/auth/me`

Header:

```
Authorization: Bearer {{token}}
```

---

# 🏢 STEP 3 — CREATE HQ

### POST `/hq/create`

```json
{
  "name": "2STC"
}
```

### ACCESS CONTROL

| Role        | Access |
| ----------- | ------ |
| super_admin | ✔      |
| others      | ❌      |

---

# 🏭 STEP 4 — CREATE UNIT

### POST `/unit/create`

```json
{
  "name": "3TTR",
  "hq_id": 1
}
```

### ACCESS CONTROL

| Role        | Access           |
| ----------- | ---------------- |
| super_admin | ✔                |
| hq_admin    | ✔ (same HQ only) |
| others      | ❌                |

---

# 🪖 STEP 5 — CREATE BRANCH

### POST `/branch/create`

```json
{
  "name": "A",
  "description": "Admin Branch",
  "unit_id": 1
}
```

### ACCESS CONTROL

| Role        | Access             |
| ----------- | ------------------ |
| super_admin | ✔                  |
| hq_admin    | ✔                  |
| unit_admin  | ✔ (same unit only) |
| others      | ❌                  |

---

# 👤 STEP 6 — CREATE USERS

### POST `/users/create`

---

## 🔹 HQ ADMIN

```json
{
  "email": "hq@army.com",
  "password": "123",
  "role": "hq_admin",
  "rank_level": 2,
  "hq_id": 1
}
```

---

## 🔹 UNIT ADMIN

```json
{
  "email": "unit@army.com",
  "password": "123",
  "role": "unit_admin",
  "rank_level": 3,
  "hq_id": 1,
  "unit_id": 1
}
```

---

## 🔹 OFFICER

```json
{
  "email": "officer@army.com",
  "password": "123",
  "role": "officer",
  "rank_level": 4,
  "hq_id": 1,
  "unit_id": 1,
  "branch_id": 1
}
```

---

## 🔹 CLERK (senior,junior)

```json
{
  "email": "clerk@army.com",
  "password": "123",
  "role": "clerk",
  "clerk_type":"senior|junior",
  "rank_level": 5,
  "hq_id": 1,
  "unit_id": 1,
  "branch_id": 1,
  "task_category": "ration"
}
```

---

## 🔹 TRAINEE

```json
{
  "email": "trainee@army.com",
  "password": "123",
  "role": "trainee",
  "rank_level": 6,
  "hq_id": 1,
  "unit_id": 1,
  "branch_id": 1
}
```

---

# 🔍 STEP 7 — GET USERS

### GET `/users/`

### ACCESS CONTROL

| Role        | Result         |
| ----------- | -------------- |
| super_admin | All users      |
| hq_admin    | Only same HQ   |
| unit_admin  | Only same Unit |
| officer     | ❌ denied       |
| clerk       | ❌ denied       |
| trainee     | ❌ denied       |

---

# 🔄 STEP 8 — UPDATE USER

### PUT `/users/update/{id}`

```json
{
  "task_category": "training"
}
```

### RULES

✔ Higher rank → can update lower
❌ Lower → cannot update higher
❌ Same level → restricted

---

# ❌ STEP 9 — DELETE USER

### DELETE `/users/delete/{id}`

### RULES

✔ Higher rank → delete lower
❌ Lower → delete higher
❌ Same → delete same

---

# 🧠 STEP 10 — RBAC TEST

Login as:

* officer
* clerk
* trainee

Try:

```
GET /users/
```

### Expected:

| Role    | Result   |
| ------- | -------- |
| officer | ❌ denied |
| clerk   | ❌ denied |
| trainee | ❌ denied |

---

# ⚠️ COMMON ERRORS

* Missing Authorization header
* Wrong token
* Wrong hq_id / unit_id
* Creating higher role from lower role
* Rank mismatch

---

# 🧱 DATABASE SCHEMA

```
headquarters
- id
- name

units
- id
- name
- hq_id

branches
- id
- name
- description
- unit_id

users
- id
- email
- password
- role
- rank_level
- hq_id
- unit_id
- branch_id
- task_category
```

---

# 🧩 MAIN.PY (FINAL CLEAN)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine

# MODELS
from app.models.user import User
from app.models.hq import HeadQuarter
from app.models.unit import Unit
from app.models.branch import Branch

# ROUTES
from app.api.routes import auth, users, hq, unit, branch

app = FastAPI(title="Army Archive System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(hq.router, prefix="/hq", tags=["hq"])
app.include_router(unit.router, prefix="/unit", tags=["unit"])
app.include_router(branch.router, prefix="/branch", tags=["branch"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/test")
def test():
    return {"message": "API working"}

Base.metadata.create_all(bind=engine)
```

---

# ✅ FINAL CHECKLIST

✔ Login works
✔ Token works
✔ /me works
✔ HQ → Unit → Branch created
✔ Users created
✔ RBAC enforced
✔ Rank restrictions working

---

# 🚀 NEXT STEP

👉 Document Upload + MinIO Integration

```
What you want to support

You have 3 concepts mixed together:

1. Approval flow
Clerk uploads
Officer approves

2. Visibility control (rank-based)
Who can SEE document

3. Clerk types
Junior Clerk → needs approval
Senior Clerk → direct upload

```

# Document Status Flow

```
uploaded
   ↓
processing (Celery starts)
   ↓
processed (OCR done)
   ↓
reviewed (clerk edits)
   ↓
indexed (Elastic stored)
```

# Document Status Flow (Deep)

```
UPLOAD →
    MinIO
    DB (status=uploaded)
    ↓
Celery Task →
    status=processing
    ↓
Download from MinIO
    ↓
PaddleOCR
    ↓
Save text (status=processed)
    ↓
Elasticsearch index
    ↓
status=indexed
```
# Uplaoding Flow

```
1. User uploads file
    ↓
2. File goes to MinIO (storage)
    ↓
3. Metadata saved in PostgreSQL
    ↓
4. Celery task triggered
    ↓
5. Worker downloads file from MinIO
    ↓
6. OCR runs (PaddleOCR)
    ↓
7. Text saved in DB
    ↓
8. Elasticsearch indexed
    ↓
9. Later → Vector DB

```