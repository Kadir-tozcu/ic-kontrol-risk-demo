import json

import pandas as pd

from suite.platform_store import connect, current_tenant


def review_db():
    conn = connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS scenario_reviews (
        id INTEGER PRIMARY KEY, scenario_id INTEGER NOT NULL, prior_id INTEGER,
        action TEXT NOT NULL, justification TEXT NOT NULL, evidence TEXT NOT NULL,
        maker TEXT NOT NULL, requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Bekliyor', reviewer TEXT, decided_at TEXT)""")
    return conn


def review_role(conn, username):
    row = conn.execute("SELECT role FROM users WHERE username=? AND tenant_id=? AND active=1",
                       (username, current_tenant())).fetchone()
    return row[0] if row else None


def active_id(conn, key, process):
    row = conn.execute("""SELECT id FROM dynamic_scenarios WHERE tenant_id=? AND process=?
                          AND scenario_key=? AND active=1""", (current_tenant(), process, key)).fetchone()
    return row[0] if row else None


def request_review(row_id, action, justification, evidence, maker):
    if action not in ("Etkinleştir", "Durdur") or not justification.strip() or not evidence.get("Taranan kayıt"):
        raise ValueError("Talep için gerekçe ve test sonucu gereklidir.")
    with review_db() as conn:
        if review_role(conn, maker) != "Yonetici":
            raise ValueError("Talebi bir yönetici göndermelidir.")
        row = conn.execute("SELECT scenario_key,process,active FROM dynamic_scenarios WHERE id=? AND tenant_id=?",
                           (row_id, current_tenant())).fetchone()
        if not row or bool(row[2]) != (action == "Durdur"):
            raise ValueError("Sürüm durumu değişti. Sayfayı yenileyin.")
        prior = active_id(conn, *row[:2])
        pending = conn.execute("""SELECT 1 FROM scenario_reviews r JOIN dynamic_scenarios s ON s.id=r.scenario_id
            WHERE s.tenant_id=? AND s.scenario_key=? AND s.process=? AND r.status='Bekliyor'""",
            (current_tenant(), *row[:2])).fetchone()
        if pending:
            raise ValueError("Bu senaryo için zaten açık bir onay talebi var.")
        conn.execute("""INSERT INTO scenario_reviews(scenario_id,prior_id,action,justification,evidence,maker)
                        VALUES(?,?,?,?,?,?)""", (row_id, prior, action, justification.strip(),
                        json.dumps(evidence, ensure_ascii=False), maker))


def review_history(process):
    with review_db() as conn:
        return pd.read_sql_query("""SELECT r.*,s.name,s.version,s.created_by,s.logic,s.conditions_json,s.points
            FROM scenario_reviews r JOIN dynamic_scenarios s ON s.id=r.scenario_id
            WHERE s.tenant_id=? AND s.process=? ORDER BY r.id DESC""", conn, params=(current_tenant(), process))


def decide_review(review_id, reviewer, accept):
    with review_db() as conn:
        if review_role(conn, reviewer) not in ("Yonetici", "Onaylayan"):
            raise ValueError("Bu hesap onay vermeye yetkili değil.")
        row = conn.execute("""SELECT r.scenario_id,r.prior_id,r.action,r.maker,s.created_by,s.scenario_key,s.process
            FROM scenario_reviews r JOIN dynamic_scenarios s ON s.id=r.scenario_id
            WHERE r.id=? AND r.status='Bekliyor' AND s.tenant_id=?""", (review_id, current_tenant())).fetchone()
        if not row:
            raise ValueError("Açık talep bulunamadı.")
        target, prior, action, maker, author, key, process = row
        if reviewer == maker or (action == "Etkinleştir" and reviewer == author):
            raise ValueError("Kararı farklı bir yetkili hesap vermelidir.")
        status = "Reddedildi"
        if accept:
            status = "Onaylandı"
            if prior != active_id(conn, key, process):
                raise ValueError("Etkin sürüm değişti. Talebi reddedip yeniden test edin.")
            if prior is not None:
                conn.execute("UPDATE dynamic_scenarios SET active=0,status='PASIF' WHERE id=?", (prior,))
            if action == "Etkinleştir":
                conn.execute("UPDATE dynamic_scenarios SET active=1,status='YAYINDA' WHERE id=?", (target,))
        conn.execute("UPDATE scenario_reviews SET reviewer=?,status=?,decided_at=CURRENT_TIMESTAMP WHERE id=?",
                     (reviewer, status, review_id))
        conn.execute("""INSERT INTO audit_log(event_time,username,action,object_type,object_id,detail,tenant_id)
                        VALUES(CURRENT_TIMESTAMP,?,?,?,?,?,?)""",
                     (reviewer,"SENARYO_KARARI","dynamic_scenario",str(target),action+" · "+status,current_tenant()))


def draw_sample(pool, id_field, quotas, seed):
    ordered = pool.sort_values(id_field).drop_duplicates(id_field)
    parts = []
    for level, quota in quotas.items():
        group = ordered.loc[ordered.risk_level.eq(level)]
        if level == "YUKSEK":
            selected = group.sort_values("risk_score", ascending=False, kind="stable").head(quota)
        else:
            selected = group.sample(n=min(quota, len(group)), random_state=seed)
        parts.append(selected)
    return pd.concat(parts)
