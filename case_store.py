import pandas as pd
from platform_store import ROLES, log, now, require

CASE_STATUSES = ["Yeni", "İncelemede", "Risk doğrulandı", "Yanlış alarm", "Kapatıldı"]
FIELDS = ["status", "analyst", "responsible_unit", "review_note", "action_taken", "evidence_note"]


def load_cases(db):
    return pd.read_sql_query("SELECT * FROM cases ORDER BY transaction_id", db)


def get_case(db, tx):
    row = db.execute("SELECT * FROM cases WHERE transaction_id=?", (tx,)).fetchone()
    return dict(row) if row else dict(zip(FIELDS, ["Yeni", "", "", "", "", ""]))


def save_case(db, actor, tx, values):
    require(db, actor, ROLES[:2])
    if values["status"] not in CASE_STATUSES:
        raise ValueError("Geçersiz vaka durumu.")
    with db:
        db.execute("""INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(transaction_id) DO UPDATE SET status=excluded.status, analyst=excluded.analyst,
            responsible_unit=excluded.responsible_unit, review_note=excluded.review_note,
            action_taken=excluded.action_taken, evidence_note=excluded.evidence_note, updated=excluded.updated""",
            (tx, *(values[k] for k in FIELDS), now()))
        log(db, actor, "Vaka kaydı", tx + " / " + values["status"])
