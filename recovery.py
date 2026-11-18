"""Read this demo's portable SQLite backup into a fresh, isolated workspace."""
import json
import sqlite3
from datetime import datetime

from case_store import CASE_STATUSES
from platform_store import ROLES, initialize, log, require
from platform_store import DEFAULTS, RULE_FIELDS

MAX_BYTES = 12 * 1024 * 1024


def string(value, limit):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ValueError("Yedekte geçersiz bir alan var.")
    return value


def timestamp(value):
    return datetime.fromisoformat(string(value, 48)).isoformat()


def schema(db):
    return db.execute(
        "SELECT type,name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()


def recover(current, actor, data, valid_ids, legacy_ids=None):
    require(current, actor, ROLES[:1])
    if not 0 < len(data) <= MAX_BYTES or not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("Bu dosya geçerli bir demo yedeği değil.")
    source = sqlite3.connect(":memory:")
    result = initialize()
    try:
        source.deserialize(data)
        source.execute("PRAGMA trusted_schema=OFF")
        source.execute("PRAGMA query_only=ON")
        source.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES)
        version = source.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 2):
            raise ValueError("Desteklenmeyen yedek sürümü.")
        if version == 0 and legacy_ids is not None:
            valid_ids = legacy_ids
        if schema(source) != [tuple(row) for row in schema(result)]:
            raise ValueError("Yedek şeması bu uygulamaya ait değil.")
        if source.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            raise ValueError("Yedek bütünlük kontrolünü geçemedi.")
        row = source.execute("SELECT data FROM settings WHERE id=1").fetchone()
        rules = json.loads(string(row[0], 4096)) if row else {}
        if not isinstance(rules, dict) or set(rules) != set(DEFAULTS) or any(
            type(rules[k]) is not int or not lo <= rules[k] <= hi
            for k, (_, _, lo, hi) in RULE_FIELDS.items()
        ):
            raise ValueError("Yedekte geçersiz kural eşikleri var.")
        with result:
            result.execute(f"PRAGMA user_version={version}")
            result.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(rules),))
            for name, role in source.execute("SELECT name,role FROM users"):
                if not string(name, 48).strip() or role not in ROLES:
                    raise ValueError("Yedekte geçersiz bir kullanıcı var.")
                if name.casefold() != "demo":
                    result.execute("INSERT INTO users VALUES (?,?,NULL,NULL)", (name, role))
            for row in source.execute("SELECT * FROM cases"):
                tx, status, *fields, updated = row
                if tx not in valid_ids or status not in CASE_STATUSES:
                    raise ValueError("Vaka, örnek işlem veya durum listesiyle eşleşmedi.")
                result.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)",
                               (tx, status, *(string(v, 1000) for v in fields), timestamp(updated)))
            result.execute("DELETE FROM audit")
            for when, who, event, detail in source.execute("SELECT time,actor,event,detail FROM audit ORDER BY rowid"):
                result.execute("INSERT INTO audit VALUES (?,?,?,?)",
                               (timestamp(when), string(who, 48), string(event, 96), string(detail, 4096)))
            log(result, "demo", "Yedek geri yüklendi", "Kayıtlar özel oturuma aktarıldı.")
        return result
    except Exception:
        result.close()
        raise
    finally:
        source.close()
