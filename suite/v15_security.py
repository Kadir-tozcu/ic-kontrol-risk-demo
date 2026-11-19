"""V15 security controls: encryption, MFA, lockout, sessions and retention."""
from __future__ import annotations
import base64,hashlib,hmac,os,secrets,sqlite3,struct,time
from datetime import datetime,timedelta
from pathlib import Path
import pandas as pd

from suite.workspace import directory, set_tenant, tenant as current_tenant
def _now():return datetime.now().isoformat(timespec="seconds")
def connect():
    (directory() / "cases.db").parent.mkdir(exist_ok=True);conn=sqlite3.connect((directory() / "cases.db"));conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS security_settings (tenant_id TEXT PRIMARY KEY,idle_timeout_minutes INTEGER NOT NULL DEFAULT 30,absolute_timeout_hours INTEGER NOT NULL DEFAULT 8,max_failed_logins INTEGER NOT NULL DEFAULT 5,lockout_minutes INTEGER NOT NULL DEFAULT 15,retention_days INTEGER NOT NULL DEFAULT 730,api_requests_per_minute INTEGER NOT NULL DEFAULT 120,updated_by TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE TABLE IF NOT EXISTS user_security (username TEXT PRIMARY KEY,mfa_secret TEXT NOT NULL DEFAULT '',mfa_enabled INTEGER NOT NULL DEFAULT 0,failed_attempts INTEGER NOT NULL DEFAULT 0,locked_until TEXT NOT NULL DEFAULT '',password_changed_at TEXT NOT NULL DEFAULT '',last_login_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE TABLE IF NOT EXISTS security_events (id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT NOT NULL,event_time TEXT NOT NULL,username TEXT NOT NULL,event_type TEXT NOT NULL,success INTEGER NOT NULL,detail TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_rate_usage (tenant_id TEXT NOT NULL,key_prefix TEXT NOT NULL,minute_bucket TEXT NOT NULL,request_count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,key_prefix,minute_bucket))")
    conn.execute("INSERT OR IGNORE INTO security_settings(tenant_id) VALUES(?)",(current_tenant(),));return conn
def _fernet():
    from cryptography.fernet import Fernet
    env=os.getenv("RISK_AJANSI_MASTER_KEY","").encode()
    if env:key=env
    else:
        (directory() / ".master.key").parent.mkdir(exist_ok=True)
        if not (directory() / ".master.key").exists():(directory() / ".master.key").write_bytes(Fernet.generate_key())
        key=(directory() / ".master.key").read_bytes().strip()
    return Fernet(key)
def encrypt_text(value):return "enc:"+_fernet().encrypt(str(value).encode()).decode()
def decrypt_text(value):
    if value is None:return None
    text=str(value)
    return _fernet().decrypt(text[4:].encode()).decode() if text.startswith("enc:") else text
def encrypt_bytes(value:bytes):return b"RAE1"+_fernet().encrypt(value)
def decrypt_bytes(value:bytes):return _fernet().decrypt(value[4:]) if value and value.startswith(b"RAE1") else value
def get_settings(tenant_id=None):
    tenant=tenant_id or current_tenant()
    with connect() as conn:row=conn.execute("SELECT idle_timeout_minutes,absolute_timeout_hours,max_failed_logins,lockout_minutes,retention_days,api_requests_per_minute FROM security_settings WHERE tenant_id=?",(tenant,)).fetchone()
    return dict(zip(["idle_timeout_minutes","absolute_timeout_hours","max_failed_logins","lockout_minutes","retention_days","api_requests_per_minute"],row or [30,8,5,15,730,120]))
def save_settings(config,username):
    values=[int(config[x]) for x in ["idle_timeout_minutes","absolute_timeout_hours","max_failed_logins","lockout_minutes","retention_days","api_requests_per_minute"]]
    with connect() as conn:conn.execute("INSERT INTO security_settings VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET idle_timeout_minutes=excluded.idle_timeout_minutes,absolute_timeout_hours=excluded.absolute_timeout_hours,max_failed_logins=excluded.max_failed_logins,lockout_minutes=excluded.lockout_minutes,retention_days=excluded.retention_days,api_requests_per_minute=excluded.api_requests_per_minute,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(current_tenant(),*values,username,_now()))
    log_security(username,"GUVENLIK_POLITIKASI",True,str(config))
def log_security(username,event_type,success,detail="",tenant_id=None):
    with connect() as conn:conn.execute("INSERT INTO security_events(tenant_id,event_time,username,event_type,success,detail) VALUES(?,?,?,?,?,?)",(tenant_id or current_tenant(),_now(),username,event_type,int(success),str(detail)[:1000]))
def authenticate_secure(username,password,otp=""):
    from suite.platform_store import authenticate
    username=username.strip()
    with connect() as conn:
        row=conn.execute("SELECT mfa_secret,mfa_enabled,failed_attempts,locked_until FROM user_security WHERE username=?",(username,)).fetchone()
    if row and row[3] and datetime.fromisoformat(row[3])>datetime.now():log_security(username,"GIRIS_KILITLI",False,row[3]);return None,"Hesap geçici olarak kilitli."
    found=authenticate(username,password)
    tenant=found.get("tenant_id","default") if found else "default";settings=get_settings(tenant)
    if not found:return _login_failure(username,settings,"Kullanıcı adı veya parola hatalı."),"Kullanıcı adı veya parola hatalı."
    if row and row[1] and not verify_totp(decrypt_text(row[0]),otp):return _login_failure(username,settings,"MFA kodu hatalı.",tenant),"Doğrulama kodu hatalı."
    with connect() as conn:conn.execute("INSERT INTO user_security(username,failed_attempts,locked_until,last_login_at) VALUES(?,0,'',?) ON CONFLICT(username) DO UPDATE SET failed_attempts=0,locked_until='',last_login_at=excluded.last_login_at",(username,_now()))
    log_security(username,"GIRIS",True,"MFA" if row and row[1] else "Parola",tenant);return found,""
def _login_failure(username,settings,detail,tenant="default"):
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO user_security(username) VALUES(?)",(username,));conn.execute("UPDATE user_security SET failed_attempts=failed_attempts+1 WHERE username=?",(username,));attempts=conn.execute("SELECT failed_attempts FROM user_security WHERE username=?",(username,)).fetchone()[0]
        if attempts>=settings["max_failed_logins"]:conn.execute("UPDATE user_security SET locked_until=?,failed_attempts=0 WHERE username=?",((datetime.now()+timedelta(minutes=settings["lockout_minutes"])).isoformat(timespec="seconds"),username))
    log_security(username,"GIRIS_BASARISIZ",False,detail,tenant);return None
def generate_mfa_secret():return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
def totp_uri(secret,username,issuer="Risk Ajansı"):return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&digits=6&period=30"
def _totp(secret,counter):
    padded=secret+"="*((8-len(secret)%8)%8);key=base64.b32decode(padded);digest=hmac.new(key,struct.pack(">Q",counter),hashlib.sha1).digest();offset=digest[-1]&15;code=(struct.unpack(">I",digest[offset:offset+4])[0]&0x7fffffff)%1000000;return f"{code:06d}"
def verify_totp(secret,code):
    if not secret or not str(code).isdigit():return False
    counter=int(time.time())//30;return any(hmac.compare_digest(_totp(secret,counter+i),str(code).zfill(6)) for i in [-1,0,1])
def enable_mfa(username,secret,code):
    if not verify_totp(secret,code):raise ValueError("Doğrulama kodu geçersiz.")
    with connect() as conn:conn.execute("INSERT INTO user_security(username,mfa_secret,mfa_enabled) VALUES(?,?,1) ON CONFLICT(username) DO UPDATE SET mfa_secret=excluded.mfa_secret,mfa_enabled=1",(username,encrypt_text(secret)))
    log_security(username,"MFA_ETKINLESTIR",True)
def disable_mfa(username,code):
    with connect() as conn:row=conn.execute("SELECT mfa_secret FROM user_security WHERE username=? AND mfa_enabled=1",(username,)).fetchone()
    if not row or not verify_totp(decrypt_text(row[0]),code):raise ValueError("Doğrulama kodu geçersiz.")
    with connect() as conn:conn.execute("UPDATE user_security SET mfa_enabled=0,mfa_secret='' WHERE username=?",(username,))
    log_security(username,"MFA_DEVRE_DISI",True)
def mfa_status(username):
    with connect() as conn:row=conn.execute("SELECT mfa_enabled FROM user_security WHERE username=?",(username,)).fetchone()
    return bool(row and row[0])
def list_security_events(limit=500):
    with connect() as conn:return pd.read_sql_query("SELECT event_time,username,event_type,success,detail FROM security_events WHERE tenant_id=? ORDER BY id DESC LIMIT ?",conn,params=(current_tenant(),int(limit)))
def check_rate_limit(tenant,key_prefix):
    settings=get_settings(tenant);bucket=datetime.now().strftime("%Y%m%d%H%M")
    with connect() as conn:
        conn.execute("INSERT INTO api_rate_usage VALUES(?,?,?,1) ON CONFLICT(tenant_id,key_prefix,minute_bucket) DO UPDATE SET request_count=request_count+1",(tenant,key_prefix,bucket));count=conn.execute("SELECT request_count FROM api_rate_usage WHERE tenant_id=? AND key_prefix=? AND minute_bucket=?",(tenant,key_prefix,bucket)).fetchone()[0]
    return count<=settings["api_requests_per_minute"]
def mask_dataframe(data,role):
    result=data.copy()
    if role not in ["Goruntuleyen","Denetci"]:return result
    for col in ["customer_id","recipient_id","employee_id","ip_address","device_id"]:
        if col in result:result[col]=result[col].astype(str).map(lambda x:(x[:3]+"***"+x[-2:]) if len(x)>5 else "***")
    return result
def retention_preview():
    cutoff=(datetime.now()-timedelta(days=get_settings()["retention_days"])).isoformat(timespec="seconds")
    with connect() as conn:
        prefix="%|%" if current_tenant()=="default" else current_tenant()+"|%";op="NOT LIKE" if current_tenant()=="default" else "LIKE"
        comments=conn.execute(f"SELECT COUNT(*) FROM case_comments WHERE transaction_id {op} ? AND created_at<?",(prefix,cutoff)).fetchone()[0];evidence=conn.execute(f"SELECT COUNT(*) FROM case_evidence WHERE transaction_id {op} ? AND uploaded_at<?",(prefix,cutoff)).fetchone()[0]
    return {"cutoff":cutoff,"comments":comments,"evidence":evidence}
def apply_retention(username):
    preview=retention_preview();cutoff=preview["cutoff"]
    with connect() as conn:
        prefix="%|%" if current_tenant()=="default" else current_tenant()+"|%";op="NOT LIKE" if current_tenant()=="default" else "LIKE"
        conn.execute(f"DELETE FROM case_comments WHERE transaction_id {op} ? AND created_at<?",(prefix,cutoff));conn.execute(f"DELETE FROM case_evidence WHERE transaction_id {op} ? AND uploaded_at<?",(prefix,cutoff))
    log_security(username,"SAKLAMA_POLITIKASI_UYGULA",True,str(preview));return preview["comments"]+preview["evidence"]
