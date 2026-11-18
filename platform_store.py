"""One private SQLite database per Streamlit session, never shared across visitors."""
import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from risk_engine import DEFAULTS, RULE_FIELDS

ROLES = ("Yönetici", "İnceleyen", "Görüntüleyen")


def initialize():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE users (name TEXT PRIMARY KEY COLLATE NOCASE, role TEXT, salt BLOB, digest BLOB);
        CREATE TABLE settings (id INTEGER PRIMARY KEY, data TEXT);
        CREATE TABLE cases (transaction_id TEXT PRIMARY KEY, status TEXT, analyst TEXT,
          responsible_unit TEXT, review_note TEXT, action_taken TEXT, evidence_note TEXT, updated TEXT);
        CREATE TABLE audit (time TEXT, actor TEXT, event TEXT, detail TEXT);
    """)
    with db:
        db.execute("INSERT INTO settings VALUES (1,?)", (json.dumps(DEFAULTS),))
        db.execute("INSERT INTO users VALUES ('demo',?,NULL,NULL)", (ROLES[0],))
        log(db, "demo", "Oturum açıldı", "Özel demo alanı")
    return db


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(db, actor, event, detail):
    db.execute("INSERT INTO audit VALUES (?,?,?,?)", (now(), actor, event, detail))


def require(db, actor, roles):
    row = db.execute("SELECT role FROM users WHERE name=?", (actor,)).fetchone()
    if not row or row[0] not in roles:
        raise PermissionError("Bu işlem için yetki gerekiyor.")


def create_user(db, actor, name, password, role):
    require(db, actor, ROLES[:1])
    name = name.strip()
    if not (1 <= len(name) <= 48 and len(password) >= 8 and role in ROLES):
        raise ValueError("Bir kullanıcı adı, geçerli rol ve en az 8 karakterli parola girin.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    with db:
        try:
            db.execute("INSERT INTO users VALUES (?,?,?,?)", (name, role, salt, digest))
        except sqlite3.IntegrityError as error:
            raise ValueError("Bu kullanıcı adı kayıtlı.") from error
        log(db, actor, "Kullanıcı oluşturuldu", name)


def authenticate(db, name, password):
    row = db.execute("SELECT * FROM users WHERE name=?", (name.strip(),)).fetchone()
    if row and row["salt"] and hmac.compare_digest(row["digest"], hashlib.pbkdf2_hmac("sha256", password.encode(), row["salt"], 600000)):
        with db:
            log(db, row["name"], "Giriş", row["role"])
        return (row["name"], row["role"])
    return None


def get_rules(db):
    return json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])


def save_rules(db, actor, rules):
    require(db, actor, ROLES[:1])
    if set(rules) != set(DEFAULTS) or any(not isinstance(rules[k], int) or not lo <= rules[k] <= hi for k, (_, _, lo, hi) in RULE_FIELDS.items()):
        raise ValueError("Kural eşikleri geçersiz.")
    with db:
        db.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(rules),))
        log(db, actor, "Kurallar güncellendi", json.dumps(rules))


def audit(db, actor):
    require(db, actor, ROLES[:1])
    return pd.read_sql_query("SELECT * FROM audit ORDER BY rowid DESC", db)


def backup(db, actor):
    require(db, actor, ROLES[:1])
    copy = sqlite3.connect(":memory:")
    try:
        db.backup(copy)
        with copy:
            copy.execute("UPDATE users SET salt=NULL,digest=NULL")
        copy.execute("VACUUM")
        return copy.serialize()
    finally:
        copy.close()
