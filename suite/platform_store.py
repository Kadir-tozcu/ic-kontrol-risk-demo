"""Local governance store: users, rules, audit log and backups."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


from suite.workspace import directory, set_tenant, tenant as current_tenant
ROLES = ["Yonetici", "Inceleyen", "Onaylayan", "Denetci", "Goruntuleyen"]
DEFAULT_RULES = {
    "inactivity_days_threshold": 365, "inactivity_points": 25,
    "senior_age": 65, "senior_points": 10, "very_senior_age": 75, "very_senior_points": 20,
    "high_amount": 250000, "high_amount_points": 15,
    "ratio_medium": 3, "ratio_medium_points": 12, "ratio_high": 5, "ratio_high_points": 20,
    "new_recipient_points": 15, "off_hours_start": 20, "off_hours_end": 7, "off_hours_points": 10,
    "reactivation_count": 3, "reactivation_count_points": 15, "inactive_senior_combo_points": 15,
    "daily_amount": 500000, "daily_count": 25, "daily_volume_count_points": 25,
    "elderly_daily_age": 70, "elderly_daily_amount": 1000000, "elderly_daily_points": 25,
    "high_sla_hours": 24, "medium_sla_hours": 72,
}


def _scope(value: str) -> str:return value if current_tenant()=="default" else f"{current_tenant()}|{value}"
def _unscope(value: str) -> str:return str(value).split("|",1)[-1] if "|" in str(value) else str(value)


def connect() -> sqlite3.Connection:
    (directory() / "cases.db").parent.mkdir(exist_ok=True)
    conn = sqlite3.connect((directory() / "cases.db"))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY CHECK(id=1), config_json TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT NOT NULL, username TEXT NOT NULL, action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL, detail TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS custom_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, field1 TEXT NOT NULL, operator1 TEXT NOT NULL, value1 TEXT NOT NULL, field2 TEXT NOT NULL DEFAULT '', operator2 TEXT NOT NULL DEFAULT '', value2 TEXT NOT NULL DEFAULT '', points INTEGER NOT NULL, reason TEXT NOT NULL, action TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS process_rule_overrides (process TEXT NOT NULL, rule_index INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, name TEXT NOT NULL, points INTEGER NOT NULL, action TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(process,rule_index))")
    conn.execute("CREATE TABLE IF NOT EXISTS dynamic_scenarios (id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_key TEXT NOT NULL, version INTEGER NOT NULL, process TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', logic TEXT NOT NULL, conditions_json TEXT NOT NULL, points INTEGER NOT NULL, reason TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'TASLAK', active INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(scenario_key,version))")
    conn.execute("CREATE TABLE IF NOT EXISTS upload_history (id INTEGER PRIMARY KEY AUTOINCREMENT, uploaded_at TEXT NOT NULL, username TEXT NOT NULL, process TEXT NOT NULL, file_name TEXT NOT NULL, file_hash TEXT NOT NULL, row_count INTEGER NOT NULL, error_count INTEGER NOT NULL, status TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS organization_settings (id INTEGER PRIMARY KEY CHECK(id=1), organization_name TEXT NOT NULL, accent_color TEXT NOT NULL, logo BLOB, logo_mime TEXT, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS saved_filters (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, process TEXT NOT NULL, name TEXT NOT NULL, config_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(username,process,name))")
    conn.execute("CREATE TABLE IF NOT EXISTS data_mappings (tenant_id TEXT NOT NULL, process TEXT NOT NULL, source_column TEXT NOT NULL, target_field TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(tenant_id,process,source_column))")
    conn.execute("CREATE TABLE IF NOT EXISTS analysis_runs (run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, process TEXT NOT NULL, file_name TEXT NOT NULL, file_hash TEXT NOT NULL, row_count INTEGER NOT NULL, high_count INTEGER NOT NULL, medium_count INTEGER NOT NULL, low_count INTEGER NOT NULL, scenarios_json TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id,process,file_hash))")
    conn.execute("CREATE TABLE IF NOT EXISTS organizations (tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, accent_color TEXT NOT NULL DEFAULT '#175CD3', logo BLOB, logo_mime TEXT, created_at TEXT NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO organizations(tenant_id,name,created_at) VALUES('default','Risk Ajansı',?)",(datetime.now().isoformat(timespec="seconds"),))
    conn.execute("CREATE TABLE IF NOT EXISTS tenant_rules (tenant_id TEXT PRIMARY KEY, config_json TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)")
    for table in ["users","audit_log","custom_rules","dynamic_scenarios","upload_history","saved_filters"]:
        columns={row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "tenant_id" not in columns:conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
    return conn


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"{salt.hex()}:{digest.hex()}"

def get_data_mapping(process: str) -> dict[str,str]:
    with connect() as conn:
        rows=conn.execute("SELECT source_column,target_field FROM data_mappings WHERE tenant_id=? AND process=?",(current_tenant(),process)).fetchall()
    return dict(rows)

def save_data_mapping(process: str, mapping: dict[str,str], username: str) -> None:
    now=datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        for source,target in mapping.items():
            conn.execute("INSERT INTO data_mappings(tenant_id,process,source_column,target_field,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id,process,source_column) DO UPDATE SET target_field=excluded.target_field,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(current_tenant(),process,str(source),str(target),username,now))
    log_event(username,"VERI_ESLESTIRME_KAYDET","data_mapping",process,f"{len(mapping)} sütun")

def record_analysis_run(process: str, file_name: str, file_hash: str, result, scenarios: list[str], username: str) -> tuple[str,bool]:
    with connect() as conn:
        existing=conn.execute("SELECT run_id FROM analysis_runs WHERE tenant_id=? AND process=? AND file_hash=?",(current_tenant(),process,file_hash)).fetchone()
        if existing:return existing[0],False
        run_id=f"ANL-{datetime.now():%Y%m%d}-{secrets.token_hex(3).upper()}";levels=result["risk_level"].value_counts() if "risk_level" in result else {}
        conn.execute("INSERT INTO analysis_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(run_id,current_tenant(),process,file_name,file_hash,int(len(result)),int(levels.get("YUKSEK",0)),int(levels.get("ORTA",0)),int(levels.get("DUSUK",0)),json.dumps(scenarios,ensure_ascii=False),username,datetime.now().isoformat(timespec="seconds")))
    log_event(username,"ANALIZ_CALISTIR","analysis_run",run_id,f"{process} · {len(result)} kayıt");return run_id,True

def list_analysis_runs(process: str | None=None) -> pd.DataFrame:
    query="SELECT run_id,process,file_name,file_hash,row_count,high_count,medium_count,low_count,scenarios_json,created_by,created_at FROM analysis_runs WHERE tenant_id=?";params=[current_tenant()]
    if process:query+=" AND process=?";params.append(process)
    query+=" ORDER BY created_at DESC"
    with connect() as conn:return pd.read_sql_query(query,conn,params=params)


def has_users() -> bool:
    with connect() as conn:
        return bool(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def create_user(username: str, password: str, role: str, actor: str = "system") -> None:
    username = username.strip()
    if len(username)<3 or role not in ROLES:raise ValueError("Kullanıcı adı en az 3 karakter olmalıdır.")
    validate_password(password,username)
    with connect() as conn:
        conn.execute("INSERT INTO users(username,password_hash,role,active,created_at,tenant_id) VALUES (?, ?, ?, 1, ?, ?)", (username, _hash_password(password), role, datetime.now().isoformat(timespec="seconds"),current_tenant()))
    log_event(actor, "KULLANICI_OLUSTUR", "user", username, role)

def validate_password(password: str, username: str="") -> None:
    common={"password","12345678","123456789","qwerty123","admin123","riskajansi"}
    if len(password)<12:raise ValueError("Parola en az 12 karakter olmalıdır.")
    if password.casefold() in common or (username and username.casefold() in password.casefold()):raise ValueError("Kolay tahmin edilen veya kullanıcı adını içeren parola kullanılamaz.")

def change_password(username: str, current_password: str, new_password: str) -> None:
    if not authenticate(username,current_password):raise ValueError("Mevcut parola hatalı.")
    validate_password(new_password,username)
    with connect() as conn:conn.execute("UPDATE users SET password_hash=? WHERE username=? AND tenant_id=?",(_hash_password(new_password),username,current_tenant()))
    try:
        from suite.v15_security import connect as security_connect,log_security
        with security_connect() as conn:conn.execute("INSERT INTO user_security(username,password_changed_at) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET password_changed_at=excluded.password_changed_at",(username,datetime.now().isoformat(timespec="seconds")))
        log_security(username,"PAROLA_DEGISTIR",True)
    except Exception:pass


def authenticate(username: str, password: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT username, password_hash, role, tenant_id FROM users WHERE username=? AND active=1", (username.strip(),)).fetchone()
    if not row:
        return None
    salt_hex, expected = row[1].split(":", 1)
    actual = _hash_password(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    if not hmac.compare_digest(actual, expected):
        return None
    return {"username": row[0], "role": row[2], "tenant_id":row[3]}


def list_users() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query("SELECT username, role, active, created_at FROM users WHERE tenant_id=? ORDER BY username", conn,params=(current_tenant(),))


def log_event(username: str, action: str, object_type: str, object_id: str, detail: str = "") -> None:
    with connect() as conn:
        conn.execute("INSERT INTO audit_log(event_time,username,action,object_type,object_id,detail,tenant_id) VALUES(?,?,?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), username, action, object_type, str(object_id), detail[:2000],current_tenant()))


def get_audit(limit: int = 1000) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query("SELECT event_time,username,action,object_type,object_id,detail FROM audit_log WHERE tenant_id=? ORDER BY id DESC LIMIT ?", conn, params=(current_tenant(),limit))


def get_rules() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT config_json FROM rules WHERE id=1").fetchone() if current_tenant()=="default" else conn.execute("SELECT config_json FROM tenant_rules WHERE tenant_id=?",(current_tenant(),)).fetchone()
    if not row:
        return DEFAULT_RULES.copy()
    return {**DEFAULT_RULES, **json.loads(row[0])}


def save_rules(config: dict, username: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        old = conn.execute("SELECT config_json FROM rules WHERE id=1").fetchone() if current_tenant()=="default" else conn.execute("SELECT config_json FROM tenant_rules WHERE tenant_id=?",(current_tenant(),)).fetchone()
        if current_tenant()=="default":conn.execute("INSERT INTO rules VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at,updated_by=excluded.updated_by", (json.dumps(config), now, username))
        else:conn.execute("INSERT INTO tenant_rules VALUES(?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at,updated_by=excluded.updated_by",(current_tenant(),json.dumps(config),now,username))
    log_event(username, "KURAL_GUNCELLE", "rule_set", "active", f"once={old[0] if old else 'varsayilan'}; sonra={json.dumps(config)}")


def backup_bytes() -> bytes:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp:
        path = Path(temp) / "export.db"
        target = sqlite3.connect(path)
        source = connect()
        try:
            source.backup(target)
            tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            with target:
                target.execute("UPDATE users SET password_hash='', active=0")
                if "user_security" in tables:
                    target.execute("DELETE FROM user_security")
                if "api_keys" in tables:
                    target.execute("DELETE FROM api_keys")
                if "integration_sources" in tables:
                    target.execute("UPDATE integration_sources SET config_json='{}'")
            target.execute("PRAGMA journal_mode=DELETE")
            target.execute("VACUUM")
        finally:
            target.close()
            source.close()
        return path.read_bytes()


def list_custom_rules(active_only: bool = False) -> pd.DataFrame:
    query = "SELECT * FROM custom_rules WHERE tenant_id=?" + (" AND active=1" if active_only else "") + " ORDER BY id DESC"
    with connect() as conn:
        return pd.read_sql_query(query, conn,params=(current_tenant(),))


def create_custom_rule(name: str, field1: str, operator1: str, value1: str,
                       field2: str, operator2: str, value2: str, points: int,
                       reason: str, action: str, username: str) -> None:
    if not name.strip() or not reason.strip() or not action.strip() or not (1 <= int(points) <= 100):
        raise ValueError("Senaryo adi, gerekce, aksiyon ve 1-100 arasi puan zorunludur.")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO custom_rules(name,field1,operator1,value1,field2,operator2,value2,points,reason,action,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), field1, operator1, str(value1), field2, operator2, str(value2), int(points), reason.strip(), action.strip(), username, datetime.now().isoformat(timespec="seconds"),current_tenant()),
        )
        rule_id = cur.lastrowid
    log_event(username, "OZEL_KURAL_OLUSTUR", "custom_rule", str(rule_id), name)


def set_custom_rule_active(rule_id: int, active: bool, username: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE custom_rules SET active=? WHERE id=?", (int(active), int(rule_id)))
    log_event(username, "OZEL_KURAL_DURUM", "custom_rule", str(rule_id), "aktif" if active else "pasif")


def get_process_rule_overrides(process: str | None = None) -> pd.DataFrame:
    query = "SELECT * FROM process_rule_overrides"
    params = ()
    if process is not None:
        query += " WHERE process=?"
        params = (_scope(process),)
    elif current_tenant()=="default":query += " WHERE process NOT LIKE '%|%'"
    else:query += " WHERE process LIKE ?";params=(current_tenant()+"|%",)
    query += " ORDER BY process, rule_index"
    with connect() as conn:
        result=pd.read_sql_query(query, conn, params=params)
    if len(result):result["process"]=result["process"].map(_unscope)
    return result


def save_process_rule_override(process: str, rule_index: int, active: bool, name: str,
                               points: int, action: str, username: str) -> None:
    if not name.strip() or not action.strip() or not 1 <= int(points) <= 100:
        raise ValueError("Senaryo adı, kontrol aksiyonu ve 1-100 arası risk puanı zorunludur.")
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            "INSERT INTO process_rule_overrides VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(process,rule_index) DO UPDATE SET active=excluded.active,name=excluded.name,points=excluded.points,action=excluded.action,updated_by=excluded.updated_by,updated_at=excluded.updated_at",
            (_scope(process), int(rule_index), int(active), name.strip(), int(points), action.strip(), username, now),
        )
    log_event(username, "SUREC_KURALI_GUNCELLE", "process_rule", f"{process}:{rule_index}", f"aktif={active}; ad={name}; puan={points}")


def list_dynamic_scenarios(process: str | None = None, active_only: bool = False) -> pd.DataFrame:
    query="SELECT * FROM dynamic_scenarios WHERE tenant_id=?";params=[current_tenant()]
    if process is not None:query+=" AND process=?";params.append(process)
    if active_only:query+=" AND active=1 AND status='YAYINDA'"
    query+=" ORDER BY scenario_key, version DESC"
    with connect() as conn:return pd.read_sql_query(query,conn,params=tuple(params))


def save_dynamic_scenario(scenario_key: str, process: str, name: str, description: str,
                          logic: str, conditions: list[dict], points: int, reason: str,
                          action: str, username: str, publish: bool = False) -> int:
    if not name.strip() or not conditions or not reason.strip() or not action.strip():
        raise ValueError("Senaryo adı, en az bir koşul, gerekçe ve kontrol aksiyonu zorunludur.")
    key=scenario_key.strip() or secrets.token_hex(6);now=datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        version=int(conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM dynamic_scenarios WHERE scenario_key=?",(key,)).fetchone()[0])
        if publish:conn.execute("UPDATE dynamic_scenarios SET active=0 WHERE scenario_key=? AND tenant_id=?",(key,current_tenant()))
        conn.execute("INSERT INTO dynamic_scenarios(scenario_key,version,process,name,description,logic,conditions_json,points,reason,action,status,active,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(key,version,process,name.strip(),description.strip(),logic,json.dumps(conditions,ensure_ascii=False),int(points),reason.strip(),action.strip(),"YAYINDA" if publish else "TASLAK",int(publish),username,now,current_tenant()))
    log_event(username,"SENARYO_YAYINLA" if publish else "SENARYO_TASLAK","dynamic_scenario",f"{key}:v{version}",name)
    return version


def publish_dynamic_scenario(row_id: int, username: str) -> None:
    with connect() as conn:
        row=conn.execute("SELECT scenario_key,version,name FROM dynamic_scenarios WHERE id=? AND tenant_id=?",(int(row_id),current_tenant())).fetchone()
        if not row:raise ValueError("Senaryo sürümü bulunamadı.")
        conn.execute("UPDATE dynamic_scenarios SET active=0 WHERE scenario_key=? AND tenant_id=?",(row[0],current_tenant()))
        conn.execute("UPDATE dynamic_scenarios SET active=1,status='YAYINDA' WHERE id=? AND tenant_id=?",(int(row_id),current_tenant()))
    log_event(username,"SENARYO_YAYINLA","dynamic_scenario",f"{row[0]}:v{row[1]}",row[2])


def record_upload(username: str, process: str, file_name: str, file_hash: str,
                  row_count: int, error_count: int, status: str) -> None:
    with connect() as conn:
        exists=conn.execute("SELECT 1 FROM upload_history WHERE username=? AND process=? AND file_hash=? AND tenant_id=?",(username,process,file_hash,current_tenant())).fetchone()
        if not exists:conn.execute("INSERT INTO upload_history(uploaded_at,username,process,file_name,file_hash,row_count,error_count,status,tenant_id) VALUES(?,?,?,?,?,?,?,?,?)",(datetime.now().isoformat(timespec="seconds"),username,process,file_name,file_hash,int(row_count),int(error_count),status,current_tenant()))
    log_event(username,"VERI_YUKLE","upload",file_name,f"surec={process}; satir={row_count}; hata={error_count}; durum={status}")


def list_upload_history(process: str | None = None, limit: int = 200) -> pd.DataFrame:
    query="SELECT uploaded_at,username,process,file_name,row_count,error_count,status FROM upload_history WHERE tenant_id=?";params=[current_tenant()]
    if process is not None:query+=" AND process=?";params.append(process)
    query+=" ORDER BY id DESC LIMIT ?";params.append(int(limit))
    with connect() as conn:return pd.read_sql_query(query,conn,params=tuple(params))


def get_organization_settings() -> dict:
    with connect() as conn:
        if current_tenant()=="default":
            legacy=conn.execute("SELECT organization_name,accent_color,logo,logo_mime FROM organization_settings WHERE id=1").fetchone()
            if legacy:return {"organization_name":legacy[0],"accent_color":legacy[1],"logo":legacy[2],"logo_mime":legacy[3]}
        row=conn.execute("SELECT name,accent_color,logo,logo_mime FROM organizations WHERE tenant_id=?",(current_tenant(),)).fetchone()
    return {"organization_name":row[0],"accent_color":row[1],"logo":row[2],"logo_mime":row[3]} if row else {"organization_name":"Risk Ajansı","accent_color":"#175CD3","logo":None,"logo_mime":None}


def save_organization_settings(name: str, accent: str, logo: bytes | None, logo_mime: str | None, username: str) -> None:
    if not name.strip():raise ValueError("Kurum adı zorunludur.")
    if not accent.startswith("#") or len(accent)!=7:raise ValueError("Geçerli bir renk seçin.")
    old=get_organization_settings();logo_value=logo if logo is not None else old["logo"];mime_value=logo_mime if logo is not None else old["logo_mime"]
    with connect() as conn:
        conn.execute("UPDATE organizations SET name=?,accent_color=?,logo=?,logo_mime=? WHERE tenant_id=?",(name.strip(),accent,logo_value,mime_value,current_tenant()))
        if current_tenant()=="default":conn.execute("INSERT INTO organization_settings VALUES(1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET organization_name=excluded.organization_name,accent_color=excluded.accent_color,logo=excluded.logo,logo_mime=excluded.logo_mime,updated_at=excluded.updated_at,updated_by=excluded.updated_by",(name.strip(),accent,logo_value,mime_value,datetime.now().isoformat(timespec="seconds"),username))
    log_event(username,"KURUM_AYARLARI","organization","1",name)


def save_filter(username: str, process: str, name: str, config: dict) -> None:
    if not name.strip():raise ValueError("Filtre adı zorunludur.")
    with connect() as conn:conn.execute("INSERT INTO saved_filters(username,process,name,config_json,created_at,tenant_id) VALUES(?,?,?,?,?,?) ON CONFLICT(username,process,name) DO UPDATE SET config_json=excluded.config_json,created_at=excluded.created_at,tenant_id=excluded.tenant_id",(username,process,name.strip(),json.dumps(config,ensure_ascii=False),datetime.now().isoformat(timespec="seconds"),current_tenant()))


def list_saved_filters(username: str, process: str) -> pd.DataFrame:
    with connect() as conn:return pd.read_sql_query("SELECT id,name,config_json,created_at FROM saved_filters WHERE username=? AND process=? AND tenant_id=? ORDER BY name",conn,params=(username,process,current_tenant()))


def delete_saved_filter(filter_id: int, username: str) -> None:
    with connect() as conn:conn.execute("DELETE FROM saved_filters WHERE id=? AND username=? AND tenant_id=?",(int(filter_id),username,current_tenant()))


def create_organization(name: str, admin_username: str, admin_password: str, actor: str) -> str:
    if len(name.strip())<2:raise ValueError("Kurum adı zorunludur.")
    tenant_id="org_"+secrets.token_hex(5);now=datetime.now().isoformat(timespec="seconds")
    with connect() as conn:conn.execute("INSERT INTO organizations(tenant_id,name,created_at) VALUES(?,?,?)",(tenant_id,name.strip(),now))
    previous=current_tenant()
    try:set_tenant(tenant_id);create_user(admin_username,admin_password,"Yonetici",actor)
    finally:set_tenant(previous)
    log_event(actor,"KURUM_OLUSTUR","organization",tenant_id,name);return tenant_id


def list_organizations() -> pd.DataFrame:
    with connect() as conn:return pd.read_sql_query("SELECT tenant_id,name,active,created_at FROM organizations ORDER BY name",conn)


def pause_dynamic_scenario(key, process, username):
    with connect() as conn:
        conn.execute("UPDATE dynamic_scenarios SET active=0, status='PASIF' WHERE tenant_id=? AND process=? AND scenario_key=? AND active=1",
                     (current_tenant(), process, key))
    log_event(username, "SENARYO_PASIF", "dynamic_scenario", key, process)


SCENARIO_FIELDS = ["scenario_key", "version", "name", "description", "logic", "points", "reason", "action", "status", "active"]


def scenario_package(process):
    versions = []
    for row in list_dynamic_scenarios(process).to_dict("records"):
        entry = {key: row[key] for key in SCENARIO_FIELDS}
        entry["conditions"] = json.loads(row["conditions_json"])
        versions.append(entry)
    return {"format": "risk-ajansi-senaryo-v1", "process": process, "versions": versions}


def restore_scenario_package(package, process, username):
    from suite.v10_features import OPERATORS

    if not isinstance(package, dict) or package.get("format") != "risk-ajansi-senaryo-v1" or package.get("process") != process:
        raise ValueError("Dosya biçimi veya seçili süreç uyuşmuyor.")
    versions = package.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("Dosyada senaryo sürümü bulunamadı.")
    existing = {}
    active = set()
    for row in versions:
        if not isinstance(row, dict) or not all(k in row for k in SCENARIO_FIELDS + ["conditions"]):
            raise ValueError("Senaryo tanımı eksik.")
        key = row["scenario_key"]
        if not all(isinstance(row[k], str) for k in ("scenario_key","name","description","reason","action")) or not all(row[k].strip() for k in ("scenario_key","name","reason","action")):
            raise ValueError("Senaryo metinleri eksik veya geçersiz.")
        if type(row["version"]) != int or not 1 <= row["version"] < 2**63 or type(row["points"]) != int or not 1 <= row["points"] <= 100:
            raise ValueError("Sürüm veya puan geçersiz.")
        if row["logic"] not in ("VE","VEYA") or row["status"] not in ("YAYINDA","TASLAK","PASIF") or row["active"] not in (0,1):
            raise ValueError("Senaryo durumu geçersiz.")
        conditions = row["conditions"]
        if not isinstance(conditions, list) or not conditions or not all(isinstance(c,dict) and isinstance(c.get("field"),str) and c["field"] and c.get("operator") in tuple(OPERATORS.values()) and isinstance(c.get("value",""),(str,int,float,bool)) for c in conditions):
            raise ValueError("Senaryo koşulları geçersiz.")
        by_version = existing.setdefault(key, {})
        if row["version"] in by_version or row["active"] and (key in active or row["status"] != "YAYINDA"):
            raise ValueError("Dosyada çakışan sürümler var.")
        by_version[row["version"]] = row
        if row["active"]:
            active.add(key)
    added = 0
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        for key, by_version in existing.items():
            stored = conn.execute("SELECT * FROM dynamic_scenarios WHERE scenario_key=?", (key,)).fetchall()
            for old in stored:
                item = by_version.get(old["version"])
                if old["tenant_id"] != current_tenant() or old["process"] != process or item is None or any(old[k] != item[k] for k in SCENARIO_FIELDS) or json.loads(old["conditions_json"]) != item["conditions"]:
                    raise ValueError("Aynı senaryonun farklı bir sürümü bu oturumda mevcut. Yedeği boş bir oturumda açın.")
            saved = {old["version"] for old in stored}
            for version, item in by_version.items():
                if version in saved:
                    continue
                values = [item[k] for k in SCENARIO_FIELDS]
                conn.execute(f"INSERT INTO dynamic_scenarios ({','.join(SCENARIO_FIELDS)},conditions_json,process,tenant_id,created_by,created_at) VALUES ({','.join(['?']*15)})",
                             (*values,json.dumps(item["conditions"],ensure_ascii=False),process,current_tenant(),username,datetime.now().isoformat(timespec="seconds")))
                added += 1
    if added:
        log_event(username,"SENARYO_GERI_YUKLE","dynamic_scenario",process,str(added))
    return added
