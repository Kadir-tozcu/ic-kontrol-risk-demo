"""Tenant-isolated persistent datasets, imports, API keys and integrations."""
from __future__ import annotations
import hashlib,json,secrets,sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd

from suite.workspace import directory, set_tenant, tenant as current_tenant
def _now():return datetime.now().isoformat(timespec="seconds")
def connect():
    (directory() / "cases.db").parent.mkdir(exist_ok=True);conn=sqlite3.connect((directory() / "cases.db"));conn.execute("PRAGMA journal_mode=WAL");conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS datasets (id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT NOT NULL,process TEXT NOT NULL,name TEXT NOT NULL,period TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(tenant_id,process,name,period))")
    conn.execute("CREATE TABLE IF NOT EXISTS dataset_records (dataset_id INTEGER NOT NULL,record_key TEXT NOT NULL,payload_json TEXT NOT NULL,batch_id TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(dataset_id,record_key))")
    conn.execute("CREATE TABLE IF NOT EXISTS import_batches (batch_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,dataset_id INTEGER NOT NULL,file_name TEXT NOT NULL,strategy TEXT NOT NULL,row_count INTEGER NOT NULL,inserted INTEGER NOT NULL,updated INTEGER NOT NULL,rejected INTEGER NOT NULL,status TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,rolled_back_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE TABLE IF NOT EXISTS record_versions (id INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,dataset_id INTEGER NOT NULL,record_key TEXT NOT NULL,operation TEXT NOT NULL,old_payload TEXT,new_payload TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT NOT NULL,name TEXT NOT NULL,key_prefix TEXT NOT NULL,key_hash TEXT NOT NULL,scopes TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,last_used_at TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS integration_sources (id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT NOT NULL,name TEXT NOT NULL,source_type TEXT NOT NULL,config_json TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,last_status TEXT NOT NULL DEFAULT 'YAPILANDIRILMADI',last_checked_at TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at TEXT NOT NULL)")
    return conn

def create_dataset(process,name,period,username):
    if not name.strip():raise ValueError("Veri seti adı zorunludur.")
    with connect() as conn:
        cur=conn.execute("INSERT INTO datasets(tenant_id,process,name,period,created_by,created_at) VALUES(?,?,?,?,?,?)",(current_tenant(),process,name.strip(),period.strip(),username,_now()));return cur.lastrowid
def list_datasets(process=None):
    q="SELECT d.*,COUNT(r.record_key) record_count FROM datasets d LEFT JOIN dataset_records r ON r.dataset_id=d.id WHERE d.tenant_id=?";params=[current_tenant()]
    if process:q+=" AND d.process=?";params.append(process)
    q+=" GROUP BY d.id ORDER BY d.id DESC"
    with connect() as conn:return pd.read_sql_query(q,conn,params=tuple(params))
def load_dataset(dataset_id):
    from suite.v15_security import decrypt_text
    with connect() as conn:
        allowed=conn.execute("SELECT 1 FROM datasets WHERE id=? AND tenant_id=? AND active=1",(int(dataset_id),current_tenant())).fetchone()
        if not allowed:raise ValueError("Veri setine erişim yetkiniz yok.")
        rows=conn.execute("SELECT payload_json FROM dataset_records WHERE dataset_id=? ORDER BY record_key",(int(dataset_id),)).fetchall()
    return pd.DataFrame([json.loads(decrypt_text(x[0])) for x in rows])
def import_dataset(dataset_id,data,key_field,strategy,file_name,username):
    from suite.v15_security import encrypt_text
    if strategy not in ["EKLE","GUNCELLE","DEGISTIR"]:raise ValueError("Geçersiz aktarım yöntemi.")
    if key_field not in data:raise ValueError("Kayıt anahtarı sütunu bulunamadı.")
    work=data.copy();keys=work[key_field].astype(str).str.strip()
    if keys.eq("").any() or keys.duplicated().any():raise ValueError("Kayıt anahtarı boş veya dosya içinde mükerrer olamaz.")
    batch="bat_"+secrets.token_hex(8);inserted=updated=rejected=0
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM datasets WHERE id=? AND tenant_id=?",(int(dataset_id),current_tenant())).fetchone():raise ValueError("Veri setine erişim yetkiniz yok.")
        existing={k:v for k,v in conn.execute("SELECT record_key,payload_json FROM dataset_records WHERE dataset_id=?",(int(dataset_id),)).fetchall()}
        if strategy=="DEGISTIR":
            for key,old in existing.items():conn.execute("INSERT INTO record_versions(batch_id,dataset_id,record_key,operation,old_payload,new_payload) VALUES(?,?,?,?,?,NULL)",(batch,int(dataset_id),key,"DELETE",old))
            conn.execute("DELETE FROM dataset_records WHERE dataset_id=?",(int(dataset_id),));existing={}
        for idx,row in work.iterrows():
            key=keys.loc[idx];payload=encrypt_text(json.dumps({str(k):(None if pd.isna(v) else (v.isoformat() if hasattr(v,"isoformat") else v.item() if hasattr(v,"item") else v)) for k,v in row.to_dict().items()},ensure_ascii=False,default=str))
            old=existing.get(key)
            if old is not None and strategy=="EKLE":rejected+=1;continue
            operation="UPDATE" if old is not None else "INSERT";updated+=operation=="UPDATE";inserted+=operation=="INSERT"
            conn.execute("INSERT INTO record_versions(batch_id,dataset_id,record_key,operation,old_payload,new_payload) VALUES(?,?,?,?,?,?)",(batch,int(dataset_id),key,operation,old,payload))
            conn.execute("INSERT INTO dataset_records VALUES(?,?,?,?,?) ON CONFLICT(dataset_id,record_key) DO UPDATE SET payload_json=excluded.payload_json,batch_id=excluded.batch_id,updated_at=excluded.updated_at",(int(dataset_id),key,payload,batch,_now()))
        conn.execute("INSERT INTO import_batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(batch,current_tenant(),int(dataset_id),file_name,strategy,len(work),int(inserted),int(updated),int(rejected),"TAMAMLANDI",username,_now(),""))
    return {"batch_id":batch,"inserted":int(inserted),"updated":int(updated),"rejected":int(rejected)}
def rollback_batch(batch_id,username):
    with connect() as conn:
        batch=conn.execute("SELECT dataset_id,status FROM import_batches WHERE batch_id=? AND tenant_id=?",(batch_id,current_tenant())).fetchone()
        if not batch:raise ValueError("Aktarım bulunamadı.")
        if batch[1]=="GERI_ALINDI":raise ValueError("Aktarım zaten geri alınmış.")
        versions=conn.execute("SELECT record_key,operation,old_payload FROM record_versions WHERE batch_id=? ORDER BY id DESC",(batch_id,)).fetchall()
        for key,op,old in versions:
            if op=="INSERT":conn.execute("DELETE FROM dataset_records WHERE dataset_id=? AND record_key=?",(batch[0],key))
            else:conn.execute("INSERT INTO dataset_records VALUES(?,?,?,?,?) ON CONFLICT(dataset_id,record_key) DO UPDATE SET payload_json=excluded.payload_json,batch_id=excluded.batch_id,updated_at=excluded.updated_at",(batch[0],key,old,"rollback:"+batch_id,_now()))
        conn.execute("UPDATE import_batches SET status='GERI_ALINDI',rolled_back_at=? WHERE batch_id=?",(_now(),batch_id))
    return len(versions)
def list_imports(dataset_id=None):
    q="SELECT batch_id,dataset_id,file_name,strategy,row_count,inserted,updated,rejected,status,created_by,created_at,rolled_back_at FROM import_batches WHERE tenant_id=?";params=[current_tenant()]
    if dataset_id:q+=" AND dataset_id=?";params.append(int(dataset_id))
    q+=" ORDER BY created_at DESC"
    with connect() as conn:return pd.read_sql_query(q,conn,params=tuple(params))
def create_api_key(name,scopes,username):
    if not name.strip() or not scopes:raise ValueError("Anahtar adı ve en az bir yetki zorunludur.")
    raw="rsk_"+secrets.token_urlsafe(32);digest=hashlib.sha256(raw.encode()).hexdigest()
    with connect() as conn:conn.execute("INSERT INTO api_keys(tenant_id,name,key_prefix,key_hash,scopes,created_by,created_at) VALUES(?,?,?,?,?,?,?)",(current_tenant(),name.strip(),raw[:12],digest,",".join(scopes),username,_now()))
    return raw
def verify_api_key(raw,scope=None):
    digest=hashlib.sha256(raw.encode()).hexdigest()
    with connect() as conn:row=conn.execute("SELECT id,tenant_id,scopes FROM api_keys WHERE key_hash=? AND active=1",(digest,)).fetchone()
    if not row or (scope and scope not in row[2].split(",")):return None
    from suite.v15_security import check_rate_limit
    if not check_rate_limit(row[1],raw[:12]):raise RuntimeError("API istek sınırı aşıldı")
    with connect() as conn:conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?",(_now(),row[0]))
    return {"tenant_id":row[1],"scopes":row[2].split(",")}
def list_api_keys():
    with connect() as conn:return pd.read_sql_query("SELECT id,name,key_prefix,scopes,active,last_used_at,created_by,created_at FROM api_keys WHERE tenant_id=? ORDER BY id DESC",conn,params=(current_tenant(),))
def revoke_api_key(key_id):
    with connect() as conn:conn.execute("UPDATE api_keys SET active=0 WHERE id=? AND tenant_id=?",(int(key_id),current_tenant()))
def save_integration(name,source_type,config,username):
    if not name.strip():raise ValueError("Bağlantı adı zorunludur.")
    with connect() as conn:conn.execute("INSERT INTO integration_sources(tenant_id,name,source_type,config_json,created_by,created_at) VALUES(?,?,?,?,?,?)",(current_tenant(),name.strip(),source_type,json.dumps(config,ensure_ascii=False),username,_now()))
def list_integrations():
    with connect() as conn:return pd.read_sql_query("SELECT id,name,source_type,active,last_status,last_checked_at,created_by,created_at FROM integration_sources WHERE tenant_id=? ORDER BY id DESC",conn,params=(current_tenant(),))
