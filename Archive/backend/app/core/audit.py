import json
import inspect
from datetime import datetime
from functools import wraps

from app.core.database import SessionLocal
from app.models.audit_logs import AuditLog


# -----------------------------
# 🎯 MAIN DECORATOR
# -----------------------------
def audit_action(action_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db = SessionLocal()

            try:
                # 🔥 Support both sync + async
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                user = _extract_user(kwargs, result)

                _save_log(
                    db=db,
                    action=action_name,
                    user=user,
                    status="SUCCESS",
                    kwargs=kwargs
                )

                return result

            except Exception as e:
                user = _extract_user(kwargs, None)

                _save_log(
                    db=db,
                    action=action_name,
                    user=user,
                    status="FAILED",
                    error=str(e),
                    kwargs=kwargs
                )

                raise e

            finally:
                db.close()

        return wrapper
    return decorator


# -----------------------------
# 🔍 USER EXTRACTION
# -----------------------------
def _extract_user(kwargs, result):
    # From FastAPI Depends
    if "current_user" in kwargs:
        return kwargs["current_user"]

    if "user" in kwargs:
        return kwargs["user"]

    # From response (login case)
    if isinstance(result, dict) and "user" in result:
        return result["user"]

    return None


# -----------------------------
# 🧹 CLEAN KWARGS
# -----------------------------
def _clean_kwargs(kwargs):
    safe_data = {}

    for k, v in kwargs.items():
        if k in ["db"]:  # skip DB session
            continue

        try:
            safe_data[k] = str(v)[:100]
        except:
            continue

    return safe_data


# -----------------------------
# 💾 SAVE LOG
# -----------------------------
def _save_log(db, action, user, status, kwargs, error=None):
    doc = kwargs.get("doc", None)

    log = AuditLog(
        action=action,

        user_id=getattr(user, "id", None),
        role=getattr(user, "role", None),

        target_id=getattr(doc, "id", None),
        target_type="document" if doc else "system",

        status=status,
        message=error,

        extra=json.dumps(_clean_kwargs(kwargs)),

        timestamp=datetime.utcnow()
    )

    db.add(log)
    db.commit()