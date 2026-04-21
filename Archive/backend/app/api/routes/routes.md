Auth
/auth/login
/auth/me

Structure Creation
/hq/create
/unit/create
/branch/create

User Management
/users/create
/users/update/{id}
/users/delete/{id}

Document (later)
/documents/upload
/documents/view
/documents/search



# FINAL PERMISSION TABLE

```
| Role        | Upload | Approve | Edit OCR | View        | Download |
| ----------- | ------ | ------- | -------- | ----------- | -------- |
| super_admin | ✅      | ✅       | ✅        | ✅           | ✅        |
| hq_admin    | ❌      | ✅       | ❌        | ✅           | ✅        |
| unit_admin  | ❌      | ✅       | ❌        | ✅           | ✅        |
| officer     | ✅      | ✅       | ✅        | ✅           | ✅        |
| clerk       | ✅      | ❌       | ✅        | ✅           | ✅        |
| trainee     | ❌      | ❌       | ❌        | ✅ (limited) | ✅        |


```

# 🚀 User API Testing Guide (Postman)

Base URL:
http://localhost:8000

Auth Type:
Bearer Token (JWT)

Header:
Authorization: Bearer <your_token>
Content-Type: application/json


---

# 🔐 1. LOGIN (Get Token)

POST /auth/login

Body:
{
  "army_number": "SA001",
  "password": "password"
}

Response:
{
  "access_token": "JWT_TOKEN"
}

👉 Copy this token and use in all requests.


---

# 👤 2. CREATE USER

POST /users/create

## ✅ Super Admin (can create anyone)

Body:
{
  "army_number": "U100",
  "name": "Test User",
  "password": "123456",
  "role": "hq_admin",
  "rank_level": 5,
  "hq_id": 1,
  "unit_id": null,
  "branch_id": 1
}

---

## ✅ HQ Admin (restricted roles)

Allowed roles:
- unit_admin
- officer
- clerk
- trainee

Body:
{
  "army_number": "U101",
  "name": "HQ User",
  "password": "123456",
  "role": "unit_admin",
  "rank_level": 4,
  "hq_id": 1,
  "unit_id": 2,
  "branch_id": 1
}

❌ Test Case:
- Try creating "super_admin" → Should FAIL (403)
- Try wrong HQ → Should FAIL

---

## ✅ Clerk Creation (Special Case)

Body:
{
  "army_number": "U102",
  "name": "Clerk User",
  "password": "123456",
  "role": "clerk",
  "rank_level": 2,
  "hq_id": 1,
  "unit_id": 2,
  "branch_id": 1,
  "clerk_type": "junior",
  "task_category": "records"
}

❌ Invalid clerk_type → FAIL

---

# 📄 3. GET ALL USERS

GET /users/

## Behavior:

- super_admin → ALL users
- hq_admin → Only same HQ
- unit_admin → Only same Unit

---

# 🔍 4. GET SINGLE USER

GET /users/{user_id}

Example:
GET /users/5

## Tests:

✅ Same scope → SUCCESS  
❌ Different HQ/unit → 403  
❌ Invalid ID → 404  


---

# ✏️ 5. UPDATE USER

PUT /users/update/{user_id}

Body:
{
  "name": "Updated Name",
  "password": "newpass",
  "role": "clerk",
  "clerk_type": "senior"
}

## Rules:

- Cannot update equal/higher rank
- Scope must match
- Clerk must have valid clerk_type

❌ Test Cases:
- Update higher rank → FAIL
- Invalid clerk_type → FAIL

---

# ❌ 6. DELETE USER

DELETE /users/delete/{user_id}

## Rules:

- Cannot delete equal/higher rank
- Must be in same HQ/unit

## Tests:

✅ Valid delete → SUCCESS  
❌ Higher rank → 403  
❌ Wrong HQ → 403  
❌ Not found → 404  


---

# 🧪 IMPORTANT TEST SCENARIOS

## 🔥 RBAC Matrix

| Role         | Can Create        | Scope         |
|--------------|------------------|--------------|
| super_admin  | ALL              | Global       |
| hq_admin     | unit_admin↓      | HQ Only      |
| unit_admin   | officer↓         | Unit Only    |

---

## 🔥 Edge Cases

- Duplicate army_number → 400
- Missing fields → 400
- Invalid role → 403
- Clerk without type → 400

---

# ⚙️ Postman Setup Tips

1. Create Environment:
   - base_url = http://localhost:8000
   - token = <JWT>

2. Use in requests:
   {{base_url}}/users/

3. Headers:
   Authorization: Bearer {{token}}

---

# ✅ SUCCESS RESPONSES

{
  "message": "User created"
}

{
  "message": "User updated"
}

{
  "message": "User deleted"
}

---

# ❌ ERROR RESPONSES

403 → Not allowed  
404 → User not found  
400 → Validation error  

---

# 📌 Notes

- Rank system is critical:
  LOWER number = higher authority (assumed)
- Always test with multiple roles
- Audit logs should trigger on each action
