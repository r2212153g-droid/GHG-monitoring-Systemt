

import sqlite3
import hashlib
import re
import smtplib
import ssl
from pathlib import Path
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / "ghg_monitoring.db")
ph = PasswordHasher()


# ── Connection ────────────────────────────────────────────────
def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


# ── Password helpers ──────────────────────────────────────────
def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Returns (is_valid, needs_rehash)."""
    if stored_hash.startswith("$argon2"):
        try:
            valid = ph.verify(stored_hash, password)
            needs_rehash = ph.check_needs_rehash(stored_hash)
            return valid, needs_rehash
        except VerifyMismatchError:
            return False, False
    # Legacy SHA-256 fallback
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return (legacy == stored_hash), True   # always rehash legacy


# ── Schema setup ──────────────────────────────────────────────
def setup_database(verbose: bool = True):
    conn = get_connection()
    cursor = conn.cursor()

    # users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name        TEXT    NOT NULL,
            username         TEXT    UNIQUE NOT NULL,
            password_hash    TEXT    NOT NULL,
            role             TEXT    NOT NULL CHECK(role IN ('admin','officer','emitter')),
            email            TEXT,
            phone            TEXT,
            emitter_id       INTEGER REFERENCES emitters(id),
            totp_secret      TEXT,
            failed_attempts  INTEGER DEFAULT 0,
            lockout_until    TIMESTAMP,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login       TIMESTAMP,
            is_active        BOOLEAN DEFAULT 1
        )
    """)

    # Safe schema migrations (idempotent)
    for col, defn in [
        ("emitter_id",      "INTEGER"),
        ("totp_secret",     "TEXT"),
        ("failed_attempts", "INTEGER DEFAULT 0"),
        ("lockout_until",   "TIMESTAMP"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass

    # emitters
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emitters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            type            TEXT    NOT NULL,
            location        TEXT,
            contact_person  TEXT,
            contact_phone   TEXT,
            contact_email   TEXT,
            added_by        INTEGER REFERENCES users(id),
            added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col, defn in [
        ("contact_person", "TEXT"),
        ("contact_phone",  "TEXT"),
        ("contact_email",  "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE emitters ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass

    # readings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            emitter_id  INTEGER NOT NULL REFERENCES emitters(id),
            co2         REAL    NOT NULL,
            ch4         REAL    NOT NULL,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recorded_by INTEGER REFERENCES users(id)
        )
    """)

    # alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            emitter_id  INTEGER NOT NULL REFERENCES emitters(id),
            alert_type  TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved    BOOLEAN DEFAULT 0,
            resolved_by INTEGER REFERENCES users(id),
            resolved_at TIMESTAMP
        )
    """)

    # app_settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # compliance_actions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_actions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            emitter_id          INTEGER REFERENCES emitters(id),
            alert_type          TEXT,
            penalty_level       TEXT,
            penalty_amount      REAL,
            action_taken        TEXT,
            report_sent         BOOLEAN DEFAULT 0,
            notification_method TEXT,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        SELECT name, MIN(id), GROUP_CONCAT(id)
        FROM emitters
        GROUP BY name
        HAVING COUNT(*) > 1
    """)
    for _name, canonical_id, ids_csv in cursor.fetchall():
        duplicate_ids = [
            int(emitter_id)
            for emitter_id in ids_csv.split(",")
            if int(emitter_id) != canonical_id
        ]
        for duplicate_id in duplicate_ids:
            for table in ("readings", "alerts", "compliance_actions", "users"):
                cursor.execute(
                    f"UPDATE {table} SET emitter_id=? WHERE emitter_id=?",
                    (canonical_id, duplicate_id),
                )
            cursor.execute("DELETE FROM emitters WHERE id=?", (duplicate_id,))

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_emitters_name_unique
        ON emitters(name)
    """)

    # Default users
    cursor.execute("""
        INSERT OR IGNORE INTO users (full_name, username, password_hash, role, email, phone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("District Administrator", "admin",
          hash_password("admin123"), "admin",
          "admin@makoni.gov.zw", "+263-123-456-789"))

    cursor.execute("""
        INSERT OR IGNORE INTO users (full_name, username, password_hash, role, email, phone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("Environmental Officer", "officer",
          hash_password("officer123"), "officer",
          "officer@makoni.gov.zw", "+263-987-654-321"))

    # Sample emitters
    sample_emitters = [
        ("Makoni District Hospital Incinerator", "Incinerator",  "Makoni District Hospital",
         "Mr. Choto",    "+263 78 415 6520", "R2212153g@msu.student.ac.zw"),
        ("Rural Clinic Generator",               "Generator",    "Chitungwiza Rural Clinic",
         "Ms. Dube",     "+263 77 410 5920", "mwarianesugwandingwa@gmail.com"),
        ("Agricultural Waste Site",              "Agriculture",  "Marondera Farmland",
         "Mr. Ndoro",    "+263 77 111 0003", "ndoro@agric.gov.zw"),
        ("Wetland Methane Source",               "Wetland",      "Save River Basin",
         "Mrs. Mukwena", "+263 77 111 0004", "mukwena@env.gov.zw"),
        ("Transport Depot",                      "Transport",    "Harare Transport Hub",
         "Mr. Shava",    "+263 77 111 0005", "shava@transport.gov.zw"),
        ("Rusape Power Co",                      "Generator",    "Rusape Industrial",
         "Ms. Banda",    "+263 77 111 0006", "banda@power.co.zw"),
        ("Mutasa Cement Plant",                  "Combustion",   "Mutasa North",
         "Mr. Zindoga",  "+263 77 111 0007", "zindoga@cement.co.zw"),
        ("Murewa Abattoir",                      "Agriculture",  "Murewa Town",
         "Mrs. Gumbo",   "+263 77 111 0008", "gumbo@abattoir.co.zw"),
    ]
    for name, type_, location, contact_person, contact_phone, contact_email in sample_emitters:
        cursor.execute("""
            INSERT OR IGNORE INTO emitters (name, type, location, contact_person, contact_phone, contact_email)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, type_, location, contact_person, contact_phone, contact_email))

    conn.commit()
    conn.close()
    if verbose:
        print("Database setup complete!")
        print("  Admin login    -> username: admin    / password: admin123")
        print("  Officer login  -> username: officer  / password: officer123")


# ── Auth ──────────────────────────────────────────────────────
def verify_login(username: str, password: str) -> dict:
    """
    Returns {"user": {...}} on success.
    Returns {"error": "invalid" | "disabled" | "locked", ...} on failure.

    BUG FIXED: original SELECT fetched 14 columns but unpacked only 13,
               causing emitter_id to overwrite totp_secret silently.
    """
    # Ensure schema exists (important when dashboard starts on a fresh DB)
    try:
        get_all_emitters()  # triggers setup_database if needed in dashboard
    except Exception:
        setup_database()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, full_name, username, role, email, phone,
               COALESCE(emitter_id, NULL) AS emitter_id,
               COALESCE(totp_secret, NULL) AS totp_secret,
               password_hash,
               COALESCE(failed_attempts, 0) AS failed_attempts,
               COALESCE(lockout_until, NULL) AS lockout_until,
               COALESCE(created_at, CURRENT_TIMESTAMP) AS created_at,
               COALESCE(last_login, NULL) AS last_login,
               COALESCE(is_active, 1) AS is_active
        FROM users WHERE username = ?
    """, (username,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"error": "invalid"}

    # ── FIXED: unpack all 14 columns in the correct order ────
    (user_id, full_name, uname, role, email, phone,
     emitter_id, totp_secret, password_hash,
     failed_attempts, lockout_until, created_at, last_login, is_active) = row

    if not is_active:
        conn.close()
        return {"error": "disabled"}

    if lockout_until:
        try:
            locked_until_dt = datetime.fromisoformat(lockout_until)
        except ValueError:
            locked_until_dt = None
        if locked_until_dt and locked_until_dt > datetime.now():
            conn.close()
            return {"error": "locked", "until": locked_until_dt.isoformat()}

    valid, needs_rehash = verify_password(password, password_hash)

    if not valid:
        failed_attempts = (failed_attempts or 0) + 1
        if failed_attempts >= 5:
            lockout_until = (datetime.now() + timedelta(minutes=10)).isoformat()
            cursor.execute(
                "UPDATE users SET failed_attempts=?, lockout_until=? WHERE id=?",
                (failed_attempts, lockout_until, user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET failed_attempts=? WHERE id=?",
                (failed_attempts, user_id)
            )
        conn.commit()
        conn.close()
        return {"error": "invalid"}

    # Successful login — reset counters, update last_login
    cursor.execute("""
        UPDATE users SET failed_attempts=0, lockout_until=NULL, last_login=CURRENT_TIMESTAMP
        WHERE id=?
    """, (user_id,))

    # Upgrade legacy SHA-256 hashes to Argon2
    if needs_rehash:
        cursor.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (hash_password(password), user_id))

    conn.commit()
    conn.close()

    return {
        "user": {
            "id":          user_id,
            "full_name":   full_name,
            "username":    uname,
            "role":        role,
            "email":       email,
            "phone":       phone,
            "emitter_id":  emitter_id,     # ← was missing in original
            "totp_secret": totp_secret,
            "created_at":  created_at,
            "last_login":  last_login,
            "is_active":   is_active,
        }
    }


# ── Readings ──────────────────────────────────────────────────
def save_reading(emitter_id: int, co2: float, ch4: float, recorded_by: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO readings (emitter_id, co2, ch4, recorded_by) VALUES (?,?,?,?)",
        (emitter_id, co2, ch4, recorded_by)
    )
    conn.commit()
    conn.close()


def get_all_readings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, e.name AS emitter_name, r.co2, r.ch4,
               r.timestamp, u.username AS recorded_by
        FROM readings r
        JOIN emitters e ON r.emitter_id = e.id
        LEFT JOIN users u ON r.recorded_by = u.id
        ORDER BY r.timestamp DESC
        LIMIT 500
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_readings_by_date_range(start_date: str, end_date: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, e.name AS emitter_name, r.co2, r.ch4,
               r.timestamp, u.username AS recorded_by
        FROM readings r
        JOIN emitters e ON r.emitter_id = e.id
        LEFT JOIN users u ON r.recorded_by = u.id
        WHERE DATE(r.timestamp) BETWEEN ? AND ?
        ORDER BY r.timestamp DESC
    """, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_emissions_statistics(start_date: str = None, end_date: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    base = """
        SELECT e.name,
               AVG(r.co2) AS avg_co2, MAX(r.co2) AS max_co2, MIN(r.co2) AS min_co2,
               AVG(r.ch4) AS avg_ch4, MAX(r.ch4) AS max_ch4, MIN(r.ch4) AS min_ch4,
               COUNT(*)   AS reading_count,
               SUM(r.co2) AS total_co2, SUM(r.ch4) AS total_ch4
        FROM readings r JOIN emitters e ON r.emitter_id = e.id
    """
    if start_date and end_date:
        cursor.execute(base + " WHERE DATE(r.timestamp) BETWEEN ? AND ? GROUP BY e.name ORDER BY avg_co2 DESC",
                       (start_date, end_date))
    else:
        cursor.execute(base + " GROUP BY e.name ORDER BY avg_co2 DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_daily_emissions_trend(emitter_name: str, days: int = 30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE(r.timestamp) AS date,
               AVG(r.co2) AS avg_co2, AVG(r.ch4) AS avg_ch4, COUNT(*) AS reading_count
        FROM readings r JOIN emitters e ON r.emitter_id = e.id
        WHERE e.name = ? AND DATE(r.timestamp) >= DATE('now', ? )
        GROUP BY DATE(r.timestamp)
        ORDER BY date ASC
    """, (emitter_name, f"-{days} days"))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_compliance_statistics(start_date: str = None, end_date: str = None,
                               co2_limit: float = 450, ch4_limit: float = 25):
    conn = get_connection()
    cursor = conn.cursor()
    date_filter = "WHERE DATE(timestamp) BETWEEN ? AND ?" if (start_date and end_date) else ""
    params_base = (start_date, end_date) if (start_date and end_date) else ()

    def count(extra_where, extra_params=()):
        q = f"SELECT COUNT(*) FROM readings {date_filter}"
        q += (" AND " if date_filter else " WHERE ") + extra_where
        cursor.execute(q, params_base + extra_params)
        return cursor.fetchone()[0]

    compliant = count("co2 <= ? AND ch4 <= ?", (co2_limit, ch4_limit))
    warning   = count("((co2 > ? AND co2 <= ?) OR (ch4 > ? AND ch4 <= ?))",
                      (co2_limit * 0.8, co2_limit, ch4_limit * 0.8, ch4_limit))
    critical  = count("(co2 > ? OR ch4 > ?)", (co2_limit, ch4_limit))
    conn.close()
    return {"compliant": compliant, "warning": warning, "critical": critical}


# ── Alerts ────────────────────────────────────────────────────
def save_alert(emitter_id: int, alert_type: str, message: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alerts
        SET resolved=1, resolved_at=CURRENT_TIMESTAMP
        WHERE emitter_id=? AND alert_type<>? AND resolved=0
    """, (emitter_id, alert_type))
    cursor.execute("""
        SELECT id
        FROM alerts
        WHERE emitter_id=? AND alert_type=? AND resolved=0
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
    """, (emitter_id, alert_type))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE alerts
            SET message=?, timestamp=CURRENT_TIMESTAMP
            WHERE id=?
        """, (message, existing[0]))
    else:
        cursor.execute(
            "INSERT INTO alerts (emitter_id, alert_type, message) VALUES (?,?,?)",
            (emitter_id, alert_type, message)
        )
    conn.commit()
    conn.close()


def deduplicate_unresolved_alerts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alerts
        SET resolved=1, resolved_at=CURRENT_TIMESTAMP
        WHERE resolved=0
          AND id NOT IN (
              SELECT MAX(id)
              FROM alerts
              WHERE resolved=0
              GROUP BY emitter_id
          )
    """)
    conn.commit()
    conn.close()


def get_all_alerts():
    deduplicate_unresolved_alerts()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, e.name AS emitter_name, a.alert_type,
               a.message, a.timestamp, a.resolved
        FROM alerts a JOIN emitters e ON a.emitter_id = e.id
        WHERE a.resolved = 0
        ORDER BY a.timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def resolve_alert(alert_id: int, resolved_by: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alerts SET resolved=1, resolved_by=?, resolved_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (resolved_by, alert_id))
    conn.commit()
    conn.close()


# ── Emitters ──────────────────────────────────────────────────
def get_all_emitters() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, type, location, contact_person, contact_phone, contact_email, added_at
        FROM emitters ORDER BY name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "type": r[2], "location": r[3],
         "contact_person": r[4], "contact_phone": r[5],
         "contact_email": r[6], "added_at": r[7]}
        for r in rows
    ]


def get_emitter_by_name(name: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,type,location,contact_person,contact_phone,contact_email,added_at FROM emitters WHERE name=?", (name,))
    r = cursor.fetchone()
    conn.close()
    return {"id":r[0],"name":r[1],"type":r[2],"location":r[3],"contact_person":r[4],"contact_phone":r[5],"contact_email":r[6],"added_at":r[7]} if r else None


def get_emitter_by_id(emitter_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id,name,type,location,contact_person,contact_phone,contact_email,added_at FROM emitters WHERE id=?", (emitter_id,))
    r = cursor.fetchone()
    conn.close()
    return {"id":r[0],"name":r[1],"type":r[2],"location":r[3],"contact_person":r[4],"contact_phone":r[5],"contact_email":r[6],"added_at":r[7]} if r else None


def register_emitter_with_portal(name, type_, location, contact_person,
                                  contact_phone, contact_email, added_by,
                                  username, password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO emitters (name, type, location, contact_person, contact_phone, contact_email, added_by, added_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, type_, location, contact_person, contact_phone, contact_email,
              added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        emitter_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO users (full_name, username, password_hash, role, email, phone, emitter_id)
            VALUES (?,?,?,?,?,?,?)
        """, (name, username, hash_password(password), "emitter",
              contact_email, contact_phone, emitter_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Users ─────────────────────────────────────────────────────
def add_user(full_name, username, password, role, email, phone, emitter_id=None):
    if role not in ("admin", "officer", "emitter"):
        raise ValueError("Role must be admin, officer, or emitter.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (full_name, username, password_hash, role, email, phone, emitter_id)
        VALUES (?,?,?,?,?,?,?)
    """, (full_name, username, hash_password(password), role, email, phone, emitter_id))
    conn.commit()
    conn.close()


def add_officer(full_name, username, password, email, phone):
    add_user(full_name, username, password, "officer", email, phone)


def add_emitter_user(full_name, username, password, email, phone, emitter_id):
    """BUG FIXED: was defined twice in original; kept single canonical version."""
    add_user(full_name, username, password, "emitter", email, phone, emitter_id)


def update_user_contact(user_id, email, phone):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET email=?, phone=? WHERE id=?", (email, phone, user_id))
    conn.commit()
    conn.close()


def change_password(user_id: int, new_password: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash=? WHERE id=?",
                   (hash_password(new_password), user_id))
    conn.commit()
    conn.close()


def get_all_users() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, full_name, username, role, email, phone,
               emitter_id, created_at, last_login, is_active
        FROM users ORDER BY role, full_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id":r[0],"full_name":r[1],"username":r[2],"role":r[3],"email":r[4],
         "phone":r[5],"emitter_id":r[6],"created_at":r[7],"last_login":r[8],"is_active":r[9]}
        for r in rows
    ]


def toggle_user_active(user_id: int, active: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), user_id))
    conn.commit()
    conn.close()


# ── Settings ──────────────────────────────────────────────────
def delete_user(user_id: int, current_user_id: int) -> tuple[bool, str]:
    if user_id == current_user_id:
        return False, "You cannot delete your own logged-in account."

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username, role, COALESCE(is_active, 1) FROM users WHERE id=?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, f"User #{user_id} was not found."

        username, role, is_active = row
        if role == "admin" and is_active:
            cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1")
            active_admins = cursor.fetchone()[0]
            if active_admins <= 1:
                return False, "You cannot delete the last active admin account."

        cursor.execute("UPDATE readings SET recorded_by=NULL WHERE recorded_by=?", (user_id,))
        cursor.execute("UPDATE alerts SET resolved_by=NULL WHERE resolved_by=?", (user_id,))
        cursor.execute("UPDATE emitters SET added_by=NULL WHERE added_by=?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        return True, f"User '{username}' deleted."
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO app_settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM app_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


# ── Compliance actions ────────────────────────────────────────
def add_compliance_action(emitter_id, alert_type, penalty_level,
                           penalty_amount, action_taken, report_sent,
                           notification_method):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO compliance_actions
            (emitter_id, alert_type, penalty_level, penalty_amount,
             action_taken, report_sent, notification_method)
        VALUES (?,?,?,?,?,?,?)
    """, (emitter_id, alert_type, penalty_level, penalty_amount,
          action_taken, report_sent, notification_method))
    conn.commit()
    conn.close()


def get_all_compliance_actions():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, e.name AS emitter_name, c.alert_type, c.penalty_level,
               c.penalty_amount, c.action_taken, c.report_sent,
               c.notification_method, c.created_at
        FROM compliance_actions c
        LEFT JOIN emitters e ON c.emitter_id = e.id
        ORDER BY c.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ── Password validation ────────────────────────────────────────
def is_strong_password(password: str) -> tuple[bool, str]:
    """Check if password meets security requirements."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain an uppercase letter."
    if not re.search(r'[0-9]', password):
        return False, "Password must contain a digit."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        return False, "Password must contain a special character."
    return True, "Password is strong."


# ── Notification settings ──────────────────────────────────────
def get_notification_settings() -> dict:
    """Get SMTP, email-to-SMS gateway, and Twilio configuration."""
    settings = get_all_settings()
    return {
        # Email (SMTP)
        "smtp_host":   settings.get("smtp_host", "smtp.gmail.com"),
        "smtp_port":   int(settings.get("smtp_port", "587")),
        "smtp_user":   settings.get("smtp_user", ""),
        "smtp_pass":   settings.get("smtp_pass", ""),
        "smtp_from":   settings.get("smtp_from", ""),

        # Legacy SMS (email-to-SMS gateway)
        "sms_gateway": settings.get("sms_gateway", ""),

        # Twilio SMS
        "twilio_account_sid": settings.get("twilio_account_sid", ""),
        "twilio_auth_token":  settings.get("twilio_auth_token", ""),
        "twilio_from_phone":  settings.get("twilio_from_phone", ""),
    }



def save_notification_settings(notif: dict):
    """Save SMTP, email-to-SMS gateway, and Twilio configuration."""
    # Email (SMTP)
    set_setting("smtp_host",   notif.get("smtp_host", ""))
    set_setting("smtp_port",   str(notif.get("smtp_port", "587")))
    set_setting("smtp_user",   notif.get("smtp_user", ""))
    set_setting("smtp_pass",   notif.get("smtp_pass", ""))
    set_setting("smtp_from",   notif.get("smtp_from", ""))

    # Legacy SMS (email-to-SMS gateway)
    set_setting("sms_gateway", notif.get("sms_gateway", ""))

    # Twilio SMS
    set_setting("twilio_account_sid", notif.get("twilio_account_sid", ""))
    set_setting("twilio_auth_token",  notif.get("twilio_auth_token",  ""))
    set_setting("twilio_from_phone",  notif.get("twilio_from_phone",  ""))



# ── Email & SMS delivery ───────────────────────────────────────
def send_email_message(smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from,
                       recipient, subject, body):
    """Send email via SMTP."""
    smtp_port = int(smtp_port)
    smtp_from = (smtp_from or smtp_user or "").strip()
    recipient = (recipient or "").strip()

    if not smtp_host:
        raise ValueError("SMTP host is required.")
    if not recipient:
        raise ValueError("Recipient email is required.")
    if not smtp_from:
        raise ValueError("Sender email is required.")

    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    server = None
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
            server.ehlo()
            if smtp_port == 587 or server.has_extn("starttls"):
                server.starttls(context=context)
                server.ehlo()

        if smtp_user or smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError("SMTP authentication failed. Check the username and app password.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError(f"SMTP send failed: {e}") from e
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                server.close()


def _normalise_gateway_phone(phone: str) -> str:
    """Return a gateway-safe phone local-part, e.g. +263 77... -> 26377..."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        raise ValueError("Phone number is required for SMS gateway delivery.")
    return digits


def send_sms_via_gateway(smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from,
                         phone, gateway, message):
    """Send SMS via email-to-SMS gateway."""
    try:
        gateway = (gateway or "").strip().lstrip("@")
        if not gateway:
            raise ValueError("SMS gateway domain is required.")
        sms_address = f"{_normalise_gateway_phone(phone)}@{gateway}"
        send_email_message(smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from,
                          sms_address, "SMS", message)
    except Exception as e:
        print(f"SMS error: {e}")
        raise


# ── Report generation ──────────────────────────────────────────
def build_report(df) -> dict:
    """Generate compliance report from DataFrame."""
    summary = {
        "total_emitters": len(df),
        "compliant": int((df["Status"] == "Compliant").sum()),
        "warning": int((df["Status"] == "Warning").sum()),
        "critical": int((df["Status"] == "Critical").sum()),
        "avg_co2": round(df["CO₂ (ppm)"].mean(), 1),
        "avg_ch4": round(df["CH₄ (ppm)"].mean(), 1),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    csv = df.drop(columns=["_eid"]).to_csv(index=False).encode()
    return {"summary": summary, "csv": csv}


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    setup_database()
