"""Small local SQLite store for V2 case workflow."""

from __future__ import annotations

import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd


CASE_STATUSES = [
    "Yeni",
    "Inceleniyor",
    "Musteri teyidi bekleniyor",
    "Onay bekliyor",
    "Iade edildi",
    "Risk dogrulandi",
    "Yanlis alarm",
    "Kapatildi",
]

from suite.workspace import directory, set_tenant, tenant as current_tenant
def _case_key(value: str) -> str:return str(value) if current_tenant()=="default" else f"{current_tenant()}|{value}"
def _visible_key(value: str) -> str:return str(value).split("|",1)[-1] if "|" in str(value) else str(value)


def _connect() -> sqlite3.Connection:
    (directory() / "cases.db").parent.mkdir(exist_ok=True)
    conn = sqlite3.connect((directory() / "cases.db"))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            transaction_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'Yeni',
            analyst TEXT NOT NULL DEFAULT '',
            responsible_unit TEXT NOT NULL DEFAULT '',
            review_note TEXT NOT NULL DEFAULT '',
            action_taken TEXT NOT NULL DEFAULT '',
            evidence_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    if "created_at" not in columns:
        conn.execute("ALTER TABLE cases ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    migrations={"case_number":"TEXT NOT NULL DEFAULT ''","priority":"TEXT NOT NULL DEFAULT 'Orta'","due_date":"TEXT NOT NULL DEFAULT ''","reviewer":"TEXT NOT NULL DEFAULT ''","assigned_team":"TEXT NOT NULL DEFAULT ''","parent_case_id":"TEXT NOT NULL DEFAULT ''"}
    for name,definition in migrations.items():
        if name not in columns:conn.execute(f"ALTER TABLE cases ADD COLUMN {name} {definition}")
    conn.execute("CREATE TABLE IF NOT EXISTS case_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL, comment TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS case_evidence (id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL, file_name TEXT NOT NULL, mime_type TEXT NOT NULL, file_hash TEXT NOT NULL, content BLOB NOT NULL, uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS case_checklist (transaction_id TEXT NOT NULL, item_key TEXT NOT NULL, label TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0, completed_by TEXT NOT NULL DEFAULT '', completed_at TEXT NOT NULL DEFAULT '', PRIMARY KEY(transaction_id,item_key))")
    conn.execute("CREATE TABLE IF NOT EXISTS case_workflow_log (id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL)")
    return conn


def load_cases() -> pd.DataFrame:
    with _connect() as conn:
        if current_tenant()=="default":result=pd.read_sql_query("SELECT * FROM cases WHERE transaction_id NOT LIKE '%|%'",conn)
        else:result=pd.read_sql_query("SELECT * FROM cases WHERE transaction_id LIKE ?",conn,params=(current_tenant()+"|%",))
    if len(result):result["transaction_id"]=result["transaction_id"].map(_visible_key)
    return result


def get_case(transaction_id: str) -> dict:
    with _connect() as conn:
        cursor=conn.execute("SELECT * FROM cases WHERE transaction_id = ?",(_case_key(transaction_id),));row=cursor.fetchone();keys=[x[0] for x in cursor.description]
    if not row:
        return {
            "transaction_id": str(transaction_id), "status": "Yeni", "analyst": "",
            "responsible_unit": "", "review_note": "", "action_taken": "",
            "evidence_note": "", "created_at": "", "updated_at": "", "case_number":"", "priority":"Orta", "due_date":"", "reviewer":"", "assigned_team":"", "parent_case_id":"",
        }
    result=dict(zip(keys,row));result["transaction_id"]=_visible_key(result["transaction_id"]);return result


def save_case(transaction_id: str, status: str, analyst: str, responsible_unit: str,
              review_note: str, action_taken: str, evidence_note: str, actor: str = "system") -> None:
    if status not in CASE_STATUSES:
        raise ValueError("Gecersiz vaka durumu")
    updated_at = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO cases(transaction_id,status,analyst,responsible_unit,review_note,action_taken,evidence_note,created_at,updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
              status=excluded.status, analyst=excluded.analyst,
              responsible_unit=excluded.responsible_unit, review_note=excluded.review_note,
              action_taken=excluded.action_taken, evidence_note=excluded.evidence_note,
              updated_at=excluded.updated_at
            """,
            (_case_key(transaction_id), status, analyst.strip(), responsible_unit.strip(),
             review_note.strip(), action_taken.strip(), evidence_note.strip(), updated_at, updated_at),
        )
    from suite.platform_store import log_event
    log_event(actor, "VAKA_KAYDET", "case", str(transaction_id), status)


def add_case_comment(transaction_id: str, comment: str, actor: str) -> None:
    if not comment.strip():raise ValueError("Yorum boş olamaz.")
    now=datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:conn.execute("INSERT INTO case_comments(transaction_id,comment,created_by,created_at) VALUES(?,?,?,?)",(_case_key(transaction_id),comment.strip(),actor,now))
    from suite.platform_store import log_event
    log_event(actor,"VAKA_YORUM","case",str(transaction_id),comment[:200])


def list_case_comments(transaction_id: str) -> pd.DataFrame:
    with _connect() as conn:return pd.read_sql_query("SELECT created_at,created_by,comment FROM case_comments WHERE transaction_id=? ORDER BY id DESC",conn,params=(_case_key(transaction_id),))


def add_case_evidence(transaction_id: str, file_name: str, mime_type: str, content: bytes, actor: str) -> None:
    if not content:raise ValueError("Boş dosya yüklenemez.")
    if len(content)>10*1024*1024:raise ValueError("Kanıt dosyası 10 MB'dan büyük olamaz.")
    from suite.v15_security import encrypt_bytes
    digest=hashlib.sha256(content).hexdigest();encrypted=encrypt_bytes(content);now=datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        exists=conn.execute("SELECT 1 FROM case_evidence WHERE transaction_id=? AND file_hash=?",(_case_key(transaction_id),digest)).fetchone()
        if not exists:conn.execute("INSERT INTO case_evidence(transaction_id,file_name,mime_type,file_hash,content,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?,?)",(_case_key(transaction_id),file_name,mime_type or "application/octet-stream",digest,encrypted,actor,now))
    from suite.platform_store import log_event
    log_event(actor,"KANIT_YUKLE","case",str(transaction_id),file_name)


def list_case_evidence(transaction_id: str) -> pd.DataFrame:
    with _connect() as conn:return pd.read_sql_query("SELECT id,file_name,mime_type,LENGTH(content) AS file_size,uploaded_by,uploaded_at FROM case_evidence WHERE transaction_id=? ORDER BY id DESC",conn,params=(_case_key(transaction_id),))


def get_case_evidence(evidence_id: int):
    with _connect() as conn:
        if current_tenant()=="default":row=conn.execute("SELECT file_name,mime_type,content FROM case_evidence WHERE id=? AND transaction_id NOT LIKE '%|%'",(int(evidence_id),)).fetchone()
        else:row=conn.execute("SELECT file_name,mime_type,content FROM case_evidence WHERE id=? AND transaction_id LIKE ?",(int(evidence_id),current_tenant()+"|%" )).fetchone()
    if row:
        from suite.v15_security import decrypt_bytes
        return (row[0],row[1],decrypt_bytes(row[2]))
    return None


def bulk_update_cases(transaction_ids: list[str], status: str, analyst: str, actor: str) -> int:
    for transaction_id in transaction_ids:
        current=get_case(transaction_id);save_case(transaction_id,status,analyst or current["analyst"],current["responsible_unit"],current["review_note"],current["action_taken"],current["evidence_note"],actor)
    return len(transaction_ids)

def bulk_create_cases(transaction_ids: list[str], analyst: str, reviewer: str, assigned_team: str,
                      priority: str, due_date: str, actor: str) -> int:
    clean=list(dict.fromkeys(str(x) for x in transaction_ids if str(x).strip()))
    if not clean:raise ValueError("Vaka oluşturulacak en az bir kayıt seçilmelidir.")
    if not analyst.strip():raise ValueError("İnceleyen kullanıcı seçilmelidir.")
    if reviewer.strip() and reviewer.strip()==analyst.strip():raise ValueError("Dört göz prensibi gereği inceleyen ve onaylayan farklı olmalıdır.")
    for transaction_id in clean:
        current=get_case(transaction_id)
        save_case(transaction_id,"Inceleniyor",analyst,assigned_team,current["review_note"],current["action_taken"],current["evidence_note"],actor)
        save_case_workflow(transaction_id,priority,due_date,reviewer,assigned_team,actor)
        _log_workflow(transaction_id,"TOPLU_VAKA_OLUŞTUR",f"inceleyen={analyst}; onaylayan={reviewer}; ekip={assigned_team}",actor)
    return len(clean)


def save_case_workflow(transaction_id: str, priority: str, due_date: str, reviewer: str,
                       assigned_team: str, actor: str) -> None:
    if priority not in ["Düşük","Orta","Yüksek","Kritik"]:raise ValueError("Geçersiz öncelik.")
    current=get_case(transaction_id)
    if not current.get("created_at"):
        save_case(transaction_id,current["status"],current["analyst"],current["responsible_unit"],current["review_note"],current["action_taken"],current["evidence_note"],actor)
    case_no=current.get("case_number") or f"VAK-{datetime.now():%Y%m%d}-{abs(hash(str(transaction_id)))%100000:05d}"
    now=datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("UPDATE cases SET case_number=?,priority=?,due_date=?,reviewer=?,assigned_team=?,updated_at=? WHERE transaction_id=?",(case_no,priority,due_date,reviewer.strip(),assigned_team.strip(),now,_case_key(transaction_id)))
        conn.execute("INSERT INTO case_workflow_log(transaction_id,action,detail,actor,created_at) VALUES(?,?,?,?,?)",(_case_key(transaction_id),"İŞ_AKIŞI_GÜNCELLE",f"öncelik={priority}; son tarih={due_date}; onaylayan={reviewer}; ekip={assigned_team}",actor,now))


def submit_for_approval(transaction_id: str, actor: str) -> None:
    case=get_case(transaction_id)
    if not case.get("reviewer"):raise ValueError("Onaya göndermeden önce onaylayan kullanıcı seçilmelidir.")
    save_case(transaction_id,"Onay bekliyor",case["analyst"],case["responsible_unit"],case["review_note"],case["action_taken"],case["evidence_note"],actor)
    _log_workflow(transaction_id,"ONAYA_GÖNDER",case["reviewer"],actor)


def approval_decision(transaction_id: str, approve: bool, note: str, actor: str) -> None:
    case=get_case(transaction_id)
    if case.get("reviewer") and case["reviewer"]!=actor:raise ValueError("Bu vaka için onaylayan kullanıcı siz değilsiniz.")
    status="Risk dogrulandi" if approve else "Iade edildi";save_case(transaction_id,status,case["analyst"],case["responsible_unit"],case["review_note"],case["action_taken"],case["evidence_note"],actor);_log_workflow(transaction_id,"ONAYLA" if approve else "İADE_ET",note,actor)


def _log_workflow(transaction_id: str, action: str, detail: str, actor: str) -> None:
    with _connect() as conn:conn.execute("INSERT INTO case_workflow_log(transaction_id,action,detail,actor,created_at) VALUES(?,?,?,?,?)",(_case_key(transaction_id),action,detail.strip(),actor,datetime.now().isoformat(timespec="seconds")))


def get_checklist(transaction_id: str, labels: list[str]) -> pd.DataFrame:
    with _connect() as conn:
        for idx,label in enumerate(labels):conn.execute("INSERT OR IGNORE INTO case_checklist(transaction_id,item_key,label) VALUES(?,?,?)",(_case_key(transaction_id),f"item_{idx+1}",label))
        return pd.read_sql_query("SELECT item_key,label,completed,completed_by,completed_at FROM case_checklist WHERE transaction_id=? ORDER BY item_key",conn,params=(_case_key(transaction_id),))


def update_checklist(transaction_id: str, states: dict[str,bool], actor: str) -> None:
    now=datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        for key,value in states.items():conn.execute("UPDATE case_checklist SET completed=?,completed_by=?,completed_at=? WHERE transaction_id=? AND item_key=?",(int(value),actor if value else "",now if value else "",_case_key(transaction_id),key))
    _log_workflow(transaction_id,"KONTROL_LISTESİ","Kontrol listesi güncellendi",actor)


def merge_cases(parent_id: str, child_ids: list[str], actor: str) -> int:
    clean=[str(x) for x in child_ids if str(x)!=str(parent_id)]
    for child in clean:
        existing=get_case(child)
        if not existing.get("created_at"):save_case(child,"Yeni","","","","","",actor)
    with _connect() as conn:
        for child in clean:conn.execute("UPDATE cases SET parent_case_id=?,updated_at=? WHERE transaction_id=?",(_case_key(parent_id),datetime.now().isoformat(timespec="seconds"),_case_key(child)))
    _log_workflow(parent_id,"VAKA_BİRLEŞTİR",", ".join(clean),actor);return len(clean)


def list_workflow_log(transaction_id: str) -> pd.DataFrame:
    with _connect() as conn:return pd.read_sql_query("SELECT created_at,actor,action,detail FROM case_workflow_log WHERE transaction_id=? ORDER BY id DESC",conn,params=(_case_key(transaction_id),))
