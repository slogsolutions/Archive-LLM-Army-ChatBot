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