"""Versioned JSON API for HeavyLift CRM."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from flask import Blueprint, current_app, g, jsonify, render_template_string, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ...config import Config
from ...database import close_db, get_db
from ...rate_limit import rate_limiter
from ...routes.inquiry_helpers import normalize_mobile, validate_inquiry_form
from ...security import hash_password, is_lock_active, needs_password_rehash, verify_password
from ...validation import (
    clean_choice,
    clean_email,
    clean_optional_text,
    clean_text,
    clean_username,
    parse_decimal,
    parse_optional_date,
    parse_optional_int,
    validate_ordered_ids,
)

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# In-memory revoked token store (simple revocation list). This is ephemeral
# and will be lost on process restart. For production, persist revoked tokens
# in a database or cache with expiry.
revoked_tokens = set()

def _serializer():
    return URLSafeTimedSerializer(Config.SECRET_KEY, salt="heavylift-api-token")


def _client_ip():
    return (request.access_route[0] if request.access_route else request.remote_addr or "unknown")[:64]


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_dict(row):
    return {key: _jsonable(value) for key, value in (row or {}).items()}


def _ok(data=None, msg=None, status=200, **extra):
    payload = {"ok": True}
    if msg is not None:
        payload["msg"] = msg
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload), status


def _fail(msg, status=400, **extra):
    payload = {"ok": False, "msg": msg}
    payload.update(extra)
    return jsonify(payload), status


def _page_args():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", str(Config.API_DEFAULT_PAGE_SIZE)))
    except ValueError:
        page_size = Config.API_DEFAULT_PAGE_SIZE
    page = max(1, page)
    page_size = max(1, min(Config.API_MAX_PAGE_SIZE, page_size))
    offset = (page - 1) * page_size
    return page, page_size, offset


def _json_body(required=True):
    payload = request.get_json(silent=True)
    if payload is None:
        if required:
            raise ValueError("JSON body required.")
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    return payload


def _token_for_user(user):
    return _serializer().dumps({"uid": user["id"]})


def _user_from_token(token):
    try:
        payload = _serializer().loads(token, max_age=Config.API_TOKEN_TTL_MINUTES * 60)
    except SignatureExpired:
        return None, "Token expired."
    except BadSignature:
        return None, "Invalid token."

    # Check revocation list
    if token in revoked_tokens:
        return None, "Token revoked."

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id,username,email,role,location_id,created_at FROM users WHERE id=%s;",
            (payload.get("uid"),),
        )
        user = cur.fetchone()
        return user, None
    finally:
        close_db(conn, commit=False)


def _user_from_session():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id,username,email,role,location_id,created_at FROM users WHERE id=%s;",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        close_db(conn, commit=False)


def _current_user():
    cached = getattr(g, "api_user", None)
    if cached is not None:
        return cached

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        user, error = _user_from_token(auth_header.split(None, 1)[1].strip())
        if error:
            g.api_auth_error = error
            return None
        if user:
            g.api_user = user
            g.api_auth_method = "token"
            return user

    user = _user_from_session()
    if user:
        g.api_user = user
        g.api_auth_method = "session"
        return user

    token = request.headers.get("X-API-Token", "").strip()
    if token:
        user, error = _user_from_token(token)
        if error:
            g.api_auth_error = error
            return None
        if user:
            g.api_user = user
            g.api_auth_method = "token"
            return user

    return None


def api_login_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = _current_user()
            if not user:
                return _fail(getattr(g, "api_auth_error", "Authentication required."), 401)
            if roles and user.get("role") not in roles:
                return _fail("Access denied.", 403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def _scope_clause(user, column="location_id"):
    if user.get("role") == "teacher" and user.get("location_id"):
        return f" AND {column}=%s", [user["location_id"]]
    return "", []


def _fetch_one(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchone()


def _fetch_many(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def _count_and_fetch(conn, count_sql, list_sql, params):
    total_row = _fetch_one(conn, count_sql, params)
    total = int((total_row or {}).get("total") or 0)
    rows = _fetch_many(conn, list_sql, params)
    return total, rows


def _lookup_location_ids(cur, user):
    if user.get("role") == "teacher" and user.get("location_id"):
        cur.execute("SELECT id,name FROM locations WHERE id=%s;", (user["location_id"],))
        return cur.fetchall()
    cur.execute("SELECT id,name FROM locations ORDER BY position,name;")
    return cur.fetchall()


def _lookup_course_ids(cur, user):
    if user.get("role") == "teacher" and user.get("location_id"):
        cur.execute("SELECT id,name FROM courses WHERE location_id=%s ORDER BY position,name;", (user["location_id"],))
        return cur.fetchall()
    cur.execute("SELECT id,name FROM courses ORDER BY position,name;")
    return cur.fetchall()


def _calculate_fees(cur, course_id, offer_id=None):
    if not course_id:
        return 0.0
    cur.execute("SELECT fees FROM courses WHERE id=%s;", (course_id,))
    course = cur.fetchone()
    if not course:
        return 0.0
    fees = float(course["fees"] or 0)
    if offer_id:
        cur.execute("SELECT discount_type,discount_value FROM offers WHERE id=%s;", (offer_id,))
        offer = cur.fetchone()
        if offer:
            if offer["discount_type"] == "percent":
                fees -= fees * float(offer["discount_value"] or 0) / 100
            else:
                fees -= float(offer["discount_value"] or 0)
    return max(0.0, fees)


@api_bp.route("/", methods=["GET"])
def index():
    return _ok(
        {
            "service": "HeavyLift CRM API",
            "version": "v1",
            "auth": ["Bearer token", "existing session"],
            "resources": [
                "/auth/login",
                "/auth/me",
                "/users",
                "/centers",
                "/courses",
                "/leads",
                "/submissions",
                "/followups",
                "/machines",
                "/practicals",
                "/placements",
                "/fees/calculate",
                "/dashboard",
            ],
        }
    )


@api_bp.route("/health", methods=["GET"])
def health():
    return _ok({"status": "healthy", "time": datetime.utcnow().isoformat()})


@api_bp.route("/auth/login", methods=["POST"])
def login():
    try:
        payload = _json_body(required=True)
    except ValueError as exc:
        return _fail(str(exc), 400)

    try:
        username = clean_username(payload.get("username"))
    except ValueError as exc:
        return _fail(str(exc), 400)

    password = str(payload.get("password") or "")
    if not password:
        return _fail("Password is required.", 400)

    client_ip = _client_ip()
    limited, retry_after = rate_limiter.hit(
        f"api.auth.login:{client_ip}",
        Config.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        Config.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not limited:
        return _fail("Too many login attempts.", 429, retry_after=retry_after)

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE username=%s;", (username,))
        user = cur.fetchone()
        if not user or is_lock_active(user.get("locked_until"), datetime.now()) or not verify_password(user["password_hash"], password):
            if user:
                failed_attempts = int(user.get("failed_login_attempts") or 0) + 1
                locked_until = None
                if failed_attempts >= Config.LOGIN_LOCKOUT_THRESHOLD:
                    locked_until = datetime.now() + timedelta(minutes=Config.LOGIN_LOCKOUT_MINUTES)
                cur.execute(
                    "UPDATE users SET failed_login_attempts=%s, locked_until=%s, last_failed_login_at=%s WHERE id=%s;",
                    (failed_attempts, locked_until, datetime.now(), user["id"]),
                )
                close_db(conn)
            else:
                close_db(conn, commit=False)
            return _fail("Invalid credentials.", 401)

        updated_hash = hash_password(password) if needs_password_rehash(user["password_hash"]) else user["password_hash"]
        cur.execute(
            """
            UPDATE users
            SET password_hash=%s,
                failed_login_attempts=0,
                locked_until=NULL,
                last_failed_login_at=NULL
            WHERE id=%s;
            """,
            (updated_hash, user["id"]),
        )
        close_db(conn)

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["location_id"] = user["location_id"]

        token = _token_for_user(user)
        return _ok(
            {
                "token": token,
                "token_type": "Bearer",
                "expires_in": Config.API_TOKEN_TTL_MINUTES * 60,
                "user": _row_to_dict(
                    {
                        "id": user["id"],
                        "username": user["username"],
                        "email": user["email"],
                        "role": user["role"],
                        "location_id": user["location_id"],
                    }
                ),
            },
            msg="Logged in.",
        )
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API login failed for %s", username)
        return _fail("Authentication is temporarily unavailable.", 503)


@api_bp.route("/auth/me", methods=["GET"])
@api_login_required()
def me():
    user = _current_user()
    return _ok({"user": _row_to_dict(user)})


@api_bp.route("/auth/logout", methods=["POST"])
@api_login_required()
def logout():
    # Revoke bearer token if provided
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(None, 1)[1].strip()
    if not token:
        token = request.headers.get("X-API-Token", "").strip() or None
    if token:
        revoked_tokens.add(token)
    session.clear()
    return _ok(msg="Logged out and token revoked.")


@api_bp.route("/users", methods=["GET", "POST"])
@api_login_required("admin", "developer")
def users_collection():
    user = _current_user()
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "GET":
            page, page_size, offset = _page_args()
            cur.execute(
                """
                SELECT u.id,u.username,u.email,u.role,u.location_id,l.name AS location_name,u.created_at
                FROM users u
                LEFT JOIN locations l ON u.location_id=l.id
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s;
                """,
                (page_size, offset),
            )
            return _ok({"items": [_row_to_dict(row) for row in cur.fetchall()], "page": page, "page_size": page_size})

        payload = _json_body(required=True)
        username = clean_username(payload.get("username"))
        email = clean_email(payload.get("email"))
        password = str(payload.get("password") or "")
        if len(password) < 8:
            return _fail("Password must be at least 8 characters.", 400)
        role = clean_choice(payload.get("role", "teacher"), "Role", {"teacher", "admin", "developer"})
        if role == "developer" and user.get("role") != "developer":
            return _fail("Only developers can create developer accounts.", 403)
        location_id = parse_optional_int(payload.get("location_id"), "Location")

        cur.execute("SELECT 1 FROM users WHERE username=%s OR email=%s LIMIT 1;", (username, email))
        if cur.fetchone():
            return _fail("Username or email is already in use.", 409)

        cur.execute(
            "INSERT INTO users (username,email,password_hash,role,location_id) VALUES (%s,%s,%s,%s,%s) RETURNING id;",
            (username, email, hash_password(password), role, location_id),
        )
        new_id = cur.fetchone()["id"]
        close_db(conn)
        return _ok({"id": new_id}, msg="User created.", status=201)
    except ValueError as exc:
        close_db(conn, commit=False)
        return _fail(str(exc), 400)
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API users collection failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/users/<int:user_id>", methods=["GET", "PATCH", "DELETE"])
@api_login_required("admin", "developer")
def user_item(user_id):
    current = _current_user()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT u.id,u.username,u.email,u.role,u.location_id,l.name AS location_name,u.created_at FROM users u LEFT JOIN locations l ON u.location_id=l.id WHERE u.id=%s;",
            (user_id,),
        )
        user = cur.fetchone()
        if not user:
            return _fail("Not found.", 404)

        if request.method == "GET":
            return _ok({"user": _row_to_dict(user)})

        if request.method == "DELETE":
            if user_id == current.get("id"):
                return _fail("Cannot delete yourself.", 400)
            cur.execute("DELETE FROM users WHERE id=%s;", (user_id,))
            close_db(conn)
            return _ok(msg="User deleted.")

        payload = _json_body(required=True)
        username = clean_username(payload.get("username", user["username"]))
        email = clean_email(payload.get("email", user["email"]))
        location_id = parse_optional_int(payload.get("location_id"), "Location")
        cur.execute("SELECT 1 FROM users WHERE username=%s AND id<>%s LIMIT 1;", (username, user_id))
        if cur.fetchone():
            return _fail("Username is already in use.", 409)
        cur.execute("SELECT 1 FROM users WHERE email=%s AND id<>%s LIMIT 1;", (email, user_id))
        if cur.fetchone():
            return _fail("Email is already in use.", 409)
        cur.execute("UPDATE users SET username=%s,email=%s,location_id=%s WHERE id=%s;", (username, email, location_id, user_id))
        close_db(conn)
        return _ok(msg="User updated.")
    except ValueError as exc:
        close_db(conn, commit=False)
        return _fail(str(exc), 400)
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API user item failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/users/<int:user_id>/password", methods=["POST"])
@api_login_required("admin", "developer")
def user_password(user_id):
    current = _current_user()
    if current.get("role") != "developer" and current.get("id") != user_id:
        return _fail("Permission denied.", 403)
    try:
        payload = _json_body(required=True)
    except ValueError as exc:
        return _fail(str(exc), 400)
    new_password = str(payload.get("new_password") or "")
    if len(new_password) < 8:
        return _fail("Password must be at least 8 characters.", 400)

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s;", (hash_password(new_password), user_id))
        close_db(conn)
        return _ok(msg="Password updated.")
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API password update failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/users/<int:user_id>/role", methods=["POST"])
@api_login_required("developer")
def user_role(user_id):
    try:
        payload = _json_body(required=True)
    except ValueError as exc:
        return _fail(str(exc), 400)
    role = clean_choice(payload.get("role"), "Role", {"teacher", "admin", "developer"})
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET role=%s WHERE id=%s;", (role, user_id))
        close_db(conn)
        return _ok(msg="Role updated.")
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API role update failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/centers", methods=["GET", "POST"])
@api_login_required()
def centers_collection():
    user = _current_user()
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "GET":
            page, page_size, offset = _page_args()
            where, params = _scope_clause(user, "id")
            cur.execute(
                f"SELECT id,name,description,position,created_at FROM locations WHERE 1=1{where} ORDER BY position, created_at LIMIT %s OFFSET %s;",
                params + [page_size, offset],
            )
            return _ok({"items": [_row_to_dict(row) for row in cur.fetchall()], "page": page, "page_size": page_size})

        if user.get("role") not in {"admin", "developer"}:
            return _fail("Permission denied.", 403)
        payload = _json_body(required=True)
        name = clean_text(payload.get("name"), "Name", required=True, max_length=100)
        description = clean_optional_text(payload.get("description"), "Description", max_length=500, multiline=True)
        position = parse_optional_int(payload.get("position"), "Position")
        if position is None:
            cur.execute("SELECT COALESCE(MAX(position),0)+1 AS next_position FROM locations;")
            position = cur.fetchone()["next_position"]
        cur.execute("INSERT INTO locations (name,description,position) VALUES (%s,%s,%s) RETURNING id;", (name, description, position))
        new_id = cur.fetchone()["id"]
        close_db(conn)
        return _ok({"id": new_id}, msg="Center created.", status=201)
    except ValueError as exc:
        close_db(conn, commit=False)
        return _fail(str(exc), 400)
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API centers collection failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/centers/reorder", methods=["POST"])
@api_login_required("admin", "developer")
def centers_reorder():
    try:
        payload = _json_body(required=True)
        ids = validate_ordered_ids(payload.get("ids", []))
    except ValueError as exc:
        return _fail(str(exc), 400)
    conn = get_db()
    cur = conn.cursor()
    try:
        for position, center_id in enumerate(ids):
            cur.execute("UPDATE locations SET position=%s WHERE id=%s;", (position, center_id))
        close_db(conn)
        return _ok(msg="Centers reordered.")
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API centers reorder failed")
        return _fail("Unable to process request.", 500)


@api_bp.route("/centers/<int:center_id>", methods=["GET", "PATCH", "DELETE"])
@api_login_required()
def center_item(center_id):
    user = _current_user()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM locations WHERE id=%s;", (center_id,))
        center = cur.fetchone()
        if not center:
            return _fail("Not found.", 404)
        if user.get("role") == "teacher" and user.get("location_id") and center_id != user["location_id"]:
            return _fail("Access denied.", 403)
        if request.method == "GET":
            return _ok({"center": _row_to_dict(center)})
        if user.get("role") not in {"admin", "developer"}:
            return _fail("Permission denied.", 403)
        if request.method == "DELETE":
            cur.execute("DELETE FROM locations WHERE id=%s;", (center_id,))
            close_db(conn)
            return _ok(msg="Center deleted.")
        payload = _json_body(required=True)
        name = clean_text(payload.get("name", center["name"]), "Name", required=True, max_length=100)
        description = clean_optional_text(payload.get("description", center["description"]), "Description", max_length=500, multiline=True)
        cur.execute("UPDATE locations SET name=%s,description=%s WHERE id=%s;", (name, description, center_id))
        close_db(conn)
        return _ok(msg="Center updated.")
    except ValueError as exc:
        close_db(conn, commit=False)
        return _fail(str(exc), 400)
    except Exception:
        close_db(conn, commit=False)
        current_app.logger.exception("API center item failed")
        return _fail("Unable to process request.", 500)
