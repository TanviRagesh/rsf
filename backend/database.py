"""
database.py — PostgreSQL Schema & Connection for HeavyLift CRM

This module uses PostgreSQL through psycopg2 with a ThreadedConnectionPool
when DB_ENGINE=postgres. If importing psycopg2 fails, or DB_ENGINE=sqlite,
a lightweight SQLite fallback is used. The SQLite wrapper adapts parameter
placeholders and returns dict-like rows so the rest of the codebase doesn't
need changes.
"""
import os
import sqlite3
from .config import Config
from .security import hash_password

_USE_SQLITE = False
_pool = None


def _postgres_fallback_allowed():
    return Config.DB_ALLOW_SQLITE_FALLBACK or Config.DB_ENGINE == "sqlite"

try:
    import psycopg2, psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
except Exception:
    psycopg2 = None
    _USE_SQLITE = True

try:
    if Config.DB_ENGINE == "sqlite":
        _USE_SQLITE = True
except Exception:
    pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SQLITE_PATH = os.path.join(BASE_DIR, "heavy_dev.db")


def _db_kwargs():
    return {
        "host": Config.DB_HOST,
        "port": Config.DB_PORT,
        "dbname": Config.DB_NAME,
        "user": Config.DB_USER,
        "password": Config.DB_PASS,
        "connect_timeout": Config.DB_CONNECT_TIMEOUT,
        "cursor_factory": psycopg2.extras.RealDictCursor,
    }


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=Config.DB_POOL_MIN_CONN,
            maxconn=Config.DB_POOL_MAX_CONN,
            **_db_kwargs(),
        )
    return _pool


def _migrate_inquiry_attachment_columns(cur):
    attachment_specs = {
        "student_photo": {
            "legacy_types": ["student_photo"],
            "columns": {
                "file_path": "student_photo_file_path",
                "original_filename": "student_photo_original_filename",
                "stored_filename": "student_photo_stored_filename",
                "mime_type": "student_photo_mime_type",
                "file_size": "student_photo_file_size",
            },
        },
        "govt_id": {
            "legacy_types": ["govt_id", "govt_id_front", "govt_id_back"],
            "columns": {
                "file_path": "govt_id_file_path",
                "original_filename": "govt_id_original_filename",
                "stored_filename": "govt_id_stored_filename",
                "mime_type": "govt_id_mime_type",
                "file_size": "govt_id_file_size",
            },
        },
    }

    files_to_delete = []
    for spec in attachment_specs.values():
        placeholders = ",".join(["%s"] * len(spec["legacy_types"]))
        cur.execute(
            f"SELECT inquiry_id, original_filename, stored_filename, file_path, mime_type, file_size FROM inquiry_documents WHERE document_type IN ({placeholders}) ORDER BY inquiry_id, created_at DESC, id DESC;",
            spec["legacy_types"],
        )
        rows = cur.fetchall()
        if not rows:
            continue

        grouped = {}
        for row in rows:
            grouped.setdefault(row["inquiry_id"], []).append(row)

        for inquiry_id, docs in grouped.items():
            cur.execute(
                "SELECT id, student_photo_file_path, govt_id_file_path FROM inquiries WHERE id=%s;",
                (inquiry_id,),
            )
            inquiry = cur.fetchone() or {}
            latest = docs[0]
            keep_path = inquiry.get(spec["columns"]["file_path"]) or latest.get("file_path")

            if latest.get("file_path") and not inquiry.get(spec["columns"]["file_path"]):
                column_map = spec["columns"]
                cur.execute(
                    f"UPDATE inquiries SET {column_map['file_path']}=%s, {column_map['original_filename']}=%s, {column_map['stored_filename']}=%s, {column_map['mime_type']}=%s, {column_map['file_size']}=%s WHERE id=%s;",
                    (
                        latest.get("file_path"),
                        latest.get("original_filename"),
                        latest.get("stored_filename"),
                        latest.get("mime_type"),
                        latest.get("file_size"),
                        inquiry_id,
                    ),
                )

            cur.execute(
                f"DELETE FROM inquiry_documents WHERE inquiry_id=%s AND document_type IN ({placeholders});",
                [inquiry_id, *spec["legacy_types"]],
            )

            for doc in docs:
                file_path = doc.get("file_path")
                if file_path and file_path != keep_path:
                    files_to_delete.append(file_path)

    return files_to_delete


class SQLiteCursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        if params is None:
            params = []
        # SQLite doesn't support Postgres RETURNING clauses; remove them
        s = sql
        had_returning = False
        if "RETURNING" in s.upper():
            # strip RETURNING ... clause
            parts = s.rsplit("RETURNING", 1)
            s = parts[0]
            had_returning = True
        sql2 = s.replace("%s", "?")
        self._last_had_returning = had_returning
        return self._cur.execute(sql2, params)

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            # If the last statement was an INSERT with RETURNING (stripped above),
            # return the last inserted id so callers expecting {'id': ...} work.
            if getattr(self, "_last_had_returning", False):
                try:
                    return {"id": self._cur.lastrowid}
                except Exception:
                    return None
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class SQLiteConn:
    def __init__(self, path=_SQLITE_PATH):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def cursor(self):
        return SQLiteCursor(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def get_db():
    global _USE_SQLITE
    if _USE_SQLITE:
        return SQLiteConn()
    try:
        return _get_pool().getconn()
    except Exception:
        if _postgres_fallback_allowed():
            # Use SQLite only when it was explicitly requested or allowed.
            _USE_SQLITE = True
            return SQLiteConn()
        raise


def close_db(conn, commit=True):
    if not conn:
        return
    if _USE_SQLITE:
        try:
            if commit:
                conn.commit()
            else:
                conn.rollback()
        finally:
            conn.close()
        return
    try:
        if commit:
            conn.commit()
        else:
            conn.rollback()
    finally:
        _get_pool().putconn(conn)


def _normalize_sql_for_sqlite(sql: str) -> str:
    s = sql
    s = s.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    s = s.replace("NOW()", "CURRENT_TIMESTAMP")
    s = s.replace("TIMESTAMP", "TEXT")
    s = s.replace("NUMERIC", "REAL")
    s = s.replace("BOOLEAN", "INTEGER")
    s = s.replace("VARCHAR", "TEXT")
    return s


def bootstrap_user(username=None, email=None, password=None, role=None):
    username = (username or Config.BOOTSTRAP_USERNAME).strip()
    email = (email or Config.BOOTSTRAP_EMAIL).strip()
    password = password or Config.BOOTSTRAP_PASSWORD
    role = (role or Config.BOOTSTRAP_ROLE).strip().lower()

    if not (username and email and password):
        return False
    if role not in {"teacher", "admin", "developer"}:
        raise ValueError("BOOTSTRAP_ROLE must be teacher, admin, or developer.")

    try:
        conn = get_db()
    except Exception:
        if not _postgres_fallback_allowed():
            raise RuntimeError(
                "Unable to connect to PostgreSQL. Set DB_ENGINE=sqlite or DB_ALLOW_SQLITE_FALLBACK=1 for local fallback."
            )
        global _USE_SQLITE
        _USE_SQLITE = True
        conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=%s OR email=%s LIMIT 1;", (username, email))
        if cur.fetchone():
            return False
        cur.execute(
            "INSERT INTO users (username,email,password_hash,role) VALUES (%s,%s,%s,%s);",
            (username, email, hash_password(password), role),
        )
        conn.commit()
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass
        close_db(conn, commit=False)


def init_db():
    try:
        conn = get_db()
    except Exception:
        if not _postgres_fallback_allowed():
            raise RuntimeError(
                "Unable to initialize the database because PostgreSQL is unreachable. "
                "Check DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASS."
            )
        global _USE_SQLITE
        _USE_SQLITE = True
        conn = get_db()
    cur = conn.cursor()

    def exec_sql(sql):
        if _USE_SQLITE:
            sql = _normalize_sql_for_sqlite(sql)
        cur.execute(sql)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      VARCHAR(80)  UNIQUE NOT NULL,
            email         VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role          VARCHAR(20)  NOT NULL DEFAULT 'admin',
            location_id   INTEGER,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until  TIMESTAMP,
            last_failed_login_at TIMESTAMP,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT role_chk CHECK (role IN ('teacher','admin','developer'))
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS locations (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS courses (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            description TEXT,
            location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            fees        NUMERIC(10,2) NOT NULL DEFAULT 0,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS machines (
            id             SERIAL PRIMARY KEY,
            center_id      INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            machine_name   VARCHAR(150) NOT NULL,
            machine_type   VARCHAR(100),
            machine_number VARCHAR(100),
            capacity       VARCHAR(50),
            fuel_type      VARCHAR(50),
            status         VARCHAR(50) NOT NULL DEFAULT 'AVAILABLE',
            remarks        TEXT,
            is_deleted     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS offers (
            id             SERIAL PRIMARY KEY,
            name           VARCHAR(100) NOT NULL,
            description    TEXT,
            discount_type  VARCHAR(10) NOT NULL DEFAULT 'flat',
            discount_value NUMERIC(10,2) NOT NULL DEFAULT 0,
            valid_from     DATE,
            valid_to       DATE,
            location_id    INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT dtype_chk CHECK (discount_type IN ('flat','percent'))
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(120) NOT NULL,
            gender           VARCHAR(10),
            mobile           VARCHAR(20)  NOT NULL,
            location_id      INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            city             VARCHAR(80),
            state            VARCHAR(80),
            course_id        INTEGER REFERENCES courses(id) ON DELETE SET NULL,
            offer_id         INTEGER REFERENCES offers(id) ON DELETE SET NULL,
            inquiry_date     DATE NOT NULL DEFAULT CURRENT_DATE,
            followup_date    DATE,
            admission_date   DATE,
            status           VARCHAR(20) NOT NULL DEFAULT 'Open',
            fees_total       NUMERIC(10,2) DEFAULT 0,
            fees_paid        NUMERIC(10,2) DEFAULT 0,
            ref1_name        VARCHAR(100),
            ref1_type        VARCHAR(30),
            ref1_mobile      VARCHAR(20),
            ref1_amount_paid NUMERIC(10,2) DEFAULT 0,
            ref2_name        VARCHAR(100),
            ref2_type        VARCHAR(30),
            ref2_mobile      VARCHAR(20),
            ref2_amount_paid NUMERIC(10,2) DEFAULT 0,
            ref3_name        VARCHAR(100),
            ref3_type        VARCHAR(30),
            ref3_mobile      VARCHAR(20),
            ref3_amount_paid NUMERIC(10,2) DEFAULT 0,
            emergency1_name  VARCHAR(100),
            emergency1_mobile VARCHAR(20),
            emergency1_relation VARCHAR(20),
            emergency2_name  VARCHAR(100),
            emergency2_mobile VARCHAR(20),
            emergency2_relation VARCHAR(20),
            emergency3_name  VARCHAR(100),
            emergency3_mobile VARCHAR(20),
            emergency3_relation VARCHAR(20),
            student_photo_file_path TEXT,
            student_photo_original_filename VARCHAR(255),
            student_photo_stored_filename VARCHAR(255),
            student_photo_mime_type VARCHAR(100),
            student_photo_file_size INTEGER,
            govt_id_file_path TEXT,
            govt_id_original_filename VARCHAR(255),
            govt_id_stored_filename VARCHAR(255),
            govt_id_mime_type VARCHAR(100),
            govt_id_file_size INTEGER,
            assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT status_chk CHECK (status IN ('Open','Converted','Closed'))
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS followups (
            id             SERIAL PRIMARY KEY,
            inquiry_id     INTEGER NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
            conversation   TEXT,
            followup_date  DATE,
            status         VARCHAR(20) NOT NULL DEFAULT 'Open',
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS whatsapp_msgs (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            description TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          SERIAL PRIMARY KEY,
            title       VARCHAR(200) NOT NULL,
            message     TEXT,
            target_role VARCHAR(20),
            is_read     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS inquiry_documents (
            id                SERIAL PRIMARY KEY,
            inquiry_id        INTEGER NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
            document_type     VARCHAR(40) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            stored_filename   VARCHAR(255) NOT NULL,
            file_path         TEXT NOT NULL,
            mime_type         VARCHAR(100),
            file_size         INTEGER,
            created_at        TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS submissions (
            id             SERIAL PRIMARY KEY,
            name           VARCHAR(120) NOT NULL,
            mobile         VARCHAR(20) NOT NULL,
            email          VARCHAR(120),
            center_id      INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            course_id      INTEGER REFERENCES courses(id) ON DELETE SET NULL,
            source         VARCHAR(80) DEFAULT 'web',
            message        TEXT,
            status         VARCHAR(20) NOT NULL DEFAULT 'new',
            converted_inquiry_id INTEGER REFERENCES inquiries(id) ON DELETE SET NULL,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT submission_status_chk CHECK (status IN ('new','reviewing','converted','closed'))
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS trainer_practicals (
            id             SERIAL PRIMARY KEY,
            center_id      INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            course_id      INTEGER REFERENCES courses(id) ON DELETE SET NULL,
            trainer_name   VARCHAR(120) NOT NULL,
            practical_date DATE NOT NULL,
            topic          VARCHAR(200) NOT NULL,
            status         VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            notes          TEXT,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT practical_status_chk CHECK (status IN ('scheduled','completed','cancelled'))
        );
    """)

    exec_sql("""
        CREATE TABLE IF NOT EXISTS placements (
            id             SERIAL PRIMARY KEY,
            inquiry_id     INTEGER REFERENCES inquiries(id) ON DELETE SET NULL,
            candidate_name VARCHAR(120) NOT NULL,
            company_name   VARCHAR(160) NOT NULL,
            designation    VARCHAR(120),
            placement_date DATE NOT NULL,
            salary         NUMERIC(12,2) DEFAULT 0,
            notes          TEXT,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    # Performance indexes for the most common production queries.
    for sql in [
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_id ON inquiries(location_id)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_course_id ON inquiries(course_id)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_status ON inquiries(status)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_inquiry_date ON inquiries(inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_followup_date ON inquiries(followup_date)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_status_followup ON inquiries(location_id, status, followup_date)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_course_inquiry_date ON inquiries(course_id, inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_inquiry_date ON inquiries(location_id, inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_followups_inquiry_id_created_at ON followups(inquiry_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_role_read_created_at ON notifications(target_role, is_read, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_center_created_at ON submissions(center_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_status_created_at ON submissions(status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_practicals_center_date ON trainer_practicals(center_id, practical_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_placements_inquiry_date ON placements(inquiry_id, placement_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_inquiry_documents_inquiry_type_created_at ON inquiry_documents(inquiry_id, document_type, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_courses_location_position ON courses(location_id, position, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_locations_position_created_at ON locations(position, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_machines_center_created_at ON machines(center_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_machines_status ON machines(status)",
        "CREATE INDEX IF NOT EXISTS idx_machines_deleted_center ON machines(is_deleted, center_id)",
        "CREATE INDEX IF NOT EXISTS idx_offers_location_active_valid_to ON offers(location_id, is_active, valid_to)",
    ]:
        try:
            if _USE_SQLITE:
                cur.execute(_normalize_sql_for_sqlite(sql))
            else:
                cur.execute(sql)
        except Exception:
            # ignore index creation failures on sqlite or older PG
            pass

    # Safe migrations for existing DBs
    for sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMP",
        "ALTER TABLE locations ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE courses   ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS gender VARCHAR(10)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS city VARCHAR(80)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS state VARCHAR(80)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS followup_date DATE",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS admission_date DATE",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Open'",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS fees_total NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS fees_paid  NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_type VARCHAR(30)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_amount_paid NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_type VARCHAR(30)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_amount_paid NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_type VARCHAR(30)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_amount_paid NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency1_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency1_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency1_relation VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency2_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency2_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency2_relation VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency3_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency3_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS emergency3_relation VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS student_photo_file_path TEXT",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS student_photo_original_filename VARCHAR(255)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS student_photo_stored_filename VARCHAR(255)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS student_photo_mime_type VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS student_photo_file_size INTEGER",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS govt_id_file_path TEXT",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS govt_id_original_filename VARCHAR(255)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS govt_id_stored_filename VARCHAR(255)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS govt_id_mime_type VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS govt_id_file_size INTEGER",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "CREATE TABLE IF NOT EXISTS inquiry_documents (id SERIAL PRIMARY KEY, inquiry_id INTEGER NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE, document_type VARCHAR(40) NOT NULL, original_filename VARCHAR(255) NOT NULL, stored_filename VARCHAR(255) NOT NULL, file_path TEXT NOT NULL, mime_type VARCHAR(100), file_size INTEGER, created_at TIMESTAMP NOT NULL DEFAULT NOW())",
    ]:
        try:
            if _USE_SQLITE:
                # sqlite has limited ALTER TABLE support; skip automatic migrations for sqlite
                if "CREATE TABLE IF NOT EXISTS inquiry_documents" in sql:
                    cur.execute(_normalize_sql_for_sqlite(sql))
                continue
            cur.execute(sql); conn.commit()
        except Exception:
            conn.rollback()

    legacy_files_to_delete = []
    try:
        legacy_files_to_delete = _migrate_inquiry_attachment_columns(cur)
        conn.commit()
    except Exception:
        conn.rollback()

    try:
        cur.close()
    except Exception:
        pass
    close_db(conn)
    for file_path in legacy_files_to_delete:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
    print("HeavyLift CRM database ready.")
