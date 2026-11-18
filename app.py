from io import BytesIO
import sqlite3
from zipfile import BadZipFile, ZipFile

import pandas as pd
import streamlit as st

import case_store as cases
import platform_store as store
from recovery import recover, MAX_BYTES
from risk_engine import RULE_FIELDS, score_transactions
from synthetic_data import generate_synthetic_data

st.set_page_config(page_title="İç Kontrol Risk Ajansı", page_icon="🛡️", layout="wide")
st.markdown("<style>.block-container{max-width:1450px;padding-top:2rem}div[data-testid=stMetric]{padding:.8rem;border:1px solid #8393a344;border-radius:.65rem}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def sample():
    return generate_synthetic_data(10000, 42)


@st.cache_data(show_spinner=False)
def analyze(rules):
    return score_transactions(sample(), rules)


def spreadsheet_safe(df):
    result = df.copy()
    for col in result.select_dtypes(include=["object", "string"]).columns:
        result[col] = result[col].map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
    return result


def workbook(tx, records, audit):
    out = BytesIO()
    summary = tx.risk_level.value_counts().rename_axis("Risk seviyesi").reset_index(name="İşlem sayısı")
    sheets = {"Risk Analizi": tx, "Vakalar": records, "Yönetici Özeti": summary}
    if audit is not None:
        sheets["Denetim İzi"] = audit
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            spreadsheet_safe(frame).to_excel(writer, index=False, sheet_name=name)
            writer.sheets[name].freeze_panes = "A2"
            writer.sheets[name].auto_filter.ref = writer.sheets[name].dimensions
    return out.getvalue()


def imported_ids(file, allowed):
    if file.size > 2_000_000:
        raise ValueError("Dosya 2 MB sınırını aşıyor.")
    content = BytesIO(file.getvalue())
    if file.name.lower().endswith(".xlsx"):
        with ZipFile(content) as archive:
            if sum(f.file_size for f in archive.infolist()) > 12_000_000:
                raise ValueError("Excel dosyası çok büyük.")
        content.seek(0)
        data = pd.read_excel(content, usecols=["transaction_id"], nrows=10001)
    else:
        data = pd.read_csv(content, usecols=["transaction_id"], nrows=10001)
    ids = data.transaction_id
    if data.empty or len(ids) > 10000 or not ids.isin(allowed).all():
        raise ValueError("Dosyada yalnızca örnek veri kümesindeki işlem kimlikleri bulunabilir.")
    return ids.unique()


def metrics(items):
    for col, (label, value) in zip(st.columns(len(items)), items):
        col.metric(label, value)


def number(value):
    return f"{value:,}".replace(",", ".")


db_key = "workspace_db"
if db_key not in st.session_state:
    st.session_state[db_key] = store.initialize()
    st.session_state.identity = ("demo", "Yönetici")
db = st.session_state[db_key]
if not st.session_state.identity:
    st.title("Demo hesabına giriş")
    st.caption("Bu çalışma alanında oluşturduğun demo hesabıyla giriş yap. Yeni bir tarayıcı oturumu ayrı bir örnek alan açar.")
    with st.form("login", clear_on_submit=True):
        username = st.text_input("Kullanıcı adı")
        password = st.text_input("Parola", type="password")
        if st.form_submit_button("Giriş yap"):
            identity = store.authenticate(db, username, password)
            if identity:
                st.session_state.identity = identity
                st.rerun()
            st.error("Kullanıcı adı veya parola geçersiz.")
    st.stop()

actor, role = st.session_state.identity
admin = role == "Yönetici"
editable = role in store.ROLES[:2]
if st.session_state.pop("restored_notice", False):
    st.success("Çalışma alanı geri yüklendi. Vaka, kural ve denetim kayıtların hazır.")
rules = store.get_rules(db)
df = analyze(rules)
st.title("🛡️ İç Kontrol Risk Ajansı")
st.caption("10.000 sentetik işlem • Açıklanabilir kural tabanlı risk analizi")
with st.sidebar:
    st.header("Çalışma alanı")
    st.write(f"{actor} · {role}")
    st.caption("Bu alan yalnızca senin tarayıcı oturumuna aittir. Sonraki oturumda devam etmek için Sistem yönetimi bölümünden yedeğini indir. Yalnızca örnek bilgiler gir.")
    if st.button("Hesaptan çık"):
        with db:
            store.log(db, actor, "Çıkış", role)
        for key in list(st.session_state):
            if key != db_key:
                del st.session_state[key]
        st.session_state.identity = None
        st.rerun()
    source = st.radio("Veri kaynağı", ["10.000 sentetik işlem", "CSV / Excel seçimi"])
    if source.startswith("CSV"):
        st.caption("Örnek ID listesini indir, inceleyeceğin satırları bırak ve CSV veya Excel olarak yükle. Tutarlar ve müşteri alanları sentetik kaynaktan gelir.")
        st.download_button("Örnek ID listesi", df[["transaction_id"]].to_csv(index=False), "ornek_islemler.csv")
        file = st.file_uploader("Sentetik işlem ID listesi", type=["csv", "xlsx"])
        if not file:
            st.info("İncelenecek işlem listesini seç.")
            st.stop()
        try:
            df = df[df.transaction_id.isin(imported_ids(file, df.transaction_id))]
        except (ValueError, OSError, KeyError, BadZipFile):
            st.error("Dosya okunamadı. En fazla 2 MB büyüklüğünde, transaction_id sütunu ve geçerli örnek kimlikler içeren CSV veya XLSX kullan.")
            st.stop()
    levels = st.multiselect("Risk seviyesi", ["YÜKSEK", "ORTA", "DÜŞÜK"], default=["YÜKSEK", "ORTA", "DÜŞÜK"])
    minimum = st.slider("Asgari risk puanı", 0, 100, 0, 5)
    dormant = st.checkbox("Yalnızca 365+ gün hareketsiz")
    older = st.checkbox("Yalnızca 65 yaş ve üzeri")

view = df[df.risk_level.isin(levels) & (df.risk_score >= minimum)].copy()
if dormant:
    view = view[view.inactivity_days >= 365]
if older:
    view = view[view.age >= 65]
if not editable:
    view["customer_id"] = view.customer_id.str[-2:].radd("DEMO-***")
records = cases.load_cases(db)
records = records[records.transaction_id.isin(view.transaction_id)]
view["case_status"] = view.transaction_id.map(records.set_index("transaction_id").status).fillna("Yeni")
view = view.sort_values(["risk_score", "transaction_amount"], ascending=False)
closed = records.status.isin(["Kapatıldı", "Yanlış alarm"])
metrics([("Kaynak işlem", number(len(df))), ("Filtrelenen işlem", number(len(view))),
         ("Yüksek risk", number(view.risk_level.eq("YÜKSEK").sum())), ("Açık vaka", number((~closed).sum())),
         ("Ortalama skor", f"{view.risk_score.mean():.1f}/100" if len(view) else "—")])

pages = ["Risk panosu", "İşlem listesi", "Vaka detayı", "Yönetici raporu", "Vaka asistanı"]
if admin:
    pages += ["Kural yönetimi", "Sistem yönetimi"]
tabs = dict(zip(pages, st.tabs(pages)))
with tabs["Risk panosu"]:
    if view.empty:
        st.info("Filtrelere uygun işlem yok.")
    else:
        l, r = st.columns(2)
        l.subheader("Risk seviyeleri")
        l.bar_chart(view.risk_level.value_counts())
        r.subheader("Vaka durumları")
        r.bar_chart(records.status.value_counts() if len(records) else pd.Series({"Kayıtlı vaka": 0}))
        st.subheader("Risk puanı dağılımı")
        st.bar_chart(view.groupby(pd.cut(view.risk_score, [-1,19,39,59,79,100], labels=["0–19","20–39","40–59","60–79","80–100"]), observed=False).size())
        st.subheader("Günlük işlem eğilimi")
        st.line_chart(view.groupby(view.transaction_datetime.dt.date).agg(İşlem=("transaction_id", "size"), Yüksek=("risk_level", lambda s: (s == "YÜKSEK").sum())))
with tabs["İşlem listesi"]:
    statuses = st.multiselect("Vaka durumu", cases.CASE_STATUSES, default=cases.CASE_STATUSES)
    q = st.text_input("İşlem veya müşteri ara")
    table = view[view.case_status.isin(statuses)]
    if q:
        table = table[table.transaction_id.str.contains(q, regex=False, case=False) | table.customer_id.str.contains(q, regex=False, case=False)]
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("CSV indir", table.to_csv(index=False).encode("utf-8-sig"), "risk_analizi.csv")
    st.download_button("İşlem listesi Excel", lambda: workbook(table, records[records.transaction_id.isin(table.transaction_id)], None), "risk_analizi.xlsx")
with tabs["Vaka detayı"]:
    if view.empty:
        st.info("İncelenecek işlem yok.")
    else:
        tx = st.selectbox("İncelenecek işlem", view.transaction_id, key="case_tx")
        row = view.loc[view.transaction_id.eq(tx)].iloc[0]
        saved = cases.get_case(db, tx)
        metrics([("Risk seviyesi", row.risk_level), ("Risk puanı", f"{row.risk_score}/100"), ("Hareketsizlik", f"{row.inactivity_days} gün"), ("Tutar", f"{row.transaction_amount:,.2f} TL")])
        st.write("**Risk gerekçeleri**", row.risk_reasons)
        st.write("**Önerilen kontrol**", row.recommended_actions)
        with st.form(f"case_{tx}_{actor}"):
            values = {"status": st.selectbox("Durum", cases.CASE_STATUSES, index=cases.CASE_STATUSES.index(saved["status"]), disabled=not editable)}
            for key, label in [("analyst","İnceleyen"),("responsible_unit","Birim"),("review_note","İnceleme notu"),("action_taken","Alınan aksiyon"),("evidence_note","Kanıt açıklaması")]:
                values[key] = st.text_input(label, saved[key] or (actor if key == "analyst" else ""), disabled=not editable, max_chars=1000)
            if st.form_submit_button("Vakayı kaydet", disabled=not editable):
                cases.save_case(db, actor, tx, values)
                st.rerun()
with tabs["Yönetici raporu"]:
    false = (records.status == "Yanlış alarm").sum()
    metrics([("İşleme alınan", len(records)), ("Risk doğrulandı", (records.status == "Risk doğrulandı").sum()), ("Kapatılan", closed.sum()), ("Yanlış alarm oranı", f"%{100*false/len(records):.1f}" if len(records) else "—")])
    if len(records):
        st.subheader("İnceleyen bazında iş yükü")
        st.bar_chart(records.analyst.value_counts())
    reference = sample().transaction_datetime.max()
    hours = (reference - view.transaction_datetime).dt.total_seconds() / 3600
    sla = view.risk_level.map({"YÜKSEK":rules["high_sla_hours"], "ORTA":rules["medium_sla_hours"]})
    st.metric("İnceleme süresini aşan işlem", int(((hours > sla) & ~view.case_status.isin(["Kapatıldı","Yanlış alarm"])).sum()))
    st.caption(f"Demo değerlendirme zamanı {reference:%d.%m.%Y %H:%M}. Süre, işlem anından itibaren hesaplanır.")
    audit_export = store.audit(db, actor) if admin else None
    st.download_button("Yönetici Excel raporu", lambda: workbook(view, records, audit_export), "yonetici_raporu.xlsx")
with tabs["Vaka asistanı"]:
    if view.empty:
        st.info("Özetlenecek işlem yok.")
    else:
        selected = st.selectbox("Özetlenecek işlem", view.transaction_id, key="assistant_tx")
        x = view.loc[view.transaction_id.eq(selected)].iloc[0]
        draft = (f"{selected} · {x.risk_level} risk ({x.risk_score}/100). Günlük transfer toplamı {x.daily_transfer_total:,.2f} TL. "
                 f"Gerekçeler: {x.risk_reasons}. Önerilen kontrol: {x.recommended_actions}. Vaka durumu: {x.case_status}.")
        st.caption("Taslak, işlem ve vaka kaydından yerel kurallarla oluşturulur.")
        st.write(draft)
        st.download_button("Vaka özetini indir", draft, f"{selected}_ozet.txt")

if admin:
    with tabs["Kural yönetimi"]:
        st.caption("Kuralları kaydettiğinde bu oturumdaki işlemlerin risk puanları yeniden hesaplanır.")
        with st.form("rules"):
            cols = st.columns(3)
            changes = {}
            for i, (key, (label, _, lo, hi)) in enumerate(RULE_FIELDS.items()):
                changes[key] = cols[i % 3].number_input(label, lo, hi, rules[key])
            if st.form_submit_button("Kuralları kaydet"):
                store.save_rules(db, actor, changes)
                st.rerun()
    with tabs["Sistem yönetimi"]:
        st.subheader("Demo kullanıcıları")
        with st.form("new_account", clear_on_submit=True):
            name = st.text_input("Yeni kullanıcı adı", max_chars=48)
            password = st.text_input("Demo parolası", type="password", max_chars=256)
            new_role = st.selectbox("Rol", store.ROLES)
            if st.form_submit_button("Kullanıcı oluştur"):
                try:
                    store.create_user(db, actor, name, password, new_role)
                    st.success("Demo kullanıcısı oluşturuldu.")
                except ValueError as error:
                    st.error(str(error))
        st.dataframe(pd.read_sql_query("SELECT name AS Kullanıcı, role AS Rol FROM users", db), hide_index=True)
        st.subheader("Denetim izi")
        audit = store.audit(db, actor)
        st.dataframe(audit, hide_index=True)
        st.download_button("Denetim izini indir", spreadsheet_safe(audit).to_csv(index=False).encode("utf-8-sig"), "denetim_izi.csv")
        st.download_button("Demo veritabanı yedeği", store.backup(db, actor), "demo_yedek.db")
        st.caption("Yedek, bu oturumun kayıtlarını, kurallarını ve denetim izini içerir. Parola doğrulama bilgileri dışarı aktarılmaz.")

        with st.expander("Yedekten devam et"):
            st.caption("Bu sürümün ve önceki yedi ekranlı sürümün .db yedekleri desteklenir. Açtığın yedek, bu oturumdaki çalışma alanının yerini alır. Mevcut kayıtlarını saklamak için önce yedeklerini indir.")
            with st.form("restore_workspace"):
                imported = st.file_uploader("Demo yedeği (.db)", type=["db"], max_upload_size=12)
                confirmed = st.checkbox("Bu oturumda seçtiğim yedeği aç")
                if st.form_submit_button("Yedeği geri yükle"):
                    if imported is None or not confirmed:
                        st.info("Bir .db dosyası seç ve çalışma alanını değiştirmeyi onayla.")
                    else:
                        try:
                            if imported.size > MAX_BYTES:
                                raise ValueError("Yedek 12 MB sınırını aşıyor.")
                            recovered = recover(db, actor, imported.getvalue(), set(sample().transaction_id))
                        except (ValueError, TypeError, sqlite3.Error, OverflowError):
                            st.error("Yedek açılamadı. Dosya türünü, boyutunu ve demo yedeği olduğunu kontrol et. Mevcut çalışma alanın korunuyor.")
                        else:
                            for key in list(st.session_state):
                                del st.session_state[key]
                            st.session_state[db_key] = recovered
                            st.session_state.identity = ("demo", "Yönetici")
                            st.session_state.restored_notice = True
                            db.close()
                            st.rerun()
        inactive = [r[0] for r in db.execute("SELECT name FROM users WHERE name!='demo' AND digest IS NULL ORDER BY name")]
        if inactive:
            with st.form("activate_account", clear_on_submit=True):
                st.caption("Yedekten gelen hesapla giriş yapmak için yeni bir demo parolası belirle.")
                pending = st.selectbox("Etkinleştirilecek kullanıcı", inactive)
                replacement = st.text_input("Yeni demo parolası", type="password", max_chars=256)
                if st.form_submit_button("Hesabı etkinleştir"):
                    try:
                        store.activate_restored_user(db, actor, pending, replacement)
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.rerun()
