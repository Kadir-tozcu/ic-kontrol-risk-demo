from io import BytesIO
import json
from datetime import datetime
import sqlite3
from zipfile import BadZipFile, ZipFile

import pandas as pd
import streamlit as st

import case_store as cases
import platform_store as store
from recovery import recover, MAX_BYTES
from platform_store import RULE_FIELDS
from risk_engine import REQUIRED_COLUMNS, score_transactions
import legacy_data
import legacy_engine
from synthetic_data import generate_synthetic_data

st.set_page_config(page_title="Ic Kontrol Risk Ajansi", page_icon="🛡️", layout="wide")
st.markdown("""<style>.stApp{background:#f5f7fb}.block-container{padding-top:1.3rem;max-width:1500px}[data-testid=stMetric]{background:white;border:1px solid #e3e8f1;padding:14px;border-radius:12px}.sub{color:#667085;margin-top:-14px}</style>""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def sample(legacy=False):
    if legacy:
        return legacy_data.generate_synthetic_data(10000, 42)
    return generate_synthetic_data(10000, 42)


@st.cache_data(show_spinner=False)
def analyze(rules, legacy):
    if legacy:
        return legacy_engine.score_transactions(sample(True), rules)
    result = score_transactions(sample(), rules)
    result["risk_level"] = result.risk_level.replace({"YUKSEK": "YÜKSEK", "DUSUK": "DÜŞÜK"})
    return result


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


db_key = "workspace_db"
if db_key not in st.session_state:
    st.session_state[db_key] = store.initialize()
    st.session_state.identity = ("demo", "Yönetici")
db = st.session_state[db_key]
if not st.session_state.identity:
    st.title("🛡️ Ic Kontrol Risk Ajansi")
    st.caption("Bu çalışma alanında oluşturduğun demo hesabıyla giriş yap. Yeni bir tarayıcı oturumu ayrı bir örnek alan açar.")
    with st.form("login", clear_on_submit=True):
        username = st.text_input("Kullanici adi")
        password = st.text_input("Parola", type="password")
        if st.form_submit_button("Giris yap"):
            identity = store.authenticate(db, username, password)
            if identity:
                st.session_state.identity = identity
                st.rerun()
            st.error("Kullanıcı adı veya parola geçersiz.")
    if db.execute("SELECT count(*) FROM users").fetchone()[0] == 1:
        with st.expander("Ilk yonetici kurulumu"):
            with st.form("setup", clear_on_submit=True):
                u = st.text_input("Yonetici kullanici adi")
                pw = st.text_input("Parola (en az 8 karakter)", type="password")
                repeat = st.text_input("Parolayi tekrar yazin", type="password")
                if st.form_submit_button("Hesabi olustur"):
                    if pw != repeat:
                        st.error("Parolalar ayni degil.")
                    else:
                        try:
                            store.create_user(db, "demo", u, pw, "Yönetici")
                            st.session_state.identity = (u.strip(), "Yönetici")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
    st.stop()

actor, role = st.session_state.identity
admin = role == "Yönetici"
editable = role in store.ROLES[:2]
if st.session_state.pop("restored_notice", False):
    st.success("Çalışma alanı geri yüklendi. Vaka, kural ve denetim kayıtların hazır.")
rules = store.get_rules(db)
legacy = db.execute("PRAGMA user_version").fetchone()[0] == 0
st.title("🛡️ Ic Kontrol Risk Ajansi");st.markdown('<div class="sub">Risk analizi • Vaka yonetimi • Yonetisim • Yerel karar destek asistani</div>',unsafe_allow_html=True)
with st.sidebar:
    st.write(f"**{actor}** — {role}")
    if st.button("Guvenli cikis",width="stretch"):
        with db:
            store.log(db, actor, "Çıkış", role)
        for key in list(st.session_state):
            if key != db_key:
                del st.session_state[key]
        st.session_state.identity = None
        st.rerun()
    st.divider();source=st.radio("Veri kaynagi",["10.000 sentetik islemle demo","CSV / Excel yukle"]);uploaded=None
    if source.startswith("CSV"):
        st.caption("Demo veri kümesinden işlem seçmek için transaction_id sütunu içeren bir dosya yükleyin.")
        st.download_button("Örnek ID listesi", sample(legacy)[["transaction_id"]].to_csv(index=False), "ornek_islemler.csv")
        uploaded=st.file_uploader("Dosya secin",type=["csv","xlsx"])
        with st.expander("Gerekli sutunlar"):st.code("transaction_id",language=None)
try:
    if source.startswith("10.000"): scored=analyze(rules, legacy)
    elif uploaded is None: st.info("Dosya yukleyin.");st.stop()
    else:
        scored=analyze(rules, legacy)
        scored=scored[scored.transaction_id.isin(imported_ids(uploaded, scored.transaction_id))].copy()
    scored["risk_level"] = scored.risk_level.replace({"YÜKSEK":"YUKSEK","DÜŞÜK":"DUSUK"})
except Exception as e:st.error(f"Dosya analiz edilemedi: {e}");st.stop()

case_rows=cases.load_cases(db);case_rows=case_rows[case_rows.transaction_id.isin(scored.transaction_id)];status_map=case_rows.set_index("transaction_id")["status"].to_dict() if len(case_rows) else {};scored["case_status"]=scored["transaction_id"].astype(str).map(status_map).fillna("Yeni")
view=scored.copy()
if role=="Görüntüleyen":view["customer_id"]=view["customer_id"].astype(str).map(lambda x:x[:3]+"***"+x[-2:])
high=int((scored.risk_level=="YUKSEK").sum());closed=int(scored.case_status.isin(["Kapatıldı","Yanlış alarm"]).sum())
for col,(label,value) in zip(st.columns(5),[("Toplam islem",len(scored)),("Yuksek risk",high),("Acik vaka",len(scored)-closed),("Kapatilan",closed),("Ortalama skor",f"{scored.risk_score.mean():.1f}/100")]):col.metric(label,value)

names=["Risk panosu","Islem listesi","Vaka detayi","Yonetici raporu","Vaka asistani"]+(["Kural yonetimi","Sistem yonetimi"] if admin else []); tabs=dict(zip(names,st.tabs(names)))
with tabs["Risk panosu"]:
    l,r=st.columns(2)
    with l:st.subheader("Risk dagilimi");st.bar_chart(scored.risk_level.value_counts(),horizontal=True,color="#d24b58")
    with r:st.subheader("Vaka durumlari");st.bar_chart(scored.case_status.value_counts(),horizontal=True,color="#2457a7")
    trend=scored.assign(gun=pd.to_datetime(scored.transaction_datetime).dt.date).groupby("gun").agg(Islem=("transaction_id","count"),Yuksek=("risk_level",lambda x:(x=="YUKSEK").sum()));st.subheader("Gunluk egilim");st.line_chart(trend)
with tabs["Islem listesi"]:
    a,b,c,d=st.columns([1,1,1.4,2]);levels=a.multiselect("Risk seviyesi",["YUKSEK","ORTA","DUSUK"],default=["YUKSEK"]);minimum=b.slider("Minimum skor",0,100,70);statuses=c.multiselect("Vaka durumu",cases.CASE_STATUSES,default=cases.CASE_STATUSES);q=d.text_input("Islem / musteri ara")
    filtered=view[view.risk_level.isin(levels)&(view.risk_score>=minimum)&view.case_status.isin(statuses)].copy()
    if q:filtered=filtered[filtered.transaction_id.astype(str).str.contains(q,case=False,regex=False)|filtered.customer_id.astype(str).str.contains(q,case=False,regex=False)]
    cols=["transaction_id","customer_id","transaction_datetime","age","transaction_amount","daily_transfer_total","daily_transaction_count","risk_score","risk_level","case_status"]
    st.dataframe(filtered[cols],hide_index=True,width="stretch",height=430);st.download_button("Excel indir",lambda: workbook(filtered,case_rows[case_rows.transaction_id.isin(filtered.transaction_id)],None),"risk_analizi.xlsx",width="stretch")
with tabs["Vaka detayi"]:
    candidates=scored.sort_values(["risk_score","transaction_amount"],ascending=False);sid=st.selectbox("Incelenecek islem",candidates.transaction_id.astype(str),key="case");row=scored[scored.transaction_id.astype(str)==sid].iloc[0];saved=cases.get_case(db,sid)
    k=st.columns(4);k[0].metric("Risk",row.risk_level);k[1].metric("Skor",f"{row.risk_score}/100");k[2].metric("Hareketsizlik",f"{row.inactivity_days:g} gun");k[3].metric("Tutar",f"{row.transaction_amount:,.0f} TL")
    l,r=st.columns(2)
    with l:
        st.subheader("Risk gerekceleri")
        for x in str(row.risk_reasons).split(" | "):st.warning(x)
    with r:
        st.subheader("Kontrol aksiyonlari")
        for x in str(row.recommended_actions).split(" | "):st.success(x)
    with st.form(f"case_form_{sid}_{actor}"):
        l,r=st.columns(2);status=l.selectbox("Durum",cases.CASE_STATUSES,index=cases.CASE_STATUSES.index(saved["status"]),disabled=not editable);analyst=r.text_input("Inceleyen",saved["analyst"] or actor,disabled=not editable);unit=l.text_input("Birim",saved["responsible_unit"],disabled=not editable);action=r.text_input("Alinan aksiyon",saved["action_taken"],disabled=not editable);note=st.text_area("Inceleme notu",saved["review_note"],disabled=not editable);evidence=st.text_area("Kanit aciklamasi",saved["evidence_note"],disabled=not editable)
        if st.form_submit_button("Kaydet",type="primary",width="stretch",disabled=not editable):cases.save_case(db,actor,sid,dict(zip(cases.FIELDS,[status,analyst,unit,note,action,evidence])));st.rerun()
with tabs["Yonetici raporu"]:
    confirmed=int((case_rows.status=="Risk doğrulandı").sum()) if len(case_rows) else 0;false=int((case_rows.status=="Yanlış alarm").sum()) if len(case_rows) else 0
    for col,(label,value) in zip(st.columns(4),[("Isleme alinan",len(case_rows)),("Risk dogrulandi",confirmed),("Yanlis alarm",false),("Yanlis alarm orani",f"%{false/len(case_rows)*100:.1f}" if len(case_rows) else "%0")]):col.metric(label,value)
    if len(case_rows):st.subheader("Inceleyen bazinda is yuku");st.bar_chart(case_rows.analyst.replace("","Atanmamis").value_counts(),horizontal=True)
    age_hours=(pd.Timestamp.now()-pd.to_datetime(scored.transaction_datetime)).dt.total_seconds()/3600;sla=scored.risk_level.map({"YUKSEK":rules["high_sla_hours"],"ORTA":rules["medium_sla_hours"]}).fillna(999999);st.metric("SLA asimi",int(((age_hours>sla)&~scored.case_status.isin(["Kapatıldı","Yanlış alarm"])).sum()))
    audit_export = store.audit(db, actor) if admin else None
    st.download_button("Yonetici Excel raporu",lambda: workbook(view,case_rows,audit_export),"yonetici_raporu.xlsx",width="stretch")
with tabs["Vaka asistani"]:
    aid=st.selectbox("Ozetlenecek islem",candidates.transaction_id.astype(str),key="assistant");x=scored[scored.transaction_id.astype(str)==aid].iloc[0];s=cases.get_case(db,aid);draft=f"{aid} numarali islem {x.risk_score}/100 skorla {x.risk_level} risklidir. Gunluk toplam {x.daily_transfer_total:,.2f} TL'dir. Gerekceler: {x.risk_reasons}. Onerilen kontroller: {x.recommended_actions}. Vaka durumu: {s['status']}. Bu taslak yetkili kontrol personeli tarafindan dogrulanmalidir."
    st.caption("Veri disariya gonderilmez; denetlenebilir yerel taslak uretilir.");st.text_area("Vaka ozeti",draft,height=220);st.download_button("Ozeti indir",draft.encode("utf-8"),f"{aid}_ozet.txt")
if admin:
    with tabs["Kural yonetimi"]:
        st.warning("Degisiklikler yeni analizleri etkiler ve denetim izine kaydedilir.")
        with st.form("rules"):
            c1,c2,c3=st.columns(3);new=rules.copy();new["inactivity_days_threshold"]=c1.number_input("Hareketsizlik gunu",1,3650,int(rules["inactivity_days_threshold"]));new["high_amount"]=c2.number_input("Yuksek tutar",1,100000000,int(rules["high_amount"]),step=10000);new["daily_amount"]=c3.number_input("Gunluk tutar",1,100000000,int(rules["daily_amount"]),step=10000);new["daily_count"]=c1.number_input("Gunluk adet",1,10000,int(rules["daily_count"]));new["elderly_daily_age"]=c2.number_input("Ileri yas",18,110,int(rules["elderly_daily_age"]));new["elderly_daily_amount"]=c3.number_input("Ileri yas gunluk tutar",1,100000000,int(rules["elderly_daily_amount"]),step=10000);new["high_sla_hours"]=c1.number_input("Yuksek SLA saat",1,720,int(rules["high_sla_hours"]));new["medium_sla_hours"]=c2.number_input("Orta SLA saat",1,2160,int(rules["medium_sla_hours"]));
            if st.form_submit_button("Kurallari kaydet",type="primary",width="stretch"):store.save_rules(db,actor,new);st.rerun()
    with tabs["Sistem yonetimi"]:
        l,r=st.columns(2)
        with l:
            st.subheader("Kullanici olustur")
            # Oturumdaki st.session_state["user"] ile form anahtari cakismamali.
            with st.form("create_user_form",clear_on_submit=True):
                nu=st.text_input("Kullanici adi");np=st.text_input("Gecici parola",type="password");nr=st.selectbox("Rol",store.ROLES)
                if st.form_submit_button("Olustur"):
                    try:store.create_user(db,actor,nu,np,nr);st.rerun()
                    except Exception as e:st.error(str(e))
            st.dataframe(pd.read_sql_query("SELECT name AS Kullanıcı, role AS Rol FROM users",db),hide_index=True,width="stretch")
        with r:st.subheader("Yedekleme");st.download_button("Veritabani yedegini indir",store.backup(db,actor),f"yedek_{datetime.now():%Y%m%d}.db",width="stretch")
        audit=store.audit(db,actor);st.subheader("Denetim izi");st.dataframe(audit,hide_index=True,width="stretch",height=350);st.download_button("Denetim izini indir",spreadsheet_safe(audit).to_csv(index=False).encode("utf-8-sig"),"denetim_izi.csv")
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
                            recovered = recover(db, actor, imported.getvalue(), set(sample().transaction_id), set(sample(True).transaction_id))
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

st.caption("V3–V6 kurumsal prototip • Yerel veri • Rol tabanli erisim • Aciklanabilir risk")

