from __future__ import annotations

import json
import hashlib
import os
import time
from functools import partial
from uuid import uuid4
from html import escape
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from suite.case_store import CASE_STATUSES, get_case, load_cases, save_case, add_case_comment, list_case_comments, add_case_evidence, list_case_evidence, get_case_evidence, bulk_update_cases, bulk_create_cases, save_case_workflow, submit_for_approval, approval_decision, get_checklist, update_checklist, merge_cases, list_workflow_log, set_tenant as set_case_tenant
from suite.control_review import decide_review, draw_sample, request_review, review_history
from suite.platform_store import ROLES, authenticate, backup_bytes, create_custom_rule, create_user, get_audit, get_process_rule_overrides, get_rules, has_users, list_custom_rules, list_users, log_event, save_process_rule_override, save_rules, set_custom_rule_active, list_dynamic_scenarios, save_dynamic_scenario, record_upload, list_upload_history, get_organization_settings, save_organization_settings, save_filter, list_saved_filters, delete_saved_filter, set_tenant as set_platform_tenant, create_organization, list_organizations, change_password, get_data_mapping, save_data_mapping, record_analysis_run, list_analysis_runs
from suite.risk_engine import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, score_transactions
from suite.synthetic_data import generate_synthetic_data
from suite.process_modules import PROCESS_DEFINITIONS, generate_process_demo, score_process
from suite.data_dictionary import field_label, rename_for_display, turkish_columns
from suite.data_mapping import suggest_mapping, mapping_dict, apply_mapping, missing_required
from suite.expanded_scenarios import optional_fields as expanded_optional_fields, enrich_process_demo, apply_expanded_scenarios, scenario_catalog, transaction_types
from suite.adaptive_ai import instant_filter, read_scenario_text, api_available as ai_api_available, model_name as ai_model_name, dataset_schema as adaptive_dataset_schema, rule_from_text, run_rule, ask_dataset, safe_record as ai_safe_record
from suite.platform_store import scenario_package, restore_scenario_package
from suite.v10_features import OPERATORS, apply_dynamic_scenarios, quality_report, scenario_mask, scenario_performance
from suite.v11_operations import case_pdf, sla_notifications
from suite.v14_store import set_tenant as set_v14_tenant, create_dataset, list_datasets, load_dataset, import_dataset, rollback_batch, list_imports, create_api_key, list_api_keys, revoke_api_key, save_integration, list_integrations
from suite.v15_security import set_tenant as set_security_tenant, authenticate_secure, get_settings as get_security_settings, save_settings as save_security_settings, generate_mfa_secret, totp_uri, enable_mfa, disable_mfa, mfa_status, list_security_events, mask_dataframe, retention_preview, apply_retention

def tr_text(value):
    text=str(value)
    process_names={"Musteri Edinimi / KYC":"Müşteri Edinimi / KYC","Kart ve Odeme":"Kart ve Ödeme","Muhasebe Kayitlari":"Muhasebe Kayıtları","Satin Alma / Tedarikci":"Satın Alma / Tedarikçi","Personel / Ucret":"Personel / Ücret","BT / Siber Guvenlik":"BT / Siber Güvenlik","Sube / Operasyon":"Şube / Operasyon","Veri Gizliligi":"Veri Gizliliği","Musteri Sikayetleri":"Müşteri Şikâyetleri"}
    text=process_names.get(text,text)
    replacements={"Ic Kontrol":"İç Kontrol","Ajansi":"Ajansı","Ilk":"İlk","Yonetici":"Yönetici","Denetci":"Denetçi","Goruntuleyen":"Görüntüleyen","yonetici":"yönetici","Kullanici":"Kullanıcı","kullanici":"kullanıcı","Parolayi":"Parolayı","Hesabi":"Hesabı","olustur":"oluştur","Olustur":"Oluştur","ayni":"aynı","degil":"değil","Giris":"Giriş","hatali":"hatalı","yonetimi":"yönetimi","Yonetisim":"Yönetişim","Guvenli":"Güvenli","cikis":"çıkış","kaynagi":"kaynağı","islem":"işlem","Islem":"İşlem","Yuksek":"Yüksek","YUKSEK":"YÜKSEK","DUSUK":"DÜŞÜK","Acik":"Açık","Kapatilan":"Kapatılan","dagilimi":"dağılımı","durumlari":"durumları","Gunluk":"Günlük","egilim":"eğilim","gostergesi":"göstergesi","gosterilecek":"gösterilecek","Siralama":"Sıralama","azalan":"azalan","adlarini":"adlarını","goster":"göster","icin":"için","secin":"seçin","musteri":"müşteri","Musteri":"Müşteri","detayi":"detayı","Incelenecek":"İncelenecek","gerekceleri":"gerekçeleri","aksiyonlari":"aksiyonları","Alinan":"Alınan","Inceleyen":"İnceleyen","Kanit":"Kanıt","dogrulandi":"doğrulandı","Yanlis":"Yanlış","Iade":"İade","orani":"oranı","bazinda":"bazında","yuku":"yükü","Atanmamis":"Atanmamış","asimi":"aşımı","Ozet":"Özet","ozet":"özet","disariya":"dışarıya","gonderilmez":"gönderilmez","Surec":"Süreç","surec":"süreç","Moduler":"Modüler","Kayit":"Kayıt","kayit":"kayıt","sablonunu":"şablonunu","Bos":"Boş","yukleyin":"yükleyin","yapilamadi":"yapılamadı","Degisiklikler":"Değişiklikler","Hareketsizlik gunu":"Hareketsizlik günü","Ileri yas":"İleri yaş","Kurallari":"Kuralları","adi":"adı","Ornek":"Örnek","Genc":"Genç","Karsilastirma":"Karşılaştırma","Esik":"Eşik","deger":"değer","Ikinci":"İkinci","kosul":"koşul","puani":"puanı","Onerilen":"Önerilen","Henuz":"Henüz","Gecici":"Geçici","Veritabani":"Veritabanı","yedegini":"yedeğini","Denetim Izi":"Denetim İzi","erisim":"erişim","Aciklanabilir":"Açıklanabilir"}
    for old,new in replacements.items(): text=text.replace(old,new)
    return text

RISK_LABELS={"YUKSEK":"YÜKSEK","ORTA":"ORTA","DUSUK":"DÜŞÜK"}

st.set_page_config(page_title="İç Kontrol Risk Ajansı", page_icon="🛡️", layout="wide")
try:
    if st.secrets.get("OPENAI_API_KEY"):os.environ.setdefault("OPENAI_API_KEY",st.secrets["OPENAI_API_KEY"])
    if st.secrets.get("OPENAI_MODEL"):os.environ.setdefault("OPENAI_MODEL",st.secrets["OPENAI_MODEL"])
except Exception:pass
st.markdown("""<style>
:root{--navy:#101828;--blue:#175cd3;--violet:#6938ef;--red:#d92d20;--amber:#dc6803;--green:#039855;--line:#e4e7ec}
.stApp{background:linear-gradient(180deg,#f8faff 0,#f3f6fb 420px,#f7f8fa 100%);color:var(--navy)}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1540px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#101828,#1d2939);border-right:0}
[data-testid="stSidebarCollapseButton"] button{background:#fff!important;border:1px solid #d0d5dd!important;border-radius:10px!important;box-shadow:0 3px 10px rgba(16,24,40,.12)!important;color:#101828!important}
[data-testid="stSidebarCollapseButton"] button:hover{background:#f2f4f7!important;border-color:#98a2b3!important}
[data-testid="stSidebarCollapseButton"] button svg{color:#101828!important;fill:#101828!important}
[data-testid="stSidebar"]{color:#f2f4f7}[data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,[data-testid="stSidebar"] [data-testid="stCaptionContainer"]{color:#f2f4f7!important}
[data-testid="stSidebar"] .stButton button,[data-testid="stSidebar"] .stDownloadButton button{background:#fff!important;border:1px solid #d0d5dd!important;color:#1d2939!important;opacity:1!important}
[data-testid="stSidebar"] .stButton button *,[data-testid="stSidebar"] .stDownloadButton button *{color:#1d2939!important}
[data-testid="stSidebar"] div[data-baseweb="select"]>div{background:#fff!important;border-color:#d0d5dd!important}
[data-testid="stSidebar"] div[data-baseweb="select"]>div *,[data-testid="stSidebar"] div[data-baseweb="select"] svg{color:#101828!important;fill:#101828!important}
[data-testid="stSidebar"] [data-testid="stExpander"] summary *{color:#f2f4f7!important}
[data-testid="stSidebar"] [data-testid="stDataFrame"] *{color:#101828!important}
[data-testid="stSidebar"] button:disabled{background:#f2f4f7!important;color:#667085!important;border-color:#d0d5dd!important}
[data-testid="stSidebar"] button:disabled *{color:#667085!important}.hero{position:relative;overflow:hidden;background:linear-gradient(120deg,#101828 0%,#1849a9 58%,#6938ef 100%);padding:28px 32px;border-radius:20px;color:white;margin-bottom:18px;box-shadow:0 16px 40px rgba(16,24,40,.14)}
.hero:after{content:"";position:absolute;width:260px;height:260px;border:1px solid rgba(255,255,255,.14);border-radius:50%;right:-55px;top:-105px;box-shadow:0 0 0 42px rgba(255,255,255,.035),0 0 0 84px rgba(255,255,255,.025)}
.hero-kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:#b2ccff;margin-bottom:7px}.hero h1{font-size:31px;margin:0 0 6px;line-height:1.15}.hero p{margin:0;color:#e4e7ec;font-size:15px}.hero-badge{display:inline-block;margin-top:15px;padding:7px 11px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);border-radius:999px;font-size:12px;font-weight:600}
.process-strip{background:#fff;border:1px solid var(--line);border-left:4px solid var(--violet);padding:12px 16px;border-radius:12px;margin:4px 0 14px;box-shadow:0 4px 16px rgba(16,24,40,.04)}
.process-strip b{color:#344054}.process-strip span{color:#667085;font-size:13px;margin-left:8px}
.process-selector-label{font-size:12px;font-weight:750;letter-spacing:.06em;text-transform:uppercase;color:#667085;margin:0 0 5px}
.st-key-active_process{background:#fff;border:1px solid var(--line);border-left:5px solid var(--violet);padding:12px 16px 8px;border-radius:14px;box-shadow:0 4px 16px rgba(16,24,40,.05);margin:4px 0 4px}
.st-key-active_process div[data-baseweb="select"]>div{background:#f8faff;border-color:#b2ccff;min-height:46px}
.st-key-active_process div[data-baseweb="select"] span{font-weight:700;color:#344054}
.process-selector-note{color:#667085;font-size:13px;margin:0 0 14px 20px}
[data-testid="stMetric"]{background:rgba(255,255,255,.95);border:1px solid var(--line);padding:16px 18px;border-radius:15px;box-shadow:0 6px 20px rgba(16,24,40,.055);min-height:112px}
[data-testid="stMetricLabel"]{color:#667085;font-weight:600}[data-testid="stMetricValue"]{color:#101828;font-weight:750}
[data-baseweb="tab-list"]{gap:5px;background:#fff;border:1px solid var(--line);padding:6px;border-radius:13px;box-shadow:0 4px 14px rgba(16,24,40,.04)}
[data-baseweb="tab"]{height:42px;border-radius:9px;padding:0 15px}[aria-selected="true"][data-baseweb="tab"]{background:#eef4ff;color:#1849a9;font-weight:700}
[data-testid="stDataFrame"], [data-testid="stVegaLiteChart"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:7px;box-shadow:0 5px 18px rgba(16,24,40,.04)}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:650}.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{background:linear-gradient(90deg,#175cd3,#6938ef);border:0}
div[data-baseweb="select"]>div,div[data-baseweb="input"]>div,textarea{border-radius:10px!important}.sub{color:#667085}.sidebar-brand{padding:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);border-radius:14px;margin-bottom:16px}.sidebar-brand strong{font-size:16px}.sidebar-brand small{display:block;color:#98a2b3!important;margin-top:4px}
h2,h3{letter-spacing:-.02em}hr{border-color:#eaecf0!important}
.case-hero{display:flex;justify-content:space-between;align-items:center;gap:24px;background:linear-gradient(120deg,#fff,#f5f8ff);border:1px solid #d0d5dd;border-radius:18px;padding:22px 26px;margin:8px 0 16px;box-shadow:0 8px 24px rgba(16,24,40,.06)}
.case-kicker{color:#667085;font-size:12px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}.case-hero h2{font-size:28px;margin:4px 0;color:#101828}.case-hero p{margin:0;color:#667085}.risk-pill{min-width:150px;text-align:center;border-radius:15px;padding:13px 18px;font-weight:800;font-size:18px}.risk-pill small{display:block;font-size:12px;font-weight:600;margin-top:3px}.risk-high{background:#fee4e2;color:#b42318;border:1px solid #fecdca}.risk-medium{background:#fef0c7;color:#b54708;border:1px solid #fedf89}.risk-low{background:#dcfae6;color:#027a48;border:1px solid #abefc6}
.case-fact{background:#fff;border:1px solid #eaecf0;border-radius:12px;padding:12px 14px;min-height:70px}.case-fact span{display:block;color:#667085;font-size:12px;margin-bottom:5px}.case-fact b{color:#101828;font-size:15px}.finding-card,.action-card{position:relative;border-radius:14px;padding:16px 18px 16px 52px;min-height:74px;margin-bottom:10px}.finding-card{background:#fffaeb;border:1px solid #fedf89;color:#93370d}.action-card{background:#ecfdf3;border:1px solid #abefc6;color:#05603a}.card-no{position:absolute;left:15px;top:15px;width:25px;height:25px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#fff;font-size:12px;font-weight:800;border:1px solid currentColor}.section-label{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#667085;font-weight:750;margin:12px 0 10px}
.st-key-main_navigation [role="radiogroup"]{display:flex;flex-wrap:wrap;gap:6px;background:#fff;border:1px solid var(--line);padding:7px;border-radius:14px;box-shadow:0 4px 14px rgba(16,24,40,.04);margin:2px 0 14px}
.st-key-main_navigation label{width:auto!important;min-height:38px;padding:8px 12px!important;border:1px solid transparent;border-radius:9px;transition:background .15s ease,border-color .15s ease}
.st-key-main_navigation label:hover{background:#f2f4f7;border-color:#e4e7ec}
.st-key-main_navigation label:has(input:checked){background:#eef4ff;border-color:#b2ccff;color:#1849a9}
.st-key-main_navigation label>div:first-child{display:none!important}
.st-key-main_navigation [data-testid="stMarkdownContainer"] p{font-size:13px;font-weight:650;white-space:nowrap;margin:0}
.st-key-mobile_navigation,.st-key-mobile_cases{display:none!important}
@media(max-width:767px){
  .st-key-desktop_navigation,.st-key-desktop_cases{display:none!important}
  .st-key-mobile_navigation,.st-key-mobile_cases{display:flex!important}
  .st-key-mobile_cases button{min-height:46px;text-align:left;justify-content:flex-start}
  .st-key-mobile_cases button p{text-align:left}
  .block-container{padding-left:1rem;padding-right:1rem}
  .case-hero{flex-wrap:wrap;gap:12px}
}
</style>""", unsafe_allow_html=True)

def login():
    if not has_users() and "public_demo_started" not in st.session_state:
        import secrets
        create_user("demo", secrets.token_urlsafe(28), "Yonetici")
        st.session_state.public_demo_started = True
        st.session_state.user = {"username":"demo","role":"Yonetici","tenant_id":"default"}
        st.session_state.login_started = st.session_state.last_activity = time.time()
    if not has_users():
        st.title("🛡️ İlk yönetici kurulumu")
        with st.form("setup"):
            u=st.text_input("Yönetici kullanıcı adı"); p=st.text_input("Parola (en az 12 karakter)",type="password"); p2=st.text_input("Parolayı tekrar yazın",type="password")
            if st.form_submit_button("Hesabı oluştur",type="primary",width="stretch"):
                if p != p2: st.error("Parolalar aynı değil.")
                else:
                    try: create_user(u,p,"Yonetici"); st.session_state.user={"username":u.strip(),"role":"Yonetici"}; st.rerun()
                    except Exception as e: st.error(str(e))
        st.stop()
    if "user" not in st.session_state:
        st.title("🛡️ İç Kontrol Risk Ajansı")
        if st.session_state.pop("session_expired",False):st.warning("Güvenliğiniz için oturum süresi doldu. Lütfen yeniden giriş yapın.")
        with st.form("login"):
            u=st.text_input("Kullanıcı adı"); p=st.text_input("Parola",type="password");otp=st.text_input("Doğrulama kodu (MFA etkinse)",max_chars=6,placeholder="6 haneli kod")
            if st.form_submit_button("Giriş yap",type="primary",width="stretch"):
                found,message=authenticate_secure(u,p,otp)
                if found:st.session_state.user=found;st.session_state.login_started=time.time();st.session_state.last_activity=time.time();log_event(found["username"],"GIRIS","session","local");st.rerun()
                st.error(message or "Giriş başarısız.")
        st.stop()
    return st.session_state.user

@st.cache_data(scope="session", show_spinner=False)
def demo(rules_json,custom_json): return apply_expanded_scenarios(score_transactions(enrich_process_demo(generate_synthetic_data(10_000,42),"Para Transferleri",42),json.loads(rules_json),json.loads(custom_json)),"Para Transferleri")

@st.cache_data(scope="session", show_spinner=False)
def read_file(content,name):
    b=BytesIO(content)
    if name.lower().endswith(".csv"):
        try:return pd.read_csv(b)
        except UnicodeDecodeError:b.seek(0);return pd.read_csv(b,encoding="latin-1")
    return pd.read_excel(b)

def dataframe_excel(data, sheet_name="Rapor"):
    out=BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:data.to_excel(writer,index=False,sheet_name=sheet_name[:31])
    return out.getvalue()

@st.cache_data(scope="session", show_spinner="Risk analizi hazırlanıyor...")
def score_transfer_upload(content,name,rules_json,custom_json):
    return score_transactions(read_file(content,name),json.loads(rules_json),json.loads(custom_json))

@st.cache_data(scope="session", show_spinner="Kalıcı veri seti analiz ediliyor...")
def score_transfer_cached(data,rules_json,custom_json):
    return apply_expanded_scenarios(score_transactions(data,json.loads(rules_json),json.loads(custom_json)),"Para Transferleri")

@st.cache_data(scope="session", show_spinner="Süreç riskleri hesaplanıyor...")
def score_process_cached(data,process,overrides_json):
    return apply_expanded_scenarios(score_process(data,process,json.loads(overrides_json)),process)

@st.cache_data(scope="session", show_spinner=False)
def process_demo_cached(process,overrides_json):
    return apply_expanded_scenarios(score_process(enrich_process_demo(generate_process_demo(process,1500,42),process,42),process,json.loads(overrides_json)),process)

def excel_report(tx,cases,audit=None):
    out=BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as w:
        tx.drop(columns=["risk_reasons_json","recommended_actions_json"],errors="ignore").to_excel(w,index=False,sheet_name="Risk Analizi")
        cases.to_excel(w,index=False,sheet_name="Vakalar")
        tx["risk_level"].value_counts().rename_axis("Seviye").reset_index(name="Adet").to_excel(w,index=False,sheet_name="Yonetici Ozeti")
        if audit is not None:audit.to_excel(w,index=False,sheet_name="Denetim Izi")
        for ws in w.book.worksheets: ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
    return out.getvalue()

def localize_values(data):
    result=data.copy();text_labels={"True":"Evet","False":"Hayır","true":"Evet","false":"Hayır","Internet":"İnternet","Sube":"Şube","Tamamlandi":"Tamamlandı","Iptal":"İptal","YUKSEK":"YÜKSEK","DUSUK":"DÜŞÜK"}
    for col in result.columns:
        if result[col].dtype=="bool":result[col]=result[col].map({True:"Evet",False:"Hayır"})
        elif result[col].dtype=="object":result[col]=result[col].map(lambda value:text_labels.get(str(value),tr_text(value)) if pd.notna(value) else value)
    return result

def styled_result_excel(data, process_name):
    """Create a real, formatted Excel workbook for downloaded analysis results."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo
    display=data.drop(columns=["risk_reasons_json","recommended_actions_json"],errors="ignore").copy()
    display=localize_values(display)
    if "risk_level" in display:display["risk_level"]=display["risk_level"].map(RISK_LABELS).fillna(display["risk_level"])
    if "case_status" in display:display["case_status"]=display["case_status"].map(tr_text)
    for col in ["risk_reasons","recommended_actions"]:
        if col in display:display[col]=display[col].map(tr_text)
    display=rename_for_display(display)
    out=BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        display.to_excel(writer,index=False,sheet_name="Analiz Sonuçları")
        summary=pd.DataFrame({"Gösterge":["Süreç","İndirme zamanı","Toplam kayıt","Yüksek risk","Orta risk","Düşük risk"],"Değer":[tr_text(process_name),datetime.now().strftime("%d.%m.%Y %H:%M"),len(display),int((data.risk_level=="YUKSEK").sum()) if "risk_level" in data else 0,int((data.risk_level=="ORTA").sum()) if "risk_level" in data else 0,int((data.risk_level=="DUSUK").sum()) if "risk_level" in data else 0]})
        summary.to_excel(writer,index=False,sheet_name="Özet")
        for ws in writer.book.worksheets:
            ws.sheet_view.showGridLines=False;ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:cell.fill=PatternFill("solid",fgColor="175CD3");cell.font=Font(color="FFFFFF",bold=True);cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
            ws.row_dimensions[1].height=34
            for idx,column in enumerate(ws.columns,1):
                values=[str(c.value) if c.value is not None else "" for c in list(column)[:250]];width=min(55,max(12,max((len(v) for v in values),default=10)+2));ws.column_dimensions[get_column_letter(idx)].width=width
                header=str(ws.cell(1,idx).value or "")
                if any(x in header for x in ["Tutar","Gelir","Değer","Bakiye","Limit","Kayıp","Ücret"]):
                    for cell in ws[get_column_letter(idx)][1:]:cell.number_format='#,##0.00'
                if header in ["İşlem Tarihi","İşlem Tarihi ve Saati","Kayıt Tarihi","İndirme zamanı"] or header.endswith(" Tarihi"):
                    for cell in ws[get_column_letter(idx)][1:]:cell.number_format='dd.mm.yyyy hh:mm'
                if "Oranı" in header:
                    for cell in ws[get_column_letter(idx)][1:]:cell.number_format='0.00'
                if header in ["Risk Gerekçeleri","Önerilen Kontrol Aksiyonları"]:
                    ws.column_dimensions[get_column_letter(idx)].width=55
                    for cell in ws[get_column_letter(idx)][1:]:cell.alignment=Alignment(vertical="top",wrap_text=True)
            if ws.max_row>1 and ws.max_column>0:
                table=Table(displayName="RiskResults" if ws.title=="Analiz Sonuçları" else "RiskSummary",ref=ws.dimensions);table.tableStyleInfo=TableStyleInfo(name="TableStyleMedium2",showRowStripes=True,showColumnStripes=False);ws.add_table(table)
    return out.getvalue()

@st.cache_data(scope="session", show_spinner=False)
def process_template_excel(process_name, required_fields, optional_fields=()):
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    required=list(required_fields);optional=list(optional_fields);fields=required+optional
    boolean_fields={"new_recipient","new_currency_or_country","exception_flag","related_party","pep","missing_documents","beneficial_owner_missing","address_mismatch","remote_onboarding","new_device","card_present","manual_entry","weekend_entry","same_creator_approver","period_end","missing_description","reversal_24h","vendor_employee_match","duplicate_invoice","single_source","terminated_employee","manager_approval","employee_vendor_match","critical_asset","privileged_account","unapproved_change","unusual_pnl","manual_price","same_dealer_approver","same_maker_checker","vault_access_offhours","document_missing","cash_transaction","high_risk_country","source_of_funds_missing","bulk_export","off_hours_access","business_purpose_missing","external_share","unencrypted_file","access_role_mismatch","vulnerable_customer","root_cause_missing","product_suitability_issue","collateral_expired","same_collector_approver","first_time_counterparty","out_of_hours","approval_override","cross_border","third_party_account"}
    def field_meta(field):
        if field in ["transaction_datetime","event_date"]:return "Tarih / saat","21.08.2026 14:35"
        if field in boolean_fields:return "Evet / Hayır","Evet"
        if field=="transaction_type":return "Listeden seçim",transaction_types(process_name)[0] if transaction_types(process_name) else "İşlem türü"
        if any(x in field for x in ["amount","value","income","salary","ratio","score","count","days","hour","limit","age","loss","difference","bps"]):return "Sayısal","100"
        return "Metin","Örnek değer"
    out=BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        pd.DataFrame(columns=turkish_columns(fields)).to_excel(writer,index=False,sheet_name="Veri Girişi")
        guide=[]
        for field in fields:
            dtype,example=field_meta(field);guide.append({"Türkçe sütun adı":field_label(field),"Zorunlu mu?":"Evet" if field in required else "Hayır","Veri tipi":dtype,"Örnek":example})
        pd.DataFrame(guide).to_excel(writer,index=False,sheet_name="Veri Rehberi")
        for ws in writer.book.worksheets:
            ws.sheet_view.showGridLines=False;ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:cell.fill=PatternFill("solid",fgColor="175CD3");cell.font=Font(color="FFFFFF",bold=True);cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
            ws.row_dimensions[1].height=38
            for idx,column in enumerate(ws.columns,1):
                values=[str(c.value or "") for c in list(column)[:200]];ws.column_dimensions[get_column_letter(idx)].width=min(42,max(15,max((len(v) for v in values),default=12)+3))
        entry=writer.book["Veri Girişi"]
        for idx,field in enumerate(fields,1):
            required_text="Zorunlu alan" if field in required else "İsteğe bağlı alan";entry.cell(1,idx).comment=Comment(f"{required_text}. Ayrıntı için Veri Rehberi sayfasına bakın.","Risk Ajansı")
            dtype,_=field_meta(field)
            if dtype=="Evet / Hayır":dv=DataValidation(type="list",formula1='"Evet,Hayır"',allow_blank=field not in required);entry.add_data_validation(dv);dv.add(f"{get_column_letter(idx)}2:{get_column_letter(idx)}5000")
            if field=="transaction_type" and transaction_types(process_name):dv=DataValidation(type="list",formula1='"'+','.join(transaction_types(process_name))+'"',allow_blank=True);entry.add_data_validation(dv);dv.add(f"{get_column_letter(idx)}2:{get_column_letter(idx)}5000")
    return out.getvalue()

user=login();tenant_id=user.get("tenant_id","default");set_platform_tenant(tenant_id);set_case_tenant(tenant_id);set_v14_tenant(tenant_id);set_security_tenant(tenant_id);security_cfg=get_security_settings();now_ts=time.time()
if now_ts-st.session_state.get("last_activity",now_ts)>security_cfg["idle_timeout_minutes"]*60 or now_ts-st.session_state.get("login_started",now_ts)>security_cfg["absolute_timeout_hours"]*3600:
    st.session_state.pop("user",None);st.session_state.session_expired=True;st.rerun()
st.session_state.last_activity=now_ts
admin=user["role"]=="Yonetici"; editable=user["role"] in ["Yonetici","Inceleyen","Onaylayan"]; rules=get_rules();custom_df=list_custom_rules(active_only=True);custom_records=custom_df.to_dict("records");process_override_df=get_process_rule_overrides()
organization=get_organization_settings();st.markdown(f"<style>:root{{--blue:{organization['accent_color']}}}</style>",unsafe_allow_html=True)
names=["Operasyon merkezi","Anlık tarama","Risk panosu","İşlem listesi","Vaka detayı","Süreç merkezi","Veri setleri","Veri kalitesi","Yönetici raporu","Adaptif kontrol","Vaka asistanı","Güvenlik merkezi"]+(["Research Lab","Entegrasyon merkezi","API yönetimi","Senaryo stüdyosu","Kural yönetimi","Sistem yönetimi"] if admin else [])
nav_icons={"Anlık tarama":"🔍","Operasyon merkezi":"🏠","Risk panosu":"📊","İşlem listesi":"📋","Vaka detayı":"🔎","Süreç merkezi":"🧩","Veri setleri":"🗄️","Veri kalitesi":"✅","Yönetici raporu":"📈","Adaptif kontrol":"🧠","Vaka asistanı":"✨","Güvenlik merkezi":"🔐","Entegrasyon merkezi":"🔌","API yönetimi":"🔑","Senaryo stüdyosu":"🧪","Kural yönetimi":"⚙️","Sistem yönetimi":"🏢"}
if st.session_state.get("main_navigation") not in names:st.session_state.main_navigation=names[0]
process_options=["Para Transferleri"]+list(PROCESS_DEFINITIONS)
if st.session_state.get("active_process") not in process_options:st.session_state.active_process=process_options[0]
active_process=st.session_state.active_process
def process_overrides(process_name):
    return process_override_df[process_override_df.process==process_name].to_dict("records") if len(process_override_df) else []
def activate_upload(process_name, widget_key):
    selected = st.session_state.get(widget_key)
    st.session_state[f"current_upload_{tenant_id}_{user['username']}_{process_name}"] = selected
    if selected is not None:
        st.session_state[f"source_{process_name}"] = "Kendi CSV / Excel dosyam"
st.markdown('<div class="hero"><div class="hero-kicker">Açıklanabilir risk teknolojisi</div><h1>İç Kontrol Risk Ajansı</h1><p>İşlemleri, süreçleri ve kontrol vakalarını tek merkezden yönetin.</p><div class="hero-badge">● Sistem aktif · Yerel ve denetlenebilir analiz</div></div>',unsafe_allow_html=True)
with st.sidebar:
    st.caption("Özel demo oturumu · Yalnızca sentetik veri kullanın. Oturum sona erdiğinde bu çalışma alanı silinir.")
    st.markdown("[Önceki sürüm ve eski yedekler](?view=classic)")
    if organization.get("logo"):st.image(organization["logo"],width=150)
    st.markdown(f'<div class="sidebar-brand"><strong>🛡️ {escape(organization["organization_name"])}</strong><small>Kontrol ve vaka çalışma alanı</small></div>',unsafe_allow_html=True)
    st.write(f"**{user['username']}** — {tr_text(user['role'])}")
    st.caption(f"Çalışma alanı: {organization['organization_name']}")
    if st.button("Güvenli çıkış",width="stretch"):log_event(user["username"],"CIKIS","session","local");del st.session_state.user;st.rerun()
    st.divider();st.markdown("#### Aktif senaryo / süreç");st.info(f"Seçili: **{tr_text(active_process)}**\n\nSüreç seçimini ana ekranın üst bölümünden değiştirebilirsiniz.")
    required_fields=REQUIRED_COLUMNS if active_process=="Para Transferleri" else PROCESS_DEFINITIONS[active_process]["fields"];optional_fields=list(dict.fromkeys((OPTIONAL_COLUMNS if active_process=="Para Transferleri" else [])+expanded_optional_fields(active_process)))
    template_name=tr_text(active_process).replace("/","-").replace(" ","_")+"_veri_sablonu.xlsx"
    st.download_button("📥 Türkçe Excel şablonunu indir",process_template_excel(active_process,tuple(required_fields),tuple(optional_fields)),template_name,mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
    source=st.radio("Veri kaynağı",["Sentetik demo","Kendi CSV / Excel dosyam","Kalıcı veri seti"],key=f"source_{active_process}");uploaded=None;persistent_dataset_id=None
    with st.expander(f"Zorunlu alanlar · {len(required_fields)}"):st.dataframe(pd.DataFrame({"Türkçe sütun adı":turkish_columns(required_fields)}),hide_index=True,width="stretch")
    if optional_fields:
        with st.expander(f"İsteğe bağlı alanlar · {len(optional_fields)}"):st.dataframe(pd.DataFrame({"Türkçe sütun adı":turkish_columns(optional_fields)}),hide_index=True,width="stretch")
    if source.startswith("Kendi"):
        st.file_uploader(f"{tr_text(active_process)} dosyasını seçin",type=["csv","xlsx"],key=f"upload_{active_process}",on_change=activate_upload,args=(active_process,f"upload_{active_process}"))
        uploaded=st.session_state.get(f"current_upload_{tenant_id}_{user['username']}_{active_process}")
        if uploaded is not None:
            st.caption(f"Analizde kullanılan dosya: {uploaded.name}")
    elif source=="Kalıcı veri seti":
        persistent_options=list_datasets(active_process)
        if persistent_options.empty:st.info("Bu süreçte henüz kalıcı veri seti yok. Veri Setleri ekranından oluşturabilirsiniz.")
        else:persistent_dataset_id=st.selectbox("Veri seti",persistent_options.id.tolist(),format_func=lambda x:f"{persistent_options[persistent_options.id==x].iloc[0]['name']} · {persistent_options[persistent_options.id==x].iloc[0]['period']} · {int(persistent_options[persistent_options.id==x].iloc[0]['record_count'])} kayıt",key=f"persistent_{active_process}")
try:
    transfer_demo=demo(json.dumps(rules,sort_keys=True),json.dumps(custom_records,sort_keys=True,default=str))
    quality_issues=pd.DataFrame();quality_summary={"rows":0,"columns":0,"errors":0,"warnings":0,"missing":0};raw_input=None;mapping_preview=pd.DataFrame();upload_hash=None;analysis_authorized=False;source_pending=(source.startswith("Kendi") and uploaded is None) or (source=="Kalıcı veri seti" and persistent_dataset_id is None)
    if source.startswith("Kendi") and uploaded is not None:
        raw_input=read_file(uploaded.getvalue(),uploaded.name);expected_fields=list(required_fields)+list(optional_fields);mapping_preview=suggest_mapping(raw_input.columns,expected_fields,get_data_mapping(active_process));missing_map=missing_required(mapping_preview,required_fields)
        if missing_map:
            st.warning("Dosyanızdaki bazı sütunlar otomatik eşleştirilemedi. Analize devam etmek için aşağıdaki zorunlu alanları eşleştirin: "+", ".join(field_label(x) for x in missing_map))
            label_to_field={field_label(x):x for x in expected_fields};mapping_editor=mapping_preview.copy();mapping_editor["Sistemdeki Karşılığı"]=mapping_editor["Sistemdeki Karşılığı"].map(lambda x:field_label(x) if x else "Seçilmedi")
            edited_mapping=st.data_editor(mapping_editor,hide_index=True,width="stretch",disabled=["Kurumdaki Sütun","Türkçe Alan","Güven (%)","Eşleştirme Yöntemi"],column_config={"Sistemdeki Karşılığı":st.column_config.SelectboxColumn("Sistemdeki Karşılığı",options=["Seçilmedi"]+list(label_to_field))},key=f"blocking_mapping_{active_process}")
            if st.button("Eşleştirmeyi kaydet ve analizi başlat",type="primary",width="stretch",key=f"save_blocking_mapping_{active_process}"):
                chosen={str(row["Kurumdaki Sütun"]):label_to_field.get(str(row["Sistemdeki Karşılığı"]),"") for _,row in edited_mapping.iterrows() if str(row["Sistemdeki Karşılığı"])!="Seçilmedi"};save_data_mapping(active_process,chosen,user["username"]);st.success("Kurum eşleştirmesi kaydedildi.");st.rerun()
            st.stop()
        normalized_input=apply_mapping(raw_input,mapping_dict(mapping_preview),expected_fields);normalized_input,quality_issues,quality_summary=quality_report(normalized_input,list(required_fields),list(optional_fields));file_hash=hashlib.sha256(uploaded.getvalue()).hexdigest();upload_hash=file_hash;analysis_authorized=bool(st.session_state.get(f"analysis_authorized_{active_process}_{file_hash}",False))
        record_upload(user["username"],active_process,uploaded.name,file_hash,quality_summary["rows"],quality_summary["errors"],"HATALI" if quality_summary["errors"] else "BAŞARILI")
        if quality_summary["errors"]:
            st.error(f"Dosyada {quality_summary['errors']} düzeltmeniz gereken hata bulundu. Aşağıdaki Veri Kalitesi Raporunu inceleyin.")
            qm=st.columns(4);qm[0].metric("Satır",quality_summary["rows"]);qm[1].metric("Sütun",quality_summary["columns"]);qm[2].metric("Hata",quality_summary["errors"]);qm[3].metric("Uyarı",quality_summary["warnings"])
            st.dataframe(quality_issues,hide_index=True,width="stretch");st.download_button("Hatalı satır raporunu Excel olarak indir",dataframe_excel(quality_issues,"Veri Kalitesi Hataları"),f"{tr_text(active_process).replace('/','-')}_hatali_satirlar.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch");st.stop()
    elif source=="Kalıcı veri seti":
        if persistent_dataset_id is not None:
            raw_input=load_dataset(persistent_dataset_id);normalized_input,quality_issues,quality_summary=quality_report(raw_input,list(required_fields),list(optional_fields))
            if quality_summary["errors"]:st.error("Kalıcı veri setinde düzeltilmesi gereken veri kalitesi hataları var. Veri Kalitesi ekranını inceleyin.");st.dataframe(quality_issues,hide_index=True,width="stretch");st.stop()
    if active_process=="Para Transferleri":
        if source=="Sentetik demo" or source_pending:scored=transfer_demo
        else:
            rules_json=json.dumps(rules,sort_keys=True);custom_json=json.dumps(custom_records,sort_keys=True,default=str);scored=score_transfer_cached(normalized_input,rules_json,custom_json)
        active_df=scored.copy();active_id="transaction_id";active_date="transaction_datetime"
    else:
        scored=transfer_demo
        if source=="Sentetik demo" or source_pending:process_input=None
        else:process_input=normalized_input
        effective_overrides={int(x["rule_index"]):dict(x) for x in process_overrides(active_process)};selected_rule_indices=st.session_state.get(f"analysis_scenarios_{active_process}",list(range(len(PROCESS_DEFINITIONS[active_process]["rules"]))))
        for rule_index in range(len(PROCESS_DEFINITIONS[active_process]["rules"])):
            if rule_index not in selected_rule_indices:effective_overrides[rule_index]={"rule_index":rule_index,"active":0}
        override_json=json.dumps(list(effective_overrides.values()),sort_keys=True,default=str);active_df=process_demo_cached(active_process,override_json) if source=="Sentetik demo" or source_pending else score_process_cached(process_input,active_process,override_json);active_id="record_id";active_date="event_date"
    base_scores = active_df
    published_scenarios = list_dynamic_scenarios(active_process, active_only=True)
    active_df = apply_dynamic_scenarios(base_scores, published_scenarios)
except Exception as e:st.error(f"Dosya analiz edilemedi: {e}");st.stop()

cases=load_cases();status_map=cases.set_index("transaction_id")["status"].to_dict() if len(cases) else {};scored["case_status"]=scored["transaction_id"].astype(str).map(status_map).fillna("Yeni")
view=scored.copy()
view=mask_dataframe(view,user["role"])
source_label="Veri seçimi bekleniyor · geçici demo" if source_pending else "Yüklenen kurum verisi" if source.startswith("Kendi") else "Kalıcı veri seti" if source=="Kalıcı veri seti" else "Sentetik demo verisi"
st.markdown('<div class="process-selector-label">Senaryo / süreç seçimi</div>',unsafe_allow_html=True)
active_process=st.selectbox("Senaryo / süreç seçimi",process_options,key="active_process",format_func=tr_text,label_visibility="collapsed",help="Seçtiğiniz süreç; veri şablonunu, risk analizlerini, vaka ekranlarını ve kuralları birlikte günceller.")
st.markdown(f'<div class="process-selector-note">{source_label} · Tüm analiz ekranları <b>{tr_text(active_process)}</b> süreciyle eşitlendi.</div>',unsafe_allow_html=True)
def select_mobile_page():
    st.session_state.main_navigation = st.session_state.mobile_page

with st.container(key="desktop_navigation"):
    page=st.radio("Çalışma ekranı",names,key="main_navigation",horizontal=True,label_visibility="collapsed",format_func=lambda x:f"{nav_icons.get(x,'•')}  {x}")
with st.container(key="mobile_navigation"):
    st.session_state.mobile_page = page
    st.selectbox("Çalışma ekranı", names, key="mobile_page", on_change=select_mobile_page)

if page=="Research Lab" and admin:
    from suite.research_lab import render
    render()
    st.stop()

active_case_ids=active_df[active_id].astype(str) if active_process=="Para Transferleri" else active_process+":"+active_df[active_id].astype(str)
active_status_map=cases.set_index("transaction_id")["status"].to_dict() if len(cases) else {};active_df["case_status"]=active_case_ids.map(active_status_map).fillna("Yeni")
if len(cases):
    case_index=cases.set_index("transaction_id")
    for case_field,default in [("priority","Orta"),("due_date",""),("analyst",""),("reviewer",""),("assigned_team","")]:active_df[case_field]=active_case_ids.map(case_index[case_field].to_dict()).fillna(default) if case_field in case_index else default
active_df=mask_dataframe(active_df,user["role"])
active_high=int((active_df.risk_level=="YUKSEK").sum());active_closed=int(active_df.case_status.isin(["Kapatildi","Yanlis alarm"]).sum())
for col,(label,value) in zip(st.columns(5),[("Toplam kayıt",len(active_df)),("Yüksek risk",active_high),("Açık vaka",len(active_df)-active_closed),("Kapatılan",active_closed),("Ortalama skor",f"{active_df.risk_score.mean():.1f}/100")]):col.metric(label,value)
notifications=sla_notifications(active_df,active_date,rules)
queue_key = f"work_queue_{active_process}"
position_key = f"list_position_{active_process}"
origin_key = f"case_origin_{active_process}"
all_records = "Tüm kayıtlar"
open_cases = ~active_df.case_status.isin(["Kapatildi", "Yanlis alarm", "Risk dogrulandi"])
analyst = active_df.get("analyst", pd.Series("", index=active_df.index)).fillna("")
reviewer = active_df.get("reviewer", pd.Series("", index=active_df.index)).fillna("")
sla_alerts = notifications.get("Bildirim", pd.Series(dtype=str))
sla_hours = notifications.get("Kalan saat", pd.Series(dtype=float))
work_queues = {
    "SLA aşıldı": active_df.index.isin(sla_alerts.index[sla_alerts.eq("SLA aşıldı")]),
    "Süresi yaklaşanlar": active_df.index.isin(sla_alerts.index[sla_alerts.eq("SLA yaklaşıyor")]),
    "Bana atananlar": open_cases & (analyst.eq(user["username"]) | reviewer.eq(user["username"])),
    "Atanmamış yüksek riskler": open_cases & analyst.str.strip().eq("") & active_df.risk_level.eq("YUKSEK"),
}

def enter_queue(label):
    st.session_state[queue_key] = label
    st.session_state[position_key] = 1
    st.session_state.pop(f"list_memory_{active_process}", None)
    st.session_state.main_navigation = "İşlem listesi"

def show_case(record_id, origin, sequence):
    st.session_state[f"case_{active_process}"] = record_id
    st.session_state[f"review_sequence_{active_process}"] = sequence
    st.session_state[origin_key] = origin
    st.session_state.main_navigation = "Vaka detayı"

def open_selected_case(table_key, ids, origin, sequence):
    rows = st.session_state[table_key].selection.rows
    if rows and 0 <= rows[0] < len(ids):
        show_case(ids[rows[0]], origin, sequence)

def case_table(frame, display, key, origin, height, sequence=None):
    ids = frame[active_id].astype(str).tolist()
    st.dataframe(display, hide_index=True, width="stretch", height=height, key=key,
                 selection_mode="single-row", on_select=lambda: open_selected_case(
                     key, ids, origin, ids if sequence is None else sequence))

def return_to_origin(origin):
    st.session_state.main_navigation = origin

if page=="Anlık tarama":
    st.subheader("Anlık tarama")
    scope = f"{page}_{user['username']}_{tenant_id}_{active_process}"
    text_key = f"scan_text_{scope}"
    example = ("65 yaş ve üzerindeki ve en az 365 gündür hareketsiz olan hesapları göster" if active_process == "Para Transferleri"
               else "Risk Skoru en az 70 olan kayıtları göster")
    if text_key not in st.session_state:
        st.session_state[text_key] = st.session_state.get(f"scan_draft_{scope}", "")
    with st.form(f"instant_form_{scope}"):
        query = st.text_area("Neyi kontrol etmek istiyorsun?", placeholder=example, key=text_key, height=100, max_chars=2000)
        scan_clicked = st.form_submit_button("Verileri tara", type="primary", disabled=source_pending)
    st.session_state[f"scan_draft_{scope}"] = query
    scope_signature = (query, source, upload_hash, persistent_dataset_id)
    result_key = f"scan_result_{scope}"
    if source_pending:
        st.info("Taramak için bir dosya veya veri seti seç.")
    if scan_clicked:
        st.session_state.pop(result_key,None)
        try:
            terms, logic = instant_filter(query, active_df, active_process)
            st.session_state[result_key] = (scope_signature, terms, logic)
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("Soru şu anda yorumlanamadı. Yeniden deneyebilir veya alan adıyla birlikte bir eşik yazabilirsin.")
    result = st.session_state.get(result_key)
    if not source_pending and result and result[0] == scope_signature:
        _, terms, logic = result
        mask = scenario_mask(active_df, terms, logic)
        hits = active_df.loc[mask].sort_values("risk_score", ascending=False, kind="stable")
        st.subheader("Tarama sonucu")
        st.write(f"{source_label} · {len(active_df):,} kayıt tarandı, {len(hits):,} kayıt eşleşti.".replace(",", "."))
        st.caption((" " + logic + " ").join(f"{field_label(t['field'])} {t['operator']} {t['value']}" for t in terms))
        if len(hits):
            fields = list(dict.fromkeys([active_id, active_date, *[t["field"] for t in terms], "risk_score"]))
            display = rename_for_display(hits[fields])
            case_table(hits, display, f"scan_hits_{scope}", page, 380)
            st.download_button("Eşleşen kayıtları indir",display.to_csv(index=False).encode("utf-8-sig"),"senaryo_eslesmeleri.csv","text/csv")
        else:
            st.info("Bu koşulları karşılayan kayıt bulunamadı.")
    with st.expander("Kullanılabilecek alanlar"):
        st.dataframe(pd.DataFrame([{"Alan":field_label(f),"Teknik adı":f} for f in active_df.columns]),hide_index=True)
if page=="Operasyon merkezi":
    st.subheader(f"{organization['organization_name']} · Operasyon Merkezi")
    st.caption(f"{tr_text(active_process)} sürecinin güncel kontrol görünümü")
    if user["role"] in ("Yonetici","Onaylayan"):
        history = review_history(active_process)
        if not history.empty:
            with st.expander("Senaryo onayları", expanded=history.status.eq("Bekliyor").any().item()):
                for request in history.itertuples():
                    st.markdown(f"**{request.name} · v{request.version} · {request.action}**")
                    st.write(f"{request.status} · Talep eden: {request.maker} · {request.requested_at} UTC")
                    st.write(request.justification)
                    st.write(json.loads(request.evidence))
                    st.caption(f"{request.logic} · +{request.points} puan")
                    st.dataframe(pd.DataFrame(json.loads(request.conditions_json)), hide_index=True)
                    if request.status != "Bekliyor":
                        st.caption(f"Karar veren: {request.reviewer} · {request.decided_at} UTC")
                    elif user["username"] == request.maker or (request.action == "Etkinleştir" and user["username"] == request.created_by):
                        st.caption("Karar için aynı demo oturumunda başka bir yönetici veya onaylayan hesabıyla giriş yapın.")
                    else:
                        for col, label, decision in zip(st.columns(2), ["Onayla","Reddet"], [True,False]):
                            if col.button(label,key=f"decision_{request.id}_{decision}"):
                                try:
                                    decide_review(request.id, user["username"], decision)
                                    st.rerun()
                                except ValueError as error:
                                    st.error(str(error))
    st.subheader("Bugünkü işlerim")
    for column, (label, mask) in zip(st.columns(len(work_queues)), work_queues.items()):
        column.button(f"{label} · {int(mask.sum())}", on_click=enter_queue, args=(label,), width="stretch")
    st.caption(f"Atanmamış açık vaka sayısı: {int((open_cases & analyst.str.strip().eq('')).sum())}")
    left,right=st.columns([1.5,1])
    with left:
        st.markdown("#### Öncelikli çalışma listesi")
        priority=active_df.loc[open_cases].sort_values(["risk_score",active_date],ascending=[False,True]).head(15);priority_cols=[active_id,"customer_id",active_date,"risk_score","risk_level","case_status"];priority_display=rename_for_display(priority[[c for c in priority_cols if c in priority]].copy());case_table(priority, priority_display, f"priority_rows_{active_process}", "Operasyon merkezi", 360)
    with right:
        st.markdown(f"#### Bildirim merkezi · {len(notifications)}")
        if notifications.empty:st.success("Yaklaşan veya aşılmış SLA bildirimi bulunmuyor.")
        else:st.dataframe(notifications.sort_values("Kalan saat").round({"Kalan saat": 1}),hide_index=True,width="stretch",height=360)
    open_statuses=[x for x in CASE_STATUSES if x not in ["Kapatildi","Yanlis alarm","Risk dogrulandi"]];my_work=cases[(cases.status.isin(open_statuses))&((cases.analyst==user["username"])|(cases.reviewer==user["username"]))].copy() if len(cases) else pd.DataFrame()
    with st.expander(f"🔔 Uygulama içi görev ve onay bildirimleri · {len(my_work)}",expanded=bool(len(my_work))):
        if my_work.empty:st.success("Size atanmış açık görev veya onay bekleyen vaka bulunmuyor.")
        else:
            my_work["due_dt"]=pd.to_datetime(my_work.due_date,errors="coerce");today=pd.Timestamp.now().normalize();my_work["Bildirim"]=my_work.apply(lambda row:"Onayınız bekleniyor" if row.get("reviewer")==user["username"] and row.get("status")=="Onay bekliyor" else "Son tarih aşıldı" if pd.notna(row["due_dt"]) and row["due_dt"]<today else "İnceleme görevi",axis=1)
            nm=st.columns(3);nm[0].metric("İnceleme görevim",int((my_work.analyst==user["username"]).sum()));nm[1].metric("Onayım bekleniyor",int(((my_work.reviewer==user["username"])&(my_work.status=="Onay bekliyor")).sum()));nm[2].metric("Geciken",int((my_work["Bildirim"]=="Son tarih aşıldı").sum()))
            notice_cols=["case_number","transaction_id","priority","status","assigned_team","due_date","Bildirim"];notice_display=my_work[[c for c in notice_cols if c in my_work]].rename(columns={"case_number":"Vaka numarası","transaction_id":"Kayıt","priority":"Öncelik","status":"Durum","assigned_team":"Ekip","due_date":"Son tarih"});notice_display["Durum"]=notice_display["Durum"].map(tr_text);st.dataframe(notice_display,hide_index=True,width="stretch")
            st.download_button("Görev listemi Excel olarak indir",dataframe_excel(notice_display,"Görevlerim"),f"gorevlerim_{datetime.now():%Y%m%d}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
    st.info("Risk Panosu analiz eğilimlerini, İşlem Listesi filtreleme ve toplu işlemleri, Vaka Detayı ise inceleme ve kanıt akışını içerir.")
if page=="Risk panosu":
    dashboard_process=active_process;dashboard_df=active_df;dashboard_date=active_date;dashboard_id=active_id
    dm=st.columns(4);dm[0].metric("Seçili süreç",tr_text(dashboard_process));dm[1].metric("Toplam kayıt",len(dashboard_df));dm[2].metric("Yüksek risk",int((dashboard_df.risk_level=="YUKSEK").sum()));dm[3].metric("Ortalama skor",f"{dashboard_df.risk_score.mean():.1f}/100")
    l,r=st.columns(2)
    with l:st.subheader("Risk dağılımı");st.bar_chart(dashboard_df.risk_level.value_counts().rename(index=RISK_LABELS),horizontal=True,color="#d24b58")
    with r:
        if dashboard_process=="Para Transferleri":st.subheader("Vaka durumları");st.bar_chart(dashboard_df.case_status.value_counts().rename(index=tr_text),horizontal=True,color="#2457a7")
        else:
            st.subheader("Risk skoru bantları");bands=pd.cut(dashboard_df.risk_score,[-1,19,39,59,79,100],labels=["0–19","20–39","40–59","60–79","80–100"]);st.bar_chart(bands.value_counts().sort_index(),horizontal=True,color="#2457a7")
    trend=dashboard_df.assign(gun=pd.to_datetime(dashboard_df[dashboard_date]).dt.date).groupby("gun").agg(İşlem=(dashboard_id,"count"),Yüksek=("risk_level",lambda x:(x=="YUKSEK").sum()))
    with st.expander(f"📈 Günlük eğilim · {len(trend)} gün",expanded=False):
        st.caption("Toplam kayıt ve yüksek riskli kayıt sayısının günlere göre değişimi")
        st.line_chart(trend,color=["#175cd3","#d92d20"],height=360)
    all_reason_counts=dashboard_df.risk_reasons.str.split(r" \| ").explode().map(tr_text);all_reason_counts=all_reason_counts[~all_reason_counts.str.contains("Tetiklenen",na=False)].str.replace(r"^\+\d+: ","",regex=True).value_counts()
    process_key=str(abs(hash(dashboard_process)));default_reasons=all_reason_counts.head(min(8,len(all_reason_counts))).index.tolist()
    with st.expander(f"📊 Risk göstergeleri · {len(all_reason_counts)} senaryo",expanded=False):
        st.caption("En çok tetiklenen göstergeleri karşılaştırın. Senaryo seçimini ayarlar düğmesinden değiştirebilirsiniz.")
        rc1,rc2,rc3=st.columns([1.2,1.2,2.6])
        with rc1.popover("⚙️ Senaryoları seç",width="stretch"):
            selected_reasons=st.multiselect("Gösterilecek senaryolar",all_reason_counts.index.tolist(),default=default_reasons,key=f"risk_indicator_selection_{process_key}")
        sort_mode=rc2.selectbox("Sıralama",["Frekans - azalan","Alfabetik"],key=f"risk_indicator_sort_{process_key}",label_visibility="collapsed")
        rc3.markdown(f"<div style='padding:9px 12px;color:#667085;font-size:13px'>{len(default_reasons)} gösterge varsayılan olarak seçildi</div>",unsafe_allow_html=True)
        if selected_reasons:
            reason_counts=all_reason_counts.reindex(selected_reasons).fillna(0)
            reason_counts=reason_counts.sort_values(ascending=False) if sort_mode=="Frekans - azalan" else reason_counts.sort_index()
            st.bar_chart(reason_counts,horizontal=True,color="#6938ef",height=max(300,min(520,36*len(reason_counts))))
            if st.toggle("Tam adları ve adetleri tablo olarak göster",key=f"risk_indicator_table_{process_key}"):
                st.dataframe(reason_counts.rename("Tetiklenme adedi").rename_axis("Risk senaryosu").reset_index(),hide_index=True,width="stretch")
        else:st.info("Grafik için ayarlar bölümünden en az bir risk senaryosu seçin.")
if page=="İşlem listesi":
    with st.expander("🧭 Analiz Çalıştırma Merkezi", expanded=st.session_state.get(queue_key, all_records) == all_records):
        st.caption("Dosyanızı yükleyin, veri kalitesini ve eşleştirmeleri kontrol edin, çalışacak senaryoları seçin ve analizi başlatın.")
        up_left,up_right=st.columns([2.2,1])
        with up_left:st.file_uploader(f"{tr_text(active_process)} verisini yükleyin",type=["csv","xlsx"],key=f"list_scan_upload_{active_process}",help="Türkçe veya kuruma özel sütun adlarını kullanabilirsiniz.",on_change=activate_upload,args=(active_process,f"list_scan_upload_{active_process}"))
        with up_right:st.download_button("Boş veri şablonunu indir",process_template_excel(active_process,tuple(required_fields),tuple(optional_fields)),template_name,mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch",key=f"list_template_{active_process}")
        if raw_input is not None and upload_hash:
            qc=st.columns(4);qc[0].metric("Dosya satırı",quality_summary["rows"]);qc[1].metric("Sütun",quality_summary["columns"]);qc[2].metric("Veri hatası",quality_summary["errors"]);qc[3].metric("Uyarı",quality_summary["warnings"])
            with st.expander("👁️ Yüklenen verinin ilk 20 satırını ön izle",expanded=not analysis_authorized):st.dataframe(rename_for_display(raw_input.head(20)),hide_index=True,width="stretch")
            if not mapping_preview.empty:
                with st.expander("🔗 Sütun eşleştirmelerini incele ve kuruma kaydet",expanded=False):
                    st.caption("Kaydettiğiniz eşleştirmeler yalnızca bu kurumun seçili sürecinde sonraki yüklemelerde uygulanır.")
                    expected_fields=list(required_fields)+list(optional_fields);label_to_field={field_label(x):x for x in expected_fields};mapping_review=mapping_preview.copy();mapping_review["Sistemdeki Karşılığı"]=mapping_review["Sistemdeki Karşılığı"].map(lambda x:field_label(x) if x else "Seçilmedi")
                    reviewed_mapping=st.data_editor(mapping_review,hide_index=True,width="stretch",disabled=["Kurumdaki Sütun","Türkçe Alan","Güven (%)","Eşleştirme Yöntemi"],column_config={"Sistemdeki Karşılığı":st.column_config.SelectboxColumn("Sistemdeki Karşılığı",options=["Seçilmedi"]+list(label_to_field))},key=f"mapping_review_{active_process}")
                    if st.button("Kurum eşleştirmesini kaydet",width="stretch",key=f"save_mapping_review_{active_process}"):
                        chosen={str(row["Kurumdaki Sütun"]):label_to_field.get(str(row["Sistemdeki Karşılığı"]),"") for _,row in reviewed_mapping.iterrows() if str(row["Sistemdeki Karşılığı"])!="Seçilmedi"};save_data_mapping(active_process,chosen,user["username"]);st.success("Eşleştirme profili kaydedildi.")
            if active_process=="Para Transferleri":
                selected_rule_indices=[0];st.info("Para Transferleri için ana risk motoru ve yayımlanmış özel senaryolar birlikte çalıştırılacaktır.")
            else:
                rule_options=list(range(len(PROCESS_DEFINITIONS[active_process]["rules"])));selected_rule_indices=st.multiselect("Çalıştırılacak risk senaryoları",rule_options,default=st.session_state.get(f"analysis_scenarios_{active_process}",rule_options),format_func=lambda idx:tr_text(PROCESS_DEFINITIONS[active_process]["rules"][idx][0]),key=f"analysis_scenario_picker_{active_process}")
            prior_runs=list_analysis_runs(active_process);same_file=prior_runs[prior_runs.file_hash==upload_hash] if len(prior_runs) else pd.DataFrame()
            if len(same_file) and not analysis_authorized:st.warning(f"Bu dosya daha önce {same_file.iloc[0]['run_id']} çalışma numarasıyla analiz edilmiş. Yeniden çalıştırabilirsiniz.")
            if not analysis_authorized:
                if st.button("▶ Senaryoları tara ve analizi başlat",type="primary",width="stretch",disabled=not selected_rule_indices,key=f"start_analysis_{active_process}_{upload_hash}"):
                    if active_process!="Para Transferleri":st.session_state[f"analysis_scenarios_{active_process}"]=selected_rule_indices
                    st.session_state[f"analysis_authorized_{active_process}_{upload_hash}"]=True;st.rerun()
                st.info("Dosya hazır. Risk sonuçlarını oluşturmak için analizi başlatın.");st.stop()
            scenario_names=["Tüm transfer ve özel senaryolar"] if active_process=="Para Transferleri" else [tr_text(PROCESS_DEFINITIONS[active_process]["rules"][idx][0]) for idx in st.session_state.get(f"analysis_scenarios_{active_process}",selected_rule_indices)]
            run_id,is_new_run=record_analysis_run(active_process,uploaded.name if uploaded is not None else "Yüklenen dosya",upload_hash,active_df,scenario_names,user["username"])
            st.progress(1.0,text="Tarama tamamlandı · risk senaryoları uygulandı")
            st.success(f"Analiz tamamlandı. Çalışma numarası: {run_id}"+("" if is_new_run else " · Bu dosyanın önceki çalışma kaydı açıldı."))
        else:st.info("Analize başlamak için bu alandan veya sol menüden bir CSV/Excel dosyası yükleyin. Sentetik demo sonuçlarını aşağıda incelemeye devam edebilirsiniz.")
    queue = st.session_state.get(queue_key, all_records)
    if queue in work_queues:
        st.subheader(queue)
        st.button("Tüm kayıtları göster", on_click=enter_queue, args=(all_records,))
    memory_key = f"list_memory_{active_process}"
    memory = st.session_state.get(memory_key, {})
    saved_filters=list_saved_filters(user["username"],active_process);filter_options=["Yeni/geçici filtre"]+saved_filters.id.tolist();selected_filter=st.selectbox("Kayıtlı görünüm",filter_options,index=filter_options.index(memory["view"]) if memory.get("view") in filter_options else 0,format_func=lambda x:x if isinstance(x,str) else saved_filters[saved_filters.id==x].iloc[0]["name"],key=f"saved_filter_{active_process}");filter_cfg={}
    if not isinstance(selected_filter,str):filter_cfg=json.loads(saved_filters[saved_filters.id==selected_filter].iloc[0]["config_json"])
    if memory.get("view") == selected_filter:
        filter_cfg.update(memory)
    a,b,c,d=st.columns([1.2,1.3,1.6,2]);levels=a.multiselect("Risk seviyesi",["YUKSEK","ORTA","DUSUK"],default=filter_cfg.get("levels",["YUKSEK","ORTA","DUSUK"]),format_func=lambda x:RISK_LABELS[x],key=f"list_levels_{active_process}_{selected_filter}");score_range=b.slider("Skor aralığı",0,100,tuple(filter_cfg.get("score_range",[0,100])),key=f"list_score_{active_process}_{selected_filter}");statuses=c.multiselect("Vaka durumu",CASE_STATUSES,default=filter_cfg.get("statuses",CASE_STATUSES),format_func=tr_text,key=f"list_status_{active_process}_{selected_filter}");q=d.text_input("İşlem / müşteri ara",value=filter_cfg.get("query",""),key=f"list_query_{active_process}_{selected_filter}")
    filtered=active_df[active_df.risk_level.isin(levels)&active_df.risk_score.between(score_range[0],score_range[1],inclusive="both")&active_df.case_status.isin(statuses)].copy()
    current_filters = dict(view=selected_filter, levels=levels, score_range=score_range, statuses=statuses, query=q)
    if current_filters != memory:
        st.session_state[position_key] = 1
    st.session_state[memory_key] = current_filters
    if queue in work_queues:
        filtered = filtered.loc[filtered.index.isin(active_df.index[work_queues[queue]])].sort_values("risk_score", ascending=False)
    time_column = None
    if queue in ("SLA aşıldı", "Süresi yaklaşanlar"):
        overdue_queue = queue == "SLA aşıldı"
        time_column = "Gecikme (saat)" if overdue_queue else "Kalan süre (saat)"
        filtered[time_column] = sla_hours.reindex(filtered.index).abs()
        filtered = filtered.sort_values([time_column, "risk_score", active_id], ascending=[not overdue_queue, False, True])
        filtered[time_column] = filtered[time_column].round(1)
    if q:filtered=filtered[filtered[active_id].astype(str).str.contains(q,case=False,regex=False)|filtered.customer_id.astype(str).str.contains(q,case=False,regex=False)]
    preferred=[active_id,"customer_id",active_date,"transaction_type","source_channel","age","transaction_amount","loan_amount","amount","journal_amount","invoice_amount","payment_amount","deal_amount","exposure_amount","daily_transfer_total","daily_transaction_count","risk_score","risk_level","case_status"];cols=[c for c in preferred if c in filtered.columns]
    if time_column:
        cols.insert(1, time_column)
    filtered_display=filtered[cols].copy();filtered_display["risk_level"]=filtered_display["risk_level"].map(RISK_LABELS);filtered_display["case_status"]=filtered_display["case_status"].map(tr_text);filtered_display=rename_for_display(filtered_display)
    st.caption(f"Gösterilen süreç: {tr_text(active_process)} · {len(filtered)} kayıt listeleniyor")
    if filtered.empty:st.info("Seçilen risk seviyesi, skor aralığı, vaka durumu ve arama ölçütlerine uyan kayıt bulunamadı. Filtreleri genişletmeyi deneyin.")
    else:
        page_count = (len(filtered) + 49) // 50
        page_number = min(st.session_state.get(position_key, 1), page_count)
        if page_count > 1:
            widget_key = f"list_page_{active_process}"
            st.session_state[widget_key] = page_number
            def remember_page():
                st.session_state[position_key] = st.session_state[widget_key]
            st.number_input(f"Liste sayfası (1–{page_count})", 1, page_count, key=widget_key, on_change=remember_page)
        offset = (page_number - 1) * 50
        visible = filtered.iloc[offset:offset + 50]
        sequence = filtered[active_id].astype(str).tolist()
        with st.container(key="desktop_cases"):
            st.caption("Vaka detayını açmak için satırı seçin.")
            case_table(visible, filtered_display.iloc[offset:offset + 50], f"list_rows_{active_process}_{page_number}", "İşlem listesi", 430, sequence)
        with st.container(key="mobile_cases"):
            group_starts = list(range(0, len(visible), 5))
            start = 0
            if len(group_starts) > 1:
                group_key = f"mobile_group_{active_process}_{page_number}"
                remembered = st.session_state.get("mobile_group_memory", {}).get(group_key, 0)
                start = st.selectbox("Gösterilen kayıtlar", group_starts,
                                     index=group_starts.index(remembered) if remembered in group_starts else 0,
                                     format_func=lambda n: f"{offset+n+1}–{offset+min(n+5,len(visible))}",
                                     key=group_key)
                st.session_state.setdefault("mobile_group_memory", {})[group_key] = start
            for _, record in visible.iloc[start:start+5].iterrows():
                record_id = str(record[active_id])
                with st.container(border=True):
                    st.text(record_id)
                    if time_column:
                        st.caption(f"{time_column}: {record[time_column]:.1f}".replace(".", ","))
                    st.caption(f"{RISK_LABELS.get(record.risk_level, record.risk_level)} risk · {record.risk_score}/100 · {tr_text(record.case_status)}")
                    st.button("Vakayı aç", key=f"mobile_open_{active_process}_{record_id}", width="stretch",
                              on_click=show_case, args=(record_id, "İşlem listesi", sequence))
    st.download_button("Düzenlenmiş Excel indir",partial(styled_result_excel,filtered,active_process),f"{tr_text(active_process).replace('/','-').replace(' ','_')}_risk_analizi.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
    reason_summary=active_df.risk_reasons.str.split(r" \| ").explode().map(tr_text).value_counts().rename("Tetiklenme").rename_axis("Risk senaryosu").reset_index()
    with st.expander(f"📊 Senaryo tarama özeti · {len(reason_summary)} gösterge",expanded=False):st.dataframe(reason_summary,hide_index=True,width="stretch")
    run_history=list_analysis_runs(active_process)
    with st.expander(f"🕘 Analiz geçmişi · {len(run_history)} çalışma",expanded=False):
        if run_history.empty:st.info("Bu süreçte kaydedilmiş analiz çalışması yok.")
        else:
            history_display=run_history.drop(columns=["file_hash","scenarios_json"]).rename(columns={"run_id":"Çalışma numarası","process":"Süreç","file_name":"Dosya","row_count":"Kayıt","high_count":"Yüksek","medium_count":"Orta","low_count":"Düşük","created_by":"Çalıştıran","created_at":"Tarih"});history_display["Süreç"]=history_display["Süreç"].map(tr_text);st.dataframe(history_display,hide_index=True,width="stretch")
    with st.expander("💾 Görünümü kaydet veya sil",expanded=False):
        fc1,fc2=st.columns([2,1]);filter_name=fc1.text_input("Filtre adı",value="" if isinstance(selected_filter,str) else saved_filters[saved_filters.id==selected_filter].iloc[0]["name"],key=f"filter_name_{active_process}")
        if fc2.button("Görünümü kaydet",width="stretch",key=f"save_filter_{active_process}"):
            try:save_filter(user["username"],active_process,filter_name,{"levels":levels,"score_range":list(score_range),"statuses":statuses,"query":q});st.success("Görünüm kaydedildi.");st.rerun()
            except Exception as e:st.error(str(e))
        if not isinstance(selected_filter,str) and st.button("Seçili görünümü sil",key=f"delete_filter_{active_process}"):delete_saved_filter(int(selected_filter),user["username"]);st.rerun()
    if editable:
        with st.expander("⚡ Toplu Vaka ve İş Akışı Merkezi",expanded=False):
            st.caption("Riskli kayıtları seçin; inceleyen, bağımsız onaylayan, ekip, öncelik ve son tarih bilgileriyle toplu vaka oluşturun.")
            candidate_cols=[active_id,"customer_id","risk_score","risk_level","case_status"];candidate_table=filtered[[c for c in candidate_cols if c in filtered]].head(500).copy();candidate_table.insert(0,"Seç",False);candidate_table["risk_level"]=candidate_table["risk_level"].map(RISK_LABELS);candidate_table["case_status"]=candidate_table["case_status"].map(tr_text);candidate_table=rename_for_display(candidate_table).rename(columns={"Seç":"Seç"})
            selected_table=st.data_editor(candidate_table,hide_index=True,width="stretch",height=280,disabled=[c for c in candidate_table.columns if c!="Seç"],column_config={"Seç":st.column_config.CheckboxColumn("Seç",help="Vaka açılacak kayıt")},key=f"bulk_case_grid_{active_process}")
            selected_visible_ids=selected_table.loc[selected_table["Seç"],field_label(active_id)].astype(str).tolist();user_table=list_users();active_users=user_table[user_table.active==1].username.astype(str).tolist() if len(user_table) else [user["username"]]
            wf1,wf2,wf3=st.columns(3);bulk_analyst=wf1.selectbox("İnceleyen",active_users,index=active_users.index(user["username"]) if user["username"] in active_users else 0,key=f"bulk_create_analyst_{active_process}");reviewer_options=[""]+[x for x in active_users if x!=bulk_analyst];bulk_reviewer=wf2.selectbox("Onaylayan",reviewer_options,format_func=lambda x:x or "Daha sonra atanacak",key=f"bulk_create_reviewer_{active_process}");bulk_team=wf3.text_input("Atanan ekip",value=tr_text(active_process),key=f"bulk_create_team_{active_process}")
            wf4,wf5=st.columns(2);bulk_priority=wf4.selectbox("Öncelik",["Düşük","Orta","Yüksek","Kritik"],index=2,key=f"bulk_create_priority_{active_process}");bulk_due=wf5.date_input("Son tamamlanma tarihi",value=(pd.Timestamp.now()+pd.Timedelta(days=1)).date(),key=f"bulk_create_due_{active_process}")
            st.caption(f"Seçilen kayıt: {len(selected_visible_ids)} · Dört göz prensibi: inceleyen ve onaylayan aynı kullanıcı olamaz.")
            if st.button("Seçilenlerden toplu vaka oluştur ve ata",type="primary",disabled=not selected_visible_ids,width="stretch",key=f"bulk_create_apply_{active_process}"):
                try:
                    case_ids=selected_visible_ids if active_process=="Para Transferleri" else [f"{active_process}:{x}" for x in selected_visible_ids];count=bulk_create_cases(case_ids,bulk_analyst,bulk_reviewer,bulk_team,bulk_priority,str(bulk_due),user["username"]);st.success(f"{count} vaka oluşturuldu ve iş akışına atandı.");st.rerun()
                except Exception as e:st.error(str(e))
            st.divider();st.markdown("#### Mevcut vakaları toplu güncelle")
            selected_rows=st.multiselect("Güncellenecek kayıtlar",filtered[active_id].astype(str).tolist(),key=f"bulk_ids_{active_process}");bc1,bc2=st.columns(2);bulk_status=bc1.selectbox("Yeni vaka durumu",CASE_STATUSES,format_func=tr_text,key=f"bulk_status_{active_process}");update_analyst=bc2.selectbox("İnceleyen kullanıcı",active_users,index=active_users.index(bulk_analyst),key=f"bulk_update_analyst_{active_process}")
            if st.button("Seçilen vakaları güncelle",disabled=not selected_rows,width="stretch",key=f"bulk_apply_{active_process}"):
                case_ids=selected_rows if active_process=="Para Transferleri" else [f"{active_process}:{x}" for x in selected_rows];count=bulk_update_cases(case_ids,bulk_status,update_analyst,user["username"]);st.success(f"{count} vaka güncellendi.");st.rerun()
if page=="Vaka detayı":
    if st.session_state.get(origin_key) == "Senaryo stüdyosu":
        for key in st.session_state.get("studio_return_fields", []):
            if key in st.session_state:
                st.session_state[key] = st.session_state[key]
    origin = st.session_state.get(origin_key, "İşlem listesi")
    st.button(f"← {origin} ekranına dön", on_click=return_to_origin, args=(origin,))
    pending = st.session_state.pop(f"pending_case_{active_process}", None)
    if pending and pending in set(active_df[active_id].astype(str)):
        st.session_state[f"case_{active_process}"] = pending
    if message := st.session_state.pop("review_confirmation", None):
        st.success(message)
    candidates=active_df.sort_values("risk_score",ascending=False);sid=st.selectbox("İncelenecek kayıt",candidates[active_id].astype(str),key=f"case_{active_process}");row=active_df[active_df[active_id].astype(str)==sid].iloc[0];case_id=sid if active_process=="Para Transferleri" else f"{active_process}:{sid}";saved=get_case(case_id)
    risk_level=RISK_LABELS.get(row.risk_level,row.risk_level);risk_class={"YUKSEK":"risk-high","ORTA":"risk-medium","DUSUK":"risk-low"}.get(row.risk_level,"risk-medium");customer=str(row.get("customer_id","—"));case_status=tr_text(saved["status"])
    st.markdown(f'<div class="case-hero"><div><div class="case-kicker">Vaka dosyası · {escape(case_status)}</div><h2>{escape(sid)}</h2><p>{escape(tr_text(active_process))} · Müşteri/Kayıt sahibi: {escape(customer)}</p></div><div class="risk-pill {risk_class}">{escape(risk_level)}<small>{int(row.risk_score)}/100 risk skoru</small></div></div>',unsafe_allow_html=True)
    amount_columns=[c for c in ["transaction_amount","loan_amount","amount","journal_amount","invoice_amount","payment_amount","deal_amount","exposure_amount"] if c in active_df.columns];amount_value=f"{float(row[amount_columns[0]]):,.2f} TL" if amount_columns and pd.notna(row[amount_columns[0]]) else "—";date_value=pd.to_datetime(row[active_date]).strftime("%d.%m.%Y %H:%M") if pd.notna(row.get(active_date)) else "—"
    facts=st.columns(4);fact_values=[("Süreç",tr_text(active_process)),("Kayıt tarihi",date_value),("İlgili tutar",amount_value),("Vaka durumu",case_status)]
    for col,(label,value) in zip(facts,fact_values):col.markdown(f'<div class="case-fact"><span>{escape(label)}</span><b>{escape(str(value))}</b></div>',unsafe_allow_html=True)
    with st.expander("Müşterinin işlem zaman çizelgesi"):
        customer_ids = base_scores.get("customer_id")
        customer_id = customer_ids.loc[row.name] if customer_ids is not None else None
        if pd.isna(customer_id) or not str(customer_id).strip():
            st.info("Bu kayıtta müşteri numarası bulunmuyor.")
        else:
            related = active_df.loc[customer_ids.eq(customer_id)].sort_values([active_date, active_id])
            st.caption(f"{tr_text(active_process)} · Seçili veri setinde aynı müşteriye ait {len(related)} kayıt.")
            if len(related) == 1:
                st.info("Bu süreçte müşteriye ait tek kayıt seçili vaka.")
            else:
                fields = [active_date, active_id, *amount_columns[:1], "risk_score", "risk_level", "case_status"]
                events = related[fields].copy()
                events["risk_level"] = events.risk_level.map(RISK_LABELS)
                events["case_status"] = events.case_status.map(tr_text)
                events.insert(0, "Vaka", related[active_id].astype(str).map(lambda value: "Seçili" if value == sid else ""))
                st.dataframe(rename_for_display(events), hide_index=True, width="stretch")
                record_ids = related[active_id].astype(str).tolist()
                pos = record_ids.index(sid)
                previous, following = st.columns(2)
                if previous.button("Önceki müşteri kaydı", disabled=pos == 0, key=f"timeline_prev_{active_process}_{sid}"):
                    st.session_state[f"pending_case_{active_process}"] = record_ids[pos - 1]
                    st.rerun()
                if following.button("Sonraki müşteri kaydı", disabled=pos == len(record_ids) - 1, key=f"timeline_next_{active_process}_{sid}"):
                    st.session_state[f"pending_case_{active_process}"] = record_ids[pos + 1]
                    st.rerun()
    st.progress(int(row.risk_score)/100,text=f"Risk yoğunluğu: %{int(row.risk_score)}")
    reasons=[tr_text(x) for x in str(row.risk_reasons).split(" | ") if x.strip()];actions=[tr_text(x) for x in str(row.recommended_actions).split(" | ") if x.strip()]
    def observed_number(field):
        return pd.to_numeric(row.get(field), errors="coerce")

    def observed_value(reason):
        reason = reason.partition(": ")[2] if reason.startswith("+") else reason
        fields = []
        if active_process == "Para Transferleri":
            if reason.startswith(("Hesap en az", "Hareketsizlik ile")):
                fields.append(("Hareketsiz süre", observed_number("inactivity_days"), "gün"))
            if reason.startswith(("Musteri ", "Hareketsizlik ile")):
                fields.append(("Yaş", observed_number("age"), "yıl"))
            if reason.startswith("Tutar tarihsel"):
                average = observed_number("historical_avg_amount")
                if average > 0:
                    fields.append(("Geçmiş ortalamanın katı", observed_number("transaction_amount") / average, "kat"))
                    fields.append(("Geçmiş ortalama", average, "TL"))
            if reason.startswith(("Islem tutari ", "Yeni aliciya ilk transfer")):
                fields.append(("İşlem tutarı", observed_number("transaction_amount"), "TL"))
            if reason.startswith("Ayni gun toplam"):
                fields.extend([("Günlük toplam", observed_number("daily_transfer_total"), "TL"),
                               ("İşlem sayısı", observed_number("daily_transaction_count"), "adet")])
        elif active_process == "Krediler":
            if reason.startswith("Teminat orani") and observed_number("collateral_value") > 0:
                fields.append(("Kredi / teminat", 100 * observed_number("loan_amount") / observed_number("collateral_value"), "%"))
            if reason.startswith("Borc/gelir"):
                fields.append(("Borç / gelir", 100 * observed_number("debt_ratio"), "%"))
            if reason.startswith("Dusuk kredi skoru"):
                fields.extend([("Kredi skoru", observed_number("credit_score"), "puan"),
                               ("Kredi tutarı", observed_number("loan_amount"), "TL")])
            if reason.startswith("Ilk 90"):
                fields.append(("Temerrüde kadar geçen süre", observed_number("rapid_default_days"), "gün"))
        parts = []
        for label, value, unit in fields:
            if pd.notna(value):
                formatted = f"{value:,.2f}".rstrip("0").rstrip(".").translate(str.maketrans(".,", ",."))
                parts.append(f"{label}: {formatted} {unit}")
        return " · ".join(parts)

    raw_reasons = [value.strip() for value in str(row.risk_reasons).split(" | ") if value.strip()]
    st.markdown('<div class="section-label">Tespitler ve önerilen kontroller</div>',unsafe_allow_html=True)
    h1,h2=st.columns(2);h1.markdown("#### Risk gerekçeleri");h2.markdown("#### Kontrol aksiyonları")
    for idx in range(max(len(reasons),len(actions))):
        left,right=st.columns(2);reason=reasons[idx] if idx<len(reasons) else "Ek risk gerekçesi bulunmuyor";control=actions[idx] if idx<len(actions) else "Yetkili inceleyen tarafından kontrol aksiyonu belirlenmeli"
        left.markdown(f'<div class="finding-card"><span class="card-no">{idx+1}</span>{escape(reason)}</div>',unsafe_allow_html=True);right.markdown(f'<div class="action-card"><span class="card-no">{idx+1}</span>{escape(control)}</div>',unsafe_allow_html=True)
        if idx < len(raw_reasons) and (detail := observed_value(raw_reasons[idx])):
            left.caption(detail)
    with st.expander("🔎 Kayıt verilerini göster",expanded=False):
        excluded={"risk_reasons_json","recommended_actions_json","risk_reasons","recommended_actions","risk_score","risk_level","case_status"};detail_rows=[]
        for field in active_df.columns:
            if field in excluded:continue
            value=row[field]
            if isinstance(value,(bool,)):value="Evet" if value else "Hayır"
            elif pd.isna(value):value="—"
            elif isinstance(value,(pd.Timestamp,datetime)):value=pd.to_datetime(value).strftime("%d.%m.%Y %H:%M")
            detail_rows.append({"Alan":field_label(field),"Değer":tr_text(value)})
        st.dataframe(pd.DataFrame(detail_rows),hide_index=True,width="stretch")
    st.markdown('<div class="section-label">İnceleme ve karar</div>',unsafe_allow_html=True)
    with st.container(border=True):
        with st.form(f"case_form_{active_process}_{sid}"):
            l,r=st.columns(2);status=l.selectbox("Vaka durumu",CASE_STATUSES,index=CASE_STATUSES.index(saved["status"]),disabled=not editable,format_func=tr_text);analyst=r.text_input("İnceleyen",saved["analyst"] or user["username"],disabled=not editable);unit=l.text_input("Sorumlu birim",saved["responsible_unit"],disabled=not editable);action=r.text_input("Alınan aksiyon",saved["action_taken"],disabled=not editable);note=st.text_area("İnceleme notu",saved["review_note"],disabled=not editable,height=110);evidence=st.text_area("Kanıt ve dayanak açıklaması",saved["evidence_note"],disabled=not editable,height=90)
            available_ids = candidates[active_id].astype(str).tolist()
            available = set(available_ids)
            order = st.session_state.get(f"review_sequence_{active_process}", available_ids)
            next_id = None
            if sid in order:
                current_index = order.index(sid)
                next_id = next((value for value in order[current_index + 1:] if value in available), None)
            save = st.form_submit_button("Vaka değişikliklerini kaydet", type="primary", width="stretch", disabled=not editable)
            advance = st.form_submit_button("Kaydet ve sonraki vakaya geç", width="stretch", disabled=not editable or next_id is None)
            if save or advance:
                save_case(case_id,status,analyst,unit,note,action,evidence,user["username"])
                st.session_state["review_confirmation"] = f"{sid} için inceleme kaydedildi."
                if advance and next_id:
                    st.session_state[f"pending_case_{active_process}"] = next_id
                    if origin == "İşlem listesi" and f"review_sequence_{active_process}" in st.session_state:
                        st.session_state[position_key] = order.index(next_id) // 50 + 1
                st.rerun()
    st.markdown('<div class="section-label">İş akışı ve görev yönetimi</div>',unsafe_allow_html=True)
    with st.container(border=True):
        current_workflow=get_case(case_id);user_names=list_users().query("active == 1").username.astype(str).tolist();default_due=pd.Timestamp(current_workflow.get("due_date") or pd.Timestamp.now()+pd.Timedelta(hours=rules["high_sla_hours"] if row.risk_level=="YUKSEK" else rules["medium_sla_hours"])).date()
        with st.form(f"workflow_form_{case_id}"):
            wf1,wf2=st.columns(2);priority=wf1.selectbox("Öncelik",["Düşük","Orta","Yüksek","Kritik"],index=["Düşük","Orta","Yüksek","Kritik"].index(current_workflow.get("priority") or "Orta"));due_date=wf2.date_input("Son tamamlanma tarihi",value=default_due);team=wf1.text_input("Atanan ekip",value=current_workflow.get("assigned_team","") or current_workflow.get("responsible_unit","") or "");reviewer_options=[""]+user_names;reviewer_value=current_workflow.get("reviewer","");reviewer=wf2.selectbox("Onaylayan kullanıcı",reviewer_options,index=reviewer_options.index(reviewer_value) if reviewer_value in reviewer_options else 0,format_func=lambda x:x or "Seçilmedi")
            if st.form_submit_button("İş akışını kaydet",type="primary",width="stretch",disabled=not editable):save_case_workflow(case_id,priority,str(due_date),reviewer,team,user["username"]);st.rerun()
        wf_saved=get_case(case_id);wf_metrics=st.columns(4);wf_metrics[0].metric("Vaka numarası",wf_saved.get("case_number") or "Kaydedilince oluşur");wf_metrics[1].metric("Öncelik",wf_saved.get("priority","Orta"));wf_metrics[2].metric("Atanan ekip",wf_saved.get("assigned_team") or "Atanmamış");wf_metrics[3].metric("Onaylayan",wf_saved.get("reviewer") or "Atanmamış")
        checklist_labels=["Müşteri/kayıt sahibi bilgileri doğrulandı","İşlem ve dayanak belgeleri incelendi","Risk gerekçeleri tek tek değerlendirildi","Kontrol aksiyonları tamamlandı","İnceleme sonucu ve kanıtlar kaydedildi"]
        checklist=get_checklist(case_id,checklist_labels);states={}
        with st.form(f"checklist_form_{case_id}"):
            st.markdown("#### Kontrol listesi")
            for _,item in checklist.iterrows():states[item.item_key]=st.checkbox(item.label,value=bool(item.completed),key=f"check_{case_id}_{item.item_key}",disabled=not editable)
            if st.form_submit_button("Kontrol listesini kaydet",width="stretch",disabled=not editable):update_checklist(case_id,states,user["username"]);st.rerun()
        complete=int(checklist.completed.sum());st.progress(complete/max(len(checklist),1),text=f"Kontrol listesi: {complete}/{len(checklist)} tamamlandı")
        ab1,ab2,ab3=st.columns(3)
        if ab1.button("Onaya gönder",width="stretch",disabled=not editable or wf_saved.get("status")=="Onay bekliyor",key=f"submit_{case_id}"):
            try:submit_for_approval(case_id,user["username"]);st.rerun()
            except Exception as e:st.error(str(e))
        approval_note=st.text_input("Onay / iade açıklaması",key=f"approval_note_{case_id}",label_visibility="collapsed",placeholder="Onay veya iade açıklaması")
        can_approve=wf_saved.get("status")=="Onay bekliyor" and (not wf_saved.get("reviewer") or wf_saved.get("reviewer")==user["username"])
        if ab2.button("Onayla",type="primary",width="stretch",disabled=not can_approve,key=f"approve_{case_id}"):
            try:approval_decision(case_id,True,approval_note,user["username"]);st.rerun()
            except Exception as e:st.error(str(e))
        if ab3.button("İade et",width="stretch",disabled=not can_approve,key=f"return_{case_id}"):
            try:approval_decision(case_id,False,approval_note,user["username"]);st.rerun()
            except Exception as e:st.error(str(e))
        with st.expander("İlişkili vakaları birleştir",expanded=False):
            merge_options=[x for x in active_case_ids.tolist() if str(x)!=str(case_id)];children=st.multiselect("Ana vakaya bağlanacak vakalar",merge_options,key=f"merge_{case_id}")
            if st.button("Seçilen vakaları bu ana vakaya bağla",disabled=not children,width="stretch",key=f"merge_button_{case_id}"):count=merge_cases(case_id,children,user["username"]);st.success(f"{count} vaka bağlandı.");st.rerun()
    comments=list_case_comments(case_id);evidence_files=list_case_evidence(case_id)
    ca,ev=st.columns(2)
    with ca:
        st.markdown("#### Yorum geçmişi")
        if editable:
            with st.form(f"comment_form_{case_id}"):
                new_comment=st.text_area("Yeni yorum",height=80)
                if st.form_submit_button("Yorumu ekle",width="stretch"):
                    try:add_case_comment(case_id,new_comment,user["username"]);st.rerun()
                    except Exception as e:st.error(str(e))
        if comments.empty:st.caption("Henüz yorum eklenmedi.")
        else:
            for _,comment in comments.iterrows():st.markdown(f"**{escape(str(comment.created_by))}** · {escape(str(comment.created_at))}<br>{escape(str(comment.comment))}",unsafe_allow_html=True);st.divider()
    with ev:
        st.markdown("#### Kanıt ve belgeler")
        if editable:
            evidence_upload=st.file_uploader("Kanıt dosyası yükle",type=["pdf","xlsx","csv","png","jpg","jpeg","docx"],key=f"evidence_{case_id}")
            if st.button("Kanıtı vaka dosyasına ekle",disabled=evidence_upload is None,width="stretch",key=f"evidence_add_{case_id}"):
                try:add_case_evidence(case_id,evidence_upload.name,evidence_upload.type,evidence_upload.getvalue(),user["username"]);st.rerun()
                except Exception as e:st.error(str(e))
        if evidence_files.empty:st.caption("Henüz kanıt dosyası yüklenmedi.")
        else:
            for _,item in evidence_files.iterrows():
                file_record=get_case_evidence(int(item.id));st.download_button(f"📎 {item.file_name} · {int(item.file_size)/1024:.1f} KB",file_record[2],file_name=file_record[0],mime=file_record[1],key=f"evidence_download_{item.id}",width="stretch")
    report_saved=get_case(case_id);pdf_bytes=case_pdf(case_id,tr_text(active_process),row,report_saved,comments,organization["organization_name"])
    st.download_button("📄 Profesyonel PDF vaka raporunu indir",pdf_bytes,file_name=f"{case_id.replace('/','-').replace(':','-')}_vaka_raporu.pdf",mime="application/pdf",type="primary",width="stretch",key=f"case_pdf_{case_id}")
    with st.expander("🕒 İş akışı zaman çizelgesi",expanded=False):
        timeline=list_workflow_log(case_id)
        if timeline.empty:st.caption("Henüz iş akışı hareketi bulunmuyor.")
        else:st.dataframe(timeline.rename(columns={"created_at":"Tarih","actor":"Kullanıcı","action":"İşlem","detail":"Açıklama"}),hide_index=True,width="stretch")
if page=="Yönetici raporu":
    st.subheader("Kontrol örneklemi")
    st.caption("Yüksek riskli kayıtlar puana göre, orta ve düşük riskli kayıtlar rastgele seçilir. Aynı veri, filtre ve seçim numarası aynı örneklemi üretir.")
    dates = pd.to_datetime(active_df[active_date],errors="coerce").dt.date
    if dates.notna().any():
        branch_options = sorted(active_df["branch_id"].dropna().astype(str).unique()) if "branch_id" in active_df else []
        branch = st.selectbox("Örneklem şubesi",[None,*branch_options],format_func=lambda value:value or "Tüm şubeler",key=f"sample_branch_{active_process}")
        period = st.date_input("Örneklem dönemi",(dates.dropna().min(),dates.dropna().max()),key=f"sample_dates_{active_process}")
        if len(period) == 2:
            pool = active_df.loc[dates.between(*period)]
            if branch is not None:
                pool = pool.loc[pool.branch_id.astype(str).eq(branch)]
            levels = ["YUKSEK","ORTA","DUSUK"]
            controls = st.columns(4)
            quotas = {level:int(col.number_input(label,min_value=0,max_value=1000,value=10)) for col,level,label in zip(controls,levels,["Yüksek risk adedi","Orta risk adedi","Düşük risk adedi"])}
            seed = int(controls[3].number_input("Seçim numarası",min_value=0,max_value=999999,value=42))
            sample = draw_sample(pool,active_id,quotas,seed)
            st.caption(f"Filtreye uyan {len(pool)} kayıttan {len(sample)} kayıt seçildi. Bir risk grubunda yeterli kayıt yoksa o grubun tamamı alınır.")
            if not sample.empty:
                fields = [x for x in [active_id,active_date,"branch_id","risk_level","risk_score","case_status"] if x in sample]
                display = rename_for_display(sample[fields])
                case_table(sample,display,"sample_rows","Yönetici raporu",300)
                st.download_button("Örneklemi CSV olarak indir",display.to_csv(index=False).encode("utf-8-sig"),"kontrol_orneklemi.csv","text/csv")
    else:
        st.info("Örneklem için geçerli tarih içeren kayıt gereklidir.")
    process_cases=cases[~cases.transaction_id.astype(str).str.contains(":",regex=False)].copy() if active_process=="Para Transferleri" else cases[cases.transaction_id.astype(str).str.startswith(active_process+":")].copy();confirmed=int((process_cases.status=="Risk dogrulandi").sum()) if len(process_cases) else 0;false=int((process_cases.status=="Yanlis alarm").sum()) if len(process_cases) else 0
    for col,(label,value) in zip(st.columns(4),[("İşleme alınan",len(process_cases)),("Risk doğrulandı",confirmed),("Yanlış alarm",false),("Kararlarda yanlış alarm",f"%{false/(confirmed+false)*100:.1f}" if confirmed+false else "Karar yok")]):col.metric(label,value)
    if len(process_cases):st.subheader("İnceleyen bazında iş yükü");st.bar_chart(process_cases.analyst.replace("","Atanmamış").value_counts(),horizontal=True)
    age_hours=(pd.Timestamp.now()-pd.to_datetime(active_df[active_date])).dt.total_seconds()/3600;sla=active_df.risk_level.map({"YUKSEK":rules["high_sla_hours"],"ORTA":rules["medium_sla_hours"]}).fillna(999999);st.metric("SLA aşımı",int(((age_hours>sla)&~active_df.case_status.isin(["Kapatildi","Yanlis alarm"])).sum()))
    st.download_button("Yönetici Excel raporu",partial(styled_result_excel,active_df,active_process),"yonetici_risk_raporu.xlsx",width="stretch")
if page=="Adaptif kontrol":
    st.subheader("🧠 Adaptif Kontrol ve Veri Asistanı")
    st.caption(f"Aktif süreç: {tr_text(active_process)} · Sistem yalnızca yüklenen veride gerçekten bulunan alanları kullanır.")
    if ai_api_available():st.success(f"ChatGPT bağlantısı aktif · Model: {ai_model_name()} · Yanıtlar sunucu tarafındaki OpenAI Responses API üzerinden alınır.")
    else:st.warning("ChatGPT bağlantısı henüz etkin değil. Basit doğal dil kontrolleri yerel olarak çalışır; anlık sohbet için sunucuda OPENAI_API_KEY tanımlanmalıdır.")
    ai_left,ai_right=st.columns([1.35,1])
    with ai_left:
        st.markdown("### Kontrol etmek istediğiniz hususu yazın")
        examples={"Krediler":"Kredi tutarı 1.000.000 TL üzeri ve kredi risk skoru 500 altı olan müşterileri kontrol et.","Muhasebe Kayitlari":"Muhasebe kayıt tutarı 2.000.000 TL üzeri, manuel ve mesai dışı kayıtları kontrol et.","Musteri Edinimi / KYC":"PEP müşteri olup eksik belgesi bulunan kayıtları kontrol et.","BT / Siber Guvenlik":"Ayrıcalıklı hesaplarda onaysız değişiklik ve mesai dışı hareketleri kontrol et."};adaptive_request=st.text_area("Doğal dilde kontrol talebi",placeholder=examples.get(active_process,"Yüklediğim veride olağandışı gördüğünüz kayıtları belirtilen alanlara göre kontrol et."),height=120,key=f"adaptive_request_{active_process}")
        if st.button("Kontrolü oluştur",type="primary",width="stretch",key=f"build_adaptive_{active_process}"):
            try:
                with st.spinner("Talep veri alanlarıyla eşleştiriliyor..."):generated_rule=rule_from_text(adaptive_request,active_df,active_process)
                st.session_state[f"adaptive_rule_{active_process}"]=generated_rule;log_event(user["username"],"ADAPTIF_KURAL_OLUSTUR","adaptive_control",active_process,hashlib.sha256(adaptive_request.encode("utf-8")).hexdigest()[:16]);st.rerun()
            except Exception as e:st.warning(f"Talep otomatik çözümlenemedi: {e}");st.info("Aşağıdaki 'Alanları kendim seçeyim' bölümünden kontrolü API bağlantısı olmadan oluşturabilirsiniz.")
        with st.expander("🛠️ Alanları kendim seçeyim",expanded=not ai_api_available()):
            available_fields=active_df.columns.tolist();operator_options=[">",">=","<","<=","==","!=","contains","empty","not_empty"]
            with st.form(f"manual_adaptive_form_{active_process}"):
                manual_name=st.text_input("Kontrol adı",value=f"{tr_text(active_process)} özel kontrolü");manual_logic=st.radio("Koşullar arası ilişki",["VE","VEYA"],horizontal=True)
                manual_conditions=[]
                for condition_index in range(3):
                    mc1,mc2,mc3=st.columns([2,1,1.2]);manual_field=mc1.selectbox(f"{condition_index+1}. alan",[""]+available_fields,format_func=lambda x:"Koşul ekleme" if not x else field_label(x),key=f"manual_field_{active_process}_{condition_index}");manual_operator=mc2.selectbox("Karşılaştırma",operator_options,key=f"manual_operator_{active_process}_{condition_index}",label_visibility="collapsed");manual_value=mc3.text_input("Değer",key=f"manual_value_{active_process}_{condition_index}",placeholder="Örn. 1000000",label_visibility="collapsed")
                    if manual_field:manual_conditions.append({"field":manual_field,"operator":manual_operator,"value":manual_value})
                manual_points=st.slider("Risk puanı",1,50,20);manual_reason=st.text_input("Risk gerekçesi",value="Kullanıcı tarafından tanımlanan adaptif kontrol göstergesi");manual_action=st.text_input("Önerilen kontrol",value="Eşleşen kayıtları ve dayanak belgeleri incele")
                if st.form_submit_button("Seçtiğim alanlarla kontrolü oluştur",type="primary",width="stretch"):
                    if not manual_conditions:st.error("En az bir alan seçin.")
                    else:st.session_state[f"adaptive_rule_{active_process}"]={"name":manual_name,"description":adaptive_request or "Alan seçimiyle oluşturuldu","logic":manual_logic,"conditions":manual_conditions,"points":manual_points,"reason":manual_reason,"action":manual_action};st.rerun()
    with ai_right:
        st.markdown("### Kullanılabilir veri alanları")
        schema_table=pd.DataFrame(adaptive_dataset_schema(active_df));schema_table=schema_table.rename(columns={"field":"Teknik alan","label":"Türkçe alan","dtype":"Veri tipi","examples":"Örnek değerler","missing":"Boş değer"});st.dataframe(schema_table[["Türkçe alan","Veri tipi","Örnek değerler","Boş değer"]],hide_index=True,width="stretch",height=285)
    adaptive_rule=st.session_state.get(f"adaptive_rule_{active_process}")
    if adaptive_rule:
        st.markdown("### Oluşturulan kontrol")
        rule_info=st.columns(3);rule_info[0].metric("Kontrol",adaptive_rule["name"]);rule_info[1].metric("Mantık",adaptive_rule["logic"]);rule_info[2].metric("Risk puanı",f"+{adaptive_rule['points']}")
        condition_display=pd.DataFrame(adaptive_rule["conditions"]);condition_display["field"]=condition_display["field"].map(field_label);condition_display=condition_display.rename(columns={"field":"Alan","operator":"Koşul","value":"Değer"});st.dataframe(condition_display,hide_index=True,width="stretch")
        try:
            adaptive_mask=run_rule(active_df,adaptive_rule);matched=active_df.loc[adaptive_mask].copy();am=st.columns(3);am[0].metric("Taranan kayıt",len(active_df));am[1].metric("Eşleşen kayıt",len(matched));am[2].metric("Eşleşme oranı",f"%{(len(matched)/max(len(active_df),1)*100):.1f}")
            st.dataframe(rename_for_display(matched.head(200)),hide_index=True,width="stretch",height=330)
            st.download_button("Eşleşen kayıtları Excel olarak indir",partial(styled_result_excel,matched,active_process),f"adaptif_kontrol_{active_process.replace('/','-')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
            if editable:
                save_col,publish_col=st.columns(2)
                if save_col.button("Taslak senaryo olarak kaydet",width="stretch",key=f"save_adaptive_{active_process}"):
                    version=save_dynamic_scenario("",active_process,adaptive_rule["name"],adaptive_rule["description"],adaptive_rule["logic"],adaptive_rule["conditions"],adaptive_rule["points"],adaptive_rule["reason"],adaptive_rule["action"],user["username"],False);st.success(f"Senaryo v{version} taslak olarak kaydedildi.")
                st.caption("Taslak sürümler Senaryo stüdyosundan ikinci hesap onayına gönderilir.")
        except Exception as e:st.error(f"Kontrol çalıştırılamadı: {e}")
    st.divider();st.markdown("### 💬 Veriye anlık soru sor")
    st.caption("ChatGPT'ye ham dosyanın tamamı yerine maskelenmiş ve özetlenmiş veri bağlamı gönderilir. Yanıt karar değil, inceleme desteğidir.")
    chat_key=f"adaptive_chat_{tenant_id}_{active_process}";messages=st.session_state.setdefault(chat_key,[])
    for message in messages[-10:]:
        with st.chat_message(message["role"]):st.markdown(message["content"])
    if question:=st.chat_input(f"{tr_text(active_process)} verisi hakkında sorun",key=f"adaptive_chat_input_{active_process}"):
        messages.append({"role":"user","content":question})
        with st.chat_message("user"):st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Veri özeti inceleniyor..."):answer=ask_dataset(question,active_df,active_process)
            st.markdown(answer)
        messages.append({"role":"assistant","content":answer});log_event(user["username"],"AI_VERI_SORUSU","ai_assistant",active_process,hashlib.sha256(question.encode("utf-8")).hexdigest()[:16])
if page=="Vaka asistanı":
    assistant_candidates=active_df.sort_values("risk_score",ascending=False);aid=st.selectbox("Özetlenecek kayıt",assistant_candidates[active_id].astype(str),key=f"assistant_{active_process}");x=active_df[active_df[active_id].astype(str)==aid].iloc[0];assistant_case_id=aid if active_process=="Para Transferleri" else f"{active_process}:{aid}";s=get_case(assistant_case_id)
    amount_columns=[c for c in ["transaction_amount","loan_amount","amount","journal_amount","invoice_amount","payment_amount","deal_amount","exposure_amount"] if c in active_df.columns];amount_text=f" İlgili tutar {float(x[amount_columns[0]]):,.2f} TL'dir." if amount_columns and pd.notna(x[amount_columns[0]]) else ""
    draft=tr_text(f"{aid} numaralı {active_process} kaydı {x.risk_score}/100 skorla {x.risk_level} risk seviyesindedir.{amount_text} Risk gerekçeleri: {x.risk_reasons}. Önerilen kontroller: {x.recommended_actions}. Vaka durumu: {s['status']}. Bu taslak yetkili kontrol personeli tarafından doğrulanmalıdır.")
    st.caption(f"Seçili süreç: {tr_text(active_process)} • İlk özet yerel ve denetlenebilir biçimde üretilir.");st.text_area("Vaka özeti",draft,height=220,key=f"assistant_summary_{active_process}_{aid}");st.download_button("Özeti indir",draft.encode("utf-8"),f"{aid}_ozet.txt",key=f"assistant_download_{active_process}_{aid}")
    st.markdown("### ChatGPT ile vakayı incele")
    if ai_api_available():
        case_question=st.chat_input("Bu vaka hakkında sorun: Hangi belgeler incelenmeli? Benzer riskler neler?",key=f"case_ai_question_{active_process}_{aid}")
        if case_question:
            safe_case={k:tr_text(v) for k,v in ai_safe_record(x.to_dict()).items()};answer=ask_dataset(case_question,active_df,active_process,safe_case);log_event(user["username"],"AI_VAKA_SORUSU","case",assistant_case_id,hashlib.sha256(case_question.encode("utf-8")).hexdigest()[:16]);st.markdown(answer)
    else:st.info("ChatGPT vaka sohbeti için sunucuda OPENAI_API_KEY tanımlayın. Yerel vaka özeti API bağlantısı olmadan çalışmaya devam eder.")
if page=="Süreç merkezi":
    st.subheader("Modüler iç kontrol süreçleri")
    process=active_process;process_scored=active_df.copy();process_required=REQUIRED_COLUMNS if process=="Para Transferleri" else PROCESS_DEFINITIONS[process]["fields"];process_optional=list(dict.fromkeys((OPTIONAL_COLUMNS if process=="Para Transferleri" else [])+expanded_optional_fields(process)));process_fields=process_required+process_optional
    st.info(f"Aktif süreç: {tr_text(process)} • Bu ekran Risk Panosu, İşlem Listesi, Vaka Detayı, Vaka Asistanı ve Kural Yönetimi ile eşitlendi.")
    with st.expander("Bu sürecin gerekli sütunları"):
        st.dataframe(pd.DataFrame({"Türkçe sütun adı":turkish_columns(process_fields)}),hide_index=True,width="stretch")
        st.caption("Dosyanızda bu Türkçe sütun adlarını kullanabilirsiniz.")
    st.download_button("Türkçe Excel şablonunu indir",process_template_excel(process,tuple(process_required),tuple(process_optional)),tr_text(process).replace("/","-").replace(" ","_")+"_veri_sablonu.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    tx_types=transaction_types(process);expanded_catalog=scenario_catalog(process)
    with st.expander(f"🧭 İşlem türleri · {len(tx_types)} tür",expanded=False):
        st.write(" • ".join(tx_types));st.caption("İşlem Türü isteğe bağlıdır. Dosyada bulunduğunda türe özgü birleşik risk senaryoları devreye girer.")
    with st.expander(f"🧠 Genişletilmiş birleşik senaryolar · {len(expanded_catalog)} senaryo",expanded=False):st.dataframe(expanded_catalog,hide_index=True,width="stretch")
    pm=st.columns(4);pm[0].metric("Kayıt",len(process_scored));pm[1].metric("Yüksek risk",int((process_scored.risk_level=="YUKSEK").sum()));pm[2].metric("Orta risk",int((process_scored.risk_level=="ORTA").sum()));pm[3].metric("Ortalama skor",f"{process_scored.risk_score.mean():.1f}/100")
    pf1,pf2=st.columns([1,2]);plevels=pf1.multiselect("Risk seviyesi",["YUKSEK","ORTA","DUSUK"],default=["YUKSEK","ORTA"],key="process_levels",format_func=lambda x:RISK_LABELS[x]);pq=pf2.text_input("Kayıt / müşteri ara",key="process_search")
    process_filtered=process_scored[process_scored.risk_level.isin(plevels)].copy()
    if pq:process_filtered=process_filtered[process_filtered[active_id].astype(str).str.contains(pq,case=False)|process_filtered.customer_id.astype(str).str.contains(pq,case=False)]
    process_display=process_filtered.copy();process_display["risk_level"]=process_display["risk_level"].map(RISK_LABELS);process_display["risk_reasons"]=process_display["risk_reasons"].map(tr_text);process_display["recommended_actions"]=process_display["recommended_actions"].map(tr_text);process_display=rename_for_display(localize_values(process_display))
    st.dataframe(process_display,hide_index=True,width="stretch",height=360)
    st.download_button("Süreç sonucunu düzenlenmiş Excel olarak indir",partial(styled_result_excel,process_filtered,process),f"{tr_text(process).replace('/','-').replace(' ','_')}_risk_sonucu.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
    process_candidates=process_scored.sort_values("risk_score",ascending=False);prid=st.selectbox("Vaka detayı",process_candidates[active_id].astype(str),key=f"process_case_{process}");prow=process_scored[process_scored[active_id].astype(str)==prid].iloc[0];process_case_id=prid if process=="Para Transferleri" else f"{process}:{prid}";psaved=get_case(process_case_id)
    dl,dr=st.columns(2)
    with dl:
        st.markdown("#### Risk gerekceleri")
        for item in str(prow.risk_reasons).split(" | "):
            st.warning(tr_text(item))
    with dr:
        st.markdown("#### Kontrol aksiyonlari")
        for item in str(prow.recommended_actions).split(" | "):
            st.success(tr_text(item))
    with st.form("process_case_form"):
        fl,fr=st.columns(2);pstatus=fl.selectbox("Vaka durumu",CASE_STATUSES,index=CASE_STATUSES.index(psaved["status"]),key="pstatus",disabled=not editable,format_func=tr_text);panalyst=fr.text_input("İnceleyen",psaved["analyst"] or user["username"],disabled=not editable);punit=fl.text_input("Sorumlu birim",psaved["responsible_unit"],disabled=not editable);paction=fr.text_input("Alınan aksiyon",psaved["action_taken"],disabled=not editable);pnote=st.text_area("İnceleme notu",psaved["review_note"],disabled=not editable)
        if st.form_submit_button("Surec vakasini kaydet",type="primary",width="stretch",disabled=not editable):save_case(process_case_id,pstatus,panalyst,punit,pnote,paction,"",user["username"]);st.rerun()
if page=="Veri setleri":
    st.subheader("Kalıcı Veri Setleri")
    st.caption(f"Aktif süreç: {tr_text(active_process)} · Veriler kurum çalışma alanında kalıcı ve sürümlü olarak saklanır.")
    if editable:
        with st.expander("➕ Yeni veri seti oluştur",expanded=False):
            with st.form(f"create_dataset_{active_process}"):
                ds1,ds2=st.columns(2);dataset_name=ds1.text_input("Veri seti adı",placeholder="Örn. Ağustos 2026 işlemleri");dataset_period=ds2.text_input("Dönem",placeholder="2026-08")
                if st.form_submit_button("Veri setini oluştur",type="primary",width="stretch"):
                    try:dataset_id=create_dataset(active_process,dataset_name,dataset_period,user["username"]);log_event(user["username"],"VERI_SETI_OLUSTUR","dataset",str(dataset_id),dataset_name);st.success("Veri seti oluşturuldu.");st.rerun()
                    except Exception as e:st.error(str(e))
    datasets=list_datasets(active_process)
    if datasets.empty:st.info("Bu süreç için henüz kalıcı veri seti oluşturulmadı.")
    else:
        ds_table=datasets[["id","name","period","record_count","created_by","created_at"]].copy();ds_table.columns=["No","Veri seti","Dönem","Kayıt","Oluşturan","Oluşturulma tarihi"];st.dataframe(ds_table,hide_index=True,width="stretch")
        selected_dataset=st.selectbox("Çalışılacak veri seti",datasets.id.tolist(),format_func=lambda x:f"{datasets[datasets.id==x].iloc[0]['name']} · {datasets[datasets.id==x].iloc[0]['period']}",key=f"dataset_manager_{active_process}")
        stored=load_dataset(selected_dataset);dm=st.columns(3);dm[0].metric("Kalıcı kayıt",len(stored));dm[1].metric("Sütun",len(stored.columns));dm[2].metric("Aktarım",len(list_imports(selected_dataset)))
        with st.expander("Kayıtları önizle",expanded=False):st.dataframe(rename_for_display(stored.head(100)),hide_index=True,width="stretch")
        if editable:
            st.markdown("#### Dosyadan veri aktar")
            import_file=st.file_uploader("CSV veya Excel dosyası",type=["csv","xlsx"],key=f"dataset_import_{selected_dataset}");strategy_label=st.radio("Aktarım yöntemi",["Yalnızca yeni kayıtları ekle","Var olanları güncelle, yenileri ekle","Veri setini tamamen değiştir"],horizontal=True,key=f"strategy_{selected_dataset}");strategy_map={"Yalnızca yeni kayıtları ekle":"EKLE","Var olanları güncelle, yenileri ekle":"GUNCELLE","Veri setini tamamen değiştir":"DEGISTIR"}
            st.caption("Ekle yönteminde mevcut kayıt numaraları reddedilir. Güncelle yönteminde aynı numaralı kayıtlar yenilenir. Tam değiştirme geri alınabilir bir sürüm oluşturur.")
            if st.button("Kalıcı veri setine aktar",type="primary",disabled=import_file is None,width="stretch",key=f"import_button_{selected_dataset}"):
                try:
                    incoming=read_file(import_file.getvalue(),import_file.name);normalized,issues,summary=quality_report(incoming,list(required_fields),list(optional_fields))
                    if summary["errors"]:st.error(f"Aktarım durduruldu: {summary['errors']} veri hatası bulundu.");st.dataframe(issues,hide_index=True,width="stretch")
                    else:
                        result=import_dataset(selected_dataset,normalized,active_id,strategy_map[strategy_label],import_file.name,user["username"]);log_event(user["username"],"KALICI_VERI_AKTAR","dataset",str(selected_dataset),str(result));st.success(f"Aktarım tamamlandı: {result['inserted']} eklendi, {result['updated']} güncellendi, {result['rejected']} reddedildi.");st.cache_data.clear();st.rerun()
                except Exception as e:st.error(str(e))
        st.markdown("#### Aktarım geçmişi")
        imports=list_imports(selected_dataset)
        if imports.empty:st.caption("Henüz aktarım yapılmadı.")
        else:
            display_imports=imports.rename(columns={"batch_id":"Aktarım kodu","file_name":"Dosya","strategy":"Yöntem","row_count":"Satır","inserted":"Eklenen","updated":"Güncellenen","rejected":"Reddedilen","status":"Durum","created_by":"Kullanıcı","created_at":"Tarih","rolled_back_at":"Geri alma tarihi"});st.dataframe(display_imports.drop(columns=["dataset_id"]),hide_index=True,width="stretch")
            reversible=imports[imports.status=="TAMAMLANDI"]
            if editable and len(reversible):
                rollback_id=st.selectbox("Geri alınacak aktarım",reversible.batch_id.tolist(),format_func=lambda x:f"{x} · {reversible[reversible.batch_id==x].iloc[0].file_name}",key=f"rollback_{selected_dataset}")
                if st.button("Seçili aktarımı geri al",width="stretch",key=f"rollback_button_{selected_dataset}"):
                    try:count=rollback_batch(rollback_id,user["username"]);log_event(user["username"],"VERI_AKTARIM_GERI_AL","import",rollback_id,str(count));st.success(f"Aktarım geri alındı; {count} kayıt sürümü işlendi.");st.cache_data.clear();st.rerun()
                    except Exception as e:st.error(str(e))
if page=="Veri kalitesi":
    st.subheader("Veri Kalitesi Merkezi")
    st.caption("Dosya içeriğini analize alınmadan önce kontrol eder; eksik alan, boş hücre, geçersiz tarih ve mükerrer kayıtları gösterir.")
    if source_pending:st.info("Kalite kontrolü için seçtiğiniz veri kaynağına bir dosya veya kalıcı veri seti bağlayın.")
    elif source=="Sentetik demo":st.info("Şu anda sentetik demo kullanılıyor. Kalite kontrolü için sol menüden ‘Kendi CSV / Excel dosyam’ seçeneğini seçip dosyanızı yükleyin.")
    else:
        qm=st.columns(4);qm[0].metric("Satır",quality_summary["rows"]);qm[1].metric("Sütun",quality_summary["columns"]);qm[2].metric("Hata",quality_summary["errors"]);qm[3].metric("Uyarı",quality_summary["warnings"])
        if quality_issues.empty:st.success("Dosya kalite kontrollerini geçti ve analize alındı.")
        else:st.dataframe(quality_issues,hide_index=True,width="stretch")
        with st.expander("Yüklenen verinin ilk 25 satırını göster",expanded=False):st.dataframe(rename_for_display(raw_input.head(25)) if raw_input is not None else pd.DataFrame(),hide_index=True,width="stretch")
    st.markdown("#### Yükleme geçmişi")
    history=list_upload_history(active_process)
    if history.empty:st.caption("Bu süreç için henüz dosya yüklenmedi.")
    else:
        history=history.rename(columns={"uploaded_at":"Yükleme zamanı","username":"Kullanıcı","process":"Süreç","file_name":"Dosya adı","row_count":"Satır","error_count":"Hata","status":"Durum"});history["Süreç"]=history["Süreç"].map(tr_text)
        st.dataframe(history,hide_index=True,width="stretch")
if page=="Güvenlik merkezi":
    st.subheader("Güvenlik Merkezi")
    st.caption("Hesap güvenliği, oturum politikaları, veri maskeleme ve saklama kontrolleri")
    status_cols=st.columns(4);status_cols[0].metric("MFA", "Etkin" if mfa_status(user["username"]) else "Kapalı");status_cols[1].metric("Boşta oturum",f"{security_cfg['idle_timeout_minutes']} dk");status_cols[2].metric("Mutlak oturum",f"{security_cfg['absolute_timeout_hours']} saat");status_cols[3].metric("Saklama süresi",f"{security_cfg['retention_days']} gün")
    left_security,right_security=st.columns(2)
    with left_security:
        st.markdown("#### İki aşamalı giriş (MFA)")
        if not mfa_status(user["username"]):
            if "mfa_setup_secret" not in st.session_state:st.session_state.mfa_setup_secret=generate_mfa_secret()
            st.info("Telefonunuzdaki Microsoft Authenticator, Google Authenticator veya uyumlu bir uygulamada yeni hesap ekleyin.")
            st.code(st.session_state.mfa_setup_secret,language=None);st.caption("Kurulum anahtarı")
            with st.expander("Gelişmiş: otpauth bağlantısı",expanded=False):st.code(totp_uri(st.session_state.mfa_setup_secret,user["username"],organization["organization_name"]),language=None)
            with st.form("enable_mfa"):
                mfa_code=st.text_input("Uygulamadaki 6 haneli kod",max_chars=6)
                if st.form_submit_button("MFA'yı etkinleştir",type="primary",width="stretch"):
                    try:enable_mfa(user["username"],st.session_state.mfa_setup_secret,mfa_code);st.session_state.pop("mfa_setup_secret",None);st.success("MFA etkinleştirildi.");st.rerun()
                    except Exception as e:st.error(str(e))
        else:
            st.success("Hesabınız iki aşamalı giriş ile korunuyor.")
            with st.form("disable_mfa"):
                disable_code=st.text_input("Devre dışı bırakmak için güncel MFA kodu",max_chars=6)
                if st.form_submit_button("MFA'yı devre dışı bırak",width="stretch"):
                    try:disable_mfa(user["username"],disable_code);st.rerun()
                    except Exception as e:st.error(str(e))
    with right_security:
        st.markdown("#### Parola değiştir")
        with st.form("change_password"):
            current_password=st.text_input("Mevcut parola",type="password");new_password=st.text_input("Yeni parola (en az 12 karakter)",type="password");new_password_again=st.text_input("Yeni parolayı tekrar yazın",type="password")
            if st.form_submit_button("Parolayı değiştir",type="primary",width="stretch"):
                try:
                    if new_password!=new_password_again:raise ValueError("Yeni parolalar eşleşmiyor.")
                    change_password(user["username"],current_password,new_password);st.success("Parola değiştirildi.")
                except Exception as e:st.error(str(e))
        st.info("Görüntüleyen ve Denetçi rollerinde müşteri, alıcı, personel, cihaz ve IP bilgileri otomatik maskelenir.")
    if admin:
        st.divider();st.markdown("#### Kurum güvenlik politikası")
        with st.form("security_policy"):
            sp1,sp2,sp3=st.columns(3);new_security=security_cfg.copy();new_security["idle_timeout_minutes"]=sp1.number_input("Boşta oturum süresi (dk)",5,240,int(security_cfg["idle_timeout_minutes"]));new_security["absolute_timeout_hours"]=sp2.number_input("Mutlak oturum süresi (saat)",1,24,int(security_cfg["absolute_timeout_hours"]));new_security["max_failed_logins"]=sp3.number_input("Kilit öncesi hatalı giriş",3,10,int(security_cfg["max_failed_logins"]));new_security["lockout_minutes"]=sp1.number_input("Hesap kilidi süresi (dk)",5,1440,int(security_cfg["lockout_minutes"]));new_security["retention_days"]=sp2.number_input("Kanıt/yorum saklama süresi (gün)",30,3650,int(security_cfg["retention_days"]));new_security["api_requests_per_minute"]=sp3.number_input("API istek sınırı (dakika)",10,10000,int(security_cfg["api_requests_per_minute"]));
            if st.form_submit_button("Güvenlik politikasını kaydet",type="primary",width="stretch"):save_security_settings(new_security,user["username"]);st.success("Güvenlik politikası güncellendi.");st.rerun()
        retention=retention_preview();st.markdown("#### KVKK saklama politikası uygulaması");rc=st.columns(3);rc[0].metric("Kesim tarihi",retention["cutoff"][:10]);rc[1].metric("Silinecek eski yorum",retention["comments"]);rc[2].metric("Silinecek eski kanıt",retention["evidence"]);confirm_retention=st.checkbox("Saklama süresini aşan belirtilen kayıtların kalıcı silineceğini onaylıyorum")
        if st.button("Saklama politikasını şimdi uygula",disabled=not confirm_retention,width="stretch"):
            deleted=apply_retention(user["username"]);st.success(f"{deleted} eski kayıt güvenli biçimde silindi.");st.rerun()
        st.markdown("#### Güvenlik olayları");security_events=list_security_events();security_events["success"]=security_events.success.map({1:"Başarılı",0:"Başarısız"});st.dataframe(security_events.rename(columns={"event_time":"Tarih","username":"Kullanıcı","event_type":"Olay","success":"Sonuç","detail":"Açıklama"}),hide_index=True,width="stretch",height=330)
if admin:
    if page=="Entegrasyon merkezi":
        st.subheader("Entegrasyon Merkezi")
        st.caption("API, SFTP ve veritabanı kaynaklarını kurum bazında tanımlayın. Parola ve özel anahtarları bu prototip ekranda değil, canlı ortamın gizli anahtar kasasında saklayın.")
        with st.form("integration_source"):
            ic1,ic2=st.columns(2);integration_name=ic1.text_input("Bağlantı adı");integration_type=ic2.selectbox("Kaynak türü",["API","SFTP","PostgreSQL","Microsoft SQL Server","Webhook"]);endpoint=st.text_input("Sunucu / uç nokta",placeholder="https://... veya sunucu adı");schedule=st.selectbox("Çalışma sıklığı",["Elle","Saatlik","Günlük","Haftalık"])
            if st.form_submit_button("Entegrasyon tanımını kaydet",type="primary",width="stretch"):
                try:save_integration(integration_name,integration_type,{"endpoint":endpoint,"schedule":schedule},user["username"]);log_event(user["username"],"ENTEGRASYON_OLUSTUR","integration",integration_name,integration_type);st.success("Entegrasyon tanımı kaydedildi.");st.rerun()
                except Exception as e:st.error(str(e))
        integrations=list_integrations()
        if integrations.empty:st.info("Henüz entegrasyon tanımı yok.")
        else:st.dataframe(integrations.rename(columns={"name":"Bağlantı","source_type":"Tür","active":"Aktif","last_status":"Son durum","last_checked_at":"Son kontrol","created_by":"Oluşturan","created_at":"Tarih"}),hide_index=True,width="stretch")
        st.info("Bu demoda API anahtarlarını yönetebilirsiniz. HTTP API hizmeti masaüstünde BASLAT_API.bat ile ayrıca başlatılır.")
    if page=="API yönetimi":
        st.subheader("API Anahtarı Yönetimi")
        st.warning("Yeni anahtar yalnızca oluşturulduğu anda tam olarak gösterilir. Güvenli bir parola kasasına kaydedin.")
        with st.form("new_api_key"):
            api_name=st.text_input("Anahtar adı",placeholder="Örn. Kurumsal veri aktarımı");api_scopes=st.multiselect("Yetkiler",["veri_oku","veri_yaz","analiz"],default=["veri_oku","veri_yaz","analiz"])
            if st.form_submit_button("Yeni API anahtarı oluştur",type="primary",width="stretch"):
                try:st.session_state.last_api_key=create_api_key(api_name,api_scopes,user["username"]);log_event(user["username"],"API_ANAHTARI_OLUSTUR","api_key",api_name,",".join(api_scopes));st.rerun()
                except Exception as e:st.error(str(e))
        if st.session_state.get("last_api_key"):st.code(st.session_state.last_api_key,language=None);st.caption("Bu değeri şimdi kopyalayın; daha sonra tekrar gösterilmez.")
        keys=list_api_keys()
        if keys.empty:st.info("Henüz API anahtarı yok.")
        else:
            key_display=keys.copy();key_display["active"]=key_display.active.map({1:"Evet",0:"Hayır"});st.dataframe(key_display.rename(columns={"name":"Anahtar","key_prefix":"Ön ek","scopes":"Yetkiler","active":"Aktif","last_used_at":"Son kullanım","created_by":"Oluşturan","created_at":"Tarih"}),hide_index=True,width="stretch")
            active_keys=keys[keys.active==1]
            if len(active_keys):
                revoke_id=st.selectbox("İptal edilecek anahtar",active_keys.id.tolist(),format_func=lambda x:f"{active_keys[active_keys.id==x].iloc[0]['name']} · {active_keys[active_keys.id==x].iloc[0]['key_prefix']}…")
                if st.button("Anahtarı iptal et",width="stretch"):revoke_api_key(revoke_id);log_event(user["username"],"API_ANAHTARI_IPTAL","api_key",str(revoke_id));st.session_state.pop("last_api_key",None);st.rerun()
    if page=="Senaryo stüdyosu":
        studio_mode = st.radio("Çalışma biçimi", ["Metinle tara", "Gelişmiş düzenleyici"],
                               horizontal=True, key="studio_mode")
    if page=="Senaryo stüdyosu" and studio_mode == "Metinle tara":
        st.subheader("Senaryonu yaz")
        scope = f"{tenant_id}_{active_process}"
        text_key = f"scan_text_{scope}"
        example = ("Müşteri yaşı en az 65\nHareketsizlik günü en az 365" if active_process == "Para Transferleri"
                   else "risk_score en az 70")
        if text_key not in st.session_state:
            st.session_state[text_key] = st.session_state.get(f"scan_draft_{scope}", example)
        st.caption("Her satıra bir koşul yaz. Varsayılan olarak tüm koşullar birlikte aranır. Herhangi birinin eşleşmesi için ayrı bir satıra “Bağlantı: VEYA” yaz.")
        query = st.text_area("Senaryo metni", key=text_key, height=150, max_chars=12000)
        st.session_state[f"scan_draft_{scope}"] = query
        scope_signature = (query, source, upload_hash, persistent_dataset_id)
        result_key = f"scan_result_{scope}"
        if source_pending:
            st.info("Taramak için bir dosya veya veri seti seç.")
        if st.button("Verileri tara", type="primary", disabled=source_pending):
            st.session_state[result_key] = scope_signature
        if not source_pending and st.session_state.get(result_key) == scope_signature:
            details, terms, errors = read_scenario_text(query, active_df.columns)
            if not terms and not errors:
                errors.append("Taramak için en az bir koşul yaz.")
            for message in errors:
                st.error(message)
            if not errors:
                mask = scenario_mask(active_df, terms, details.get("logic", "VE"))
                hits = active_df.loc[mask].sort_values("risk_score", ascending=False, kind="stable")
                st.subheader(details.get("name") or "Tarama sonucu")
                st.write(f"{source_label} · {len(active_df):,} kayıt tarandı, {len(hits):,} kayıt eşleşti.".replace(",", "."))
                if len(hits):
                    fields = list(dict.fromkeys([active_id, active_date, *[t["field"] for t in terms], "risk_score"]))
                    display = rename_for_display(hits[fields])
                    st.session_state.studio_return_fields = ["studio_mode", text_key]
                    case_table(hits, display, f"scan_hits_{scope}", "Senaryo stüdyosu", 380)
                    st.download_button("Eşleşen kayıtları indir",display.to_csv(index=False).encode("utf-8-sig"),"senaryo_eslesmeleri.csv","text/csv")
                else:
                    st.info("Bu koşulları karşılayan kayıt bulunamadı.")
        with st.expander("Yazabileceğin alanlar"):
            st.dataframe(pd.DataFrame([{"Alan":field_label(f), "Teknik adı":f} for f in active_df.columns]), hide_index=True)
    if page=="Senaryo stüdyosu" and studio_mode == "Gelişmiş düzenleyici":
        st.subheader("Kod Yazmadan Senaryo Stüdyosu")
        st.caption(f"Aktif süreç: {tr_text(active_process)} · Koşulları oluşturun, mevcut veri üzerinde test edin, taslak kaydedin veya yayımlayın.")
        scenario_rows=list_dynamic_scenarios(active_process);scenario_keys=scenario_rows.scenario_key.drop_duplicates().tolist() if len(scenario_rows) else []
        if message := st.session_state.pop("studio_notice", None):
            st.success(message)
        with st.expander("Senaryo dosyasını kaydet veya geri yükle"):
            st.caption("Bu süreçte oluşturduğunuz senaryoları, sürümlerini ve etkinlik durumlarını kaydeder. İçeri aktarılan yeni sürümler taslak olarak açılır. Demo oturumu geçicidir. Son düzenlemeden sonra güncel dosyayı indirin.")
            package = scenario_package(active_process)
            st.download_button("Güncel senaryo dosyasını indir", json.dumps(package, ensure_ascii=False, indent=2),
                               f"senaryolar_{active_process.replace('/', '-')}_{datetime.now():%Y%m%d}.json", "application/json",
                               disabled=not package["versions"])
            uploaded_package = st.file_uploader("Kayıtlı senaryo dosyası", type=["json"], key=f"studio_import_{active_process}")
            if st.button("Dosyadan geri yükle", disabled=uploaded_package is None):
                try:
                    if uploaded_package.size > 8 * 1024 * 1024:
                        raise ValueError("Senaryo dosyası 8 MB sınırını aşıyor.")
                    added = restore_scenario_package(json.loads(uploaded_package.getvalue()), active_process, user["username"])
                    st.session_state.studio_notice = f"{added} sürüm geri yüklendi." if added else "Bu dosyadaki sürümler zaten mevcut."
                    st.rerun()
                except (ValueError, TypeError, OverflowError, RecursionError) as error:
                    st.error(f"Dosya yüklenemedi. {error}")
        picker_key = f"studio_picker_{active_process}"
        new_key = st.session_state.pop("studio_selection", None)
        latest = scenario_rows.drop_duplicates("scenario_key").set_index("scenario_key")
        if new_key in scenario_keys:
            st.session_state[picker_key] = new_key
            st.session_state[f"studio_version_{new_key}"] = int(latest.loc[new_key,"id"])
        def scenario_label(key):
            if key == "Yeni senaryo":
                return key
            row = latest.loc[key]
            return f"{row['name']} · v{row.version} · {key[:8]}"
        selected_key = st.selectbox("Çalışılacak senaryo", ["Yeni senaryo", *scenario_keys],
                                    key=picker_key, format_func=scenario_label,
                                    help="Listede senaryo adı veya kısa kodunu yazarak arayabilirsiniz.")
        current = None
        if selected_key != "Yeni senaryo":
            versions = scenario_rows[scenario_rows.scenario_key == selected_key].set_index("id", drop=False)
            def version_label(i):
                row = versions.loc[i]
                status = "Etkin" if row.active else "Taslak" if row.status == "TASLAK" else "Geçmiş sürüm"
                return f"v{row.version} · {status} · {row.created_at}"
            version_id = st.selectbox("Sürüm", versions.index.tolist(), key=f"studio_version_{selected_key}", format_func=version_label)
            current = versions.loc[version_id]
        templates = {
            "Para Transferleri": {
                "Hareketsiz hesaptan yüksek tutarlı transfer": (
                    [("inactivity_days", ">=", "365"), ("transaction_amount", ">=", "250000")],
                    "Uzun süredir hareketsiz hesaptan yüksek tutarda transfer yapıldı.",
                    "Transfer talimatını ve müşteri teyidini incele."),
                "Yeni alıcıya yüksek tutarlı transfer": (
                    [("new_recipient", "==", "evet"), ("transaction_amount", ">=", "500000")],
                    "Transfer tutarı yüksek ve alıcı bu müşteri için yeni.",
                    "Alıcı ilişkisini ve transferin dayanağını doğrula.")
            },
            "Krediler": {
                "Yüksek borç yükü ve yüksek kredi tutarı": (
                    [("debt_ratio", ">", "0.60"), ("loan_amount", ">=", "500000")],
                    "Borç/gelir oranı ve kredi tutarı birlikte belirlenen koşulları karşılıyor.",
                    "Gelir belgesini ve geri ödeme kapasitesi analizini incele.")
            }
        }
        defaults = current.to_dict() if current is not None else {}
        existing = json.loads(defaults.get("conditions_json", "[]"))
        template = "Boş senaryo"
        if current is None and active_process in templates:
            options = templates[active_process]
            template = st.selectbox("Başlangıç şablonu", [template, *options], key=f"template_{active_process}",
                                    help="Örnek eşikleri ve puanı kendi kontrol amacınıza göre değiştirebilirsiniz.")
            if template in options:
                terms, reason_text, action_text = options[template]
                defaults.update(name=template, reason=reason_text, action=action_text)
                existing = [dict(field=field, operator=op, value=value) for field, op, value in terms]
        available_fields = list(dict.fromkeys(list(required_fields) + list(optional_fields) + list(base_scores.columns) + [c["field"] for c in existing]))
        editor_key = f"{active_process}_{selected_key}_{defaults.get('id', template)}"
        # Keep stable row identities while adding, copying or removing a condition.
        if st.session_state.get("studio_layout_owner") != editor_key or f"name_{editor_key}" not in st.session_state:
            st.session_state.studio_layout_owner = editor_key
            st.session_state.studio_rows = {uuid4().hex: item for item in (existing or [{}])}
        rows = st.session_state.studio_rows
        row_limit = max(20, len(existing))
        with st.expander("Senaryoyu elle yaz"):
            st.caption("Her koşulu ayrı satıra yaz. Alanın Türkçe adını veya teknik adını kullanabilirsin. Yazdığın koşullar forma aktarıldığında mevcut koşulların yerini alır. Yalnızca başlık girersen koşullar korunur.")
            example_field = "age" if "age" in base_scores else active_id
            example = f"Ad: Yeni kontrol\n{field_label(example_field)} " + ("en az 65" if example_field == "age" else "boş değil") + "\nPuan: 25"
            st.text("Örnek\n" + example)
            st.caption("İsteğe bağlı başlıklar: Ad, Açıklama, Bağlantı (VE veya VEYA), Puan, Gerekçe ve Aksiyon. Karşılaştırmalar: =, !=, >, >=, <, <=, en az, en fazla, içerir, boş, boş değil. Ondalık ayırıcı virgüldür.")
            with st.expander("Bu veride kullanılabilecek alanlar"):
                st.dataframe(pd.DataFrame([{"Alan":field_label(f),"Teknik ad":f} for f in base_scores.columns]),hide_index=True,width="stretch")
            typed = st.text_area("Senaryo metni", max_chars=12000, height=160, key=f"typed_{editor_key}")
            if typed.strip():
                details, parsed, problems = read_scenario_text(typed, base_scores.columns, row_limit)
                for problem in problems:
                    st.error(problem)
                if not problems:
                    if parsed:
                        st.dataframe(pd.DataFrame([{"Alan":field_label(term["field"]), "Karşılaştırma":term["operator"], "Değer":term["value"]} for term in parsed]),hide_index=True,width="stretch")
                    if st.button("Metni forma aktar",key=f"apply_text_{editor_key}"):
                        for prop, val in details.items():
                            st.session_state[f"{prop}_{editor_key}"] = val
                        if parsed:
                            rows = {uuid4().hex: term for term in parsed}
                            st.session_state.studio_rows = rows
                        st.success("Metin forma aktarıldı. Kural özetini inceleyebilir ve senaryoyu test edebilirsin.")
        with st.container(border=True):
            name = st.text_input("Senaryo adı", defaults.get("name", ""), key=f"name_{editor_key}")
            description = st.text_area("Açıklama", defaults.get("description", ""), height=70, key=f"desc_{editor_key}")
            logic = st.radio("Koşulların bağlantısı", ["VE","VEYA"], horizontal=True, index=int(defaults.get("logic") == "VEYA"), key=f"logic_{editor_key}")
            conditions = []
            issues = []
            for idx, (row_key, old) in enumerate(rows.items()):
                suffix = f"{editor_key}_{row_key}"
                enabled = st.checkbox(f"{idx+1}. koşulu kullan", value=True, key=f"cond_enabled_{suffix}")
                cols = st.columns([1.5,1.3,1.2])
                field = cols[0].selectbox(f"{idx+1}. alan", available_fields, format_func=field_label, index=available_fields.index(old.get("field",available_fields[0])), key=f"cond_field_{suffix}")
                operator = cols[1].selectbox(f"{idx+1}. karşılaştırma", list(OPERATORS), index=list(OPERATORS.values()).index(old["operator"]) if old.get("operator") in OPERATORS.values() else 0, key=f"cond_op_{suffix}")
                op = OPERATORS[operator]
                needs_value = op not in ("empty", "not_empty")
                value = cols[2].text_input(f"{idx+1}. değer", str(old.get("value","")), disabled=not needs_value or not enabled, help="Sayısal eşiklerde binlik ayırıcı kullanmayın. Örnek: 250000 veya 0,60." if op in (">",">=","<","<=") else None, key=f"cond_value_{suffix}").strip()
                controls = st.columns(2)
                if controls[0].button("Koşulu çoğalt", key=f"copy_{suffix}", disabled=len(rows) >= row_limit):
                    rows[uuid4().hex] = dict(field=field, operator=op, value=value)
                    st.rerun()
                if controls[1].button("Koşulu kaldır", key=f"remove_{suffix}", disabled=len(rows) == 1):
                    del rows[row_key]
                    st.rerun()
                if not enabled:
                    continue
                if needs_value and not value:
                    issues.append(f"{idx+1}. koşul için bir değer girin.")
                elif op in (">", ">=", "<", "<="):
                    from math import isfinite
                    value = value.replace(",", ".")
                    if not isfinite(pd.to_numeric(value, errors="coerce")):
                        issues.append(f"{idx+1}. koşula binlik ayırıcı kullanmadan sayı girin (ör. 250000 veya 0,60).")
                conditions.append(dict(field=field, operator=op, value=value if needs_value else ""))
            if st.button("＋ Koşul ekle", key=f"add_{editor_key}", disabled=len(rows) >= row_limit):
                rows[uuid4().hex] = {}
                st.rerun()
            points_key = f"points_{editor_key}"
            if points_key not in st.session_state:
                st.session_state[points_key] = int(defaults.get("points",20))
            points = st.number_input("Risk puanı",1,100,key=points_key)
            reason = st.text_input("Risk gerekçesi", defaults.get("reason",""),key=f"reason_{editor_key}")
            action = st.text_area("Önerilen kontrol aksiyonu",defaults.get("action",""),height=80,key=f"action_{editor_key}")
            operator_text = {v:k.lower() for k,v in OPERATORS.items()}
            def describe(terms):
                return [f"{field_label(term['field'])} · {operator_text.get(term['operator'],term['operator'])} {term.get('value','')}".strip() for term in terms]
            st.markdown("#### Kural özeti")
            st.text((" " + logic + " ").join(describe(conditions)) or "Etkin koşul yok")
            st.caption(f"Eşleşen kayda +{points} risk puanı uygulanır.")
            changed = True
            if current is not None:
                baseline = [current["name"],current["description"],current["logic"],str(current["points"]),
                            current["reason"],current["action"],"\n".join(describe(existing))]
                edited = [name.strip(),description.strip(),logic,str(points),reason.strip(),action.strip(),"\n".join(describe(conditions))]
                differences = [{"Alan":label,"Kayıtlı sürüm":before,"Düzenleme":after}
                               for label,before,after in zip(["Ad","Açıklama","Bağlantı","Puan","Risk gerekçesi","Aksiyon","Koşullar"],baseline,edited)
                               if before != after]
                changed = bool(differences)
                if changed:
                    st.caption(f"v{current.version} ile karşılaştırma · Kaydedilmemiş değişiklikler")
                    st.dataframe(pd.DataFrame(differences),hide_index=True,width="stretch")
            threshold_indices = [i for i, term in enumerate(conditions) if term["operator"] in (">", ">=", "<", "<=")]
            compare_index = None
            if threshold_indices and st.checkbox("Alternatif eşikle karşılaştır", key=f"compare_{editor_key}"):
                compare_index = st.selectbox("Karşılaştırılacak koşul", threshold_indices,
                    format_func=lambda i: f"{i+1}. {field_label(conditions[i]['field'])} {conditions[i]['operator']} {conditions[i]['value']}",
                    key=f"compare_field_{editor_key}")
                alternative = st.text_input("Alternatif eşik", key=f"alternative_{editor_key}_{compare_index}").strip().replace(",", ".")
            test_clicked = st.button("Mevcut veride test et")
            draft_clicked = st.button("Taslak olarak kaydet", disabled=not changed)

        if not conditions:
            issues.append("En az bir koşulu etkinleştirin.")
        if draft_clicked and not all(text.strip() for text in (name,reason,action)):
            issues.append("Senaryo adını, risk gerekçesini ve önerilen kontrol aksiyonunu doldurun.")
        if test_clicked and compare_index is not None:
            from math import isfinite
            if not isfinite(pd.to_numeric(alternative, errors="coerce")):
                issues.append("Karşılaştırma için geçerli bir alternatif eşik girin.")
        if issues and (test_clicked or draft_clicked):
            for problem in issues:
                st.error(problem)
            test_clicked = draft_clicked = False
        new_key_slot = f"studio_new_rule_{active_process}"
        if selected_key == "Yeni senaryo" and new_key_slot not in st.session_state:
            st.session_state[new_key_slot] = uuid4().hex
        candidate_key = st.session_state[new_key_slot] if selected_key == "Yeni senaryo" else selected_key
        test_key = f"studio_test_{tenant_id}_{active_process}"
        signature = (candidate_key, editor_key, json.dumps(conditions,sort_keys=True), logic, points,
                     reason, action, compare_index, alternative if compare_index is not None else None)
        if test_clicked:
            st.session_state[test_key] = signature
        if not issues and st.session_state.get(test_key) == signature:
            other_rules = published_scenarios[published_scenarios.scenario_key != candidate_key]
            preceding = other_rules[other_rules.scenario_key < candidate_key]
            before_rule = apply_dynamic_scenarios(base_scores, preceding) if len(preceding) else base_scores
            if len(preceding):
                # The engine assigns risk levels only after evaluating all rules.
                before_rule["risk_level"] = base_scores.risk_level
            matched = scenario_mask(before_rule, conditions, logic)
            candidate = dict(scenario_key=candidate_key, conditions_json=json.dumps(conditions),
                             logic=logic, points=points, reason=reason, action=action)
            preview_rules = pd.concat([other_rules, pd.DataFrame([candidate])], ignore_index=True).sort_values("scenario_key")
            simulated = apply_dynamic_scenarios(base_scores, preview_rules)
            difference = simulated.risk_score - active_df.risk_score
            high_before = active_df.risk_level.eq("YUKSEK")
            high_after = simulated.risk_level.eq("YUKSEK")
            st.subheader("Yayımlama öncesi etki")
            st.caption(f"{tr_text(active_process)} · {len(active_df)} kayıt · Mevcut sonuçlar, bu sürüm yayımlandığında oluşacak sonuçlarla karşılaştırılır.")
            for col, (label, value) in zip(st.columns(4), [
                ("Koşulları karşılayan", matched.sum()), ("Puanı değişen", difference.ne(0).sum()),
                ("Yüksek riske geçen", (~high_before & high_after).sum()),
                ("Yüksek riskten çıkan", (high_before & ~high_after).sum())]):
                col.metric(label, int(value))
            without_candidate = apply_dynamic_scenarios(base_scores, other_rules)
            other_reasons = without_candidate.risk_reasons.fillna("").astype(str).str.strip()
            covered = other_reasons.ne("") & ~other_reasons.str.startswith("Tetiklenen risk kurali yok")
            groups = {"Formdaki eşleşmeler": matched}
            if compare_index is not None:
                trial_conditions = [dict(term) for term in conditions]
                trial_conditions[compare_index]["value"] = alternative
                alternative_mask = scenario_mask(before_rule, trial_conditions, logic)
                term = conditions[compare_index]
                comparison = pd.DataFrame([
                    {"Seçenek": label, "Alan": field_label(term["field"]), "İşleç": term["operator"],
                     "Eşik": threshold, "Eşleşen kayıt": int(mask.sum()),
                     "İlk eşiğe göre eklenen": int((mask & ~matched).sum()),
                     "İlk eşiğe göre çıkan": int((matched & ~mask).sum())}
                    for label, threshold, mask in [("Formdaki eşik", term["value"], matched), ("Alternatif", alternative, alternative_mask)]
                ])
                st.markdown("#### Eşik karşılaştırması")
                st.caption("İki eşik aynı kayıtlar üzerinde denenir. Kaydetme ve yayımlama işlemleri formdaki eşiği kullanır.")
                st.dataframe(comparison, hide_index=True, width="stretch")
                st.download_button("Eşik karşılaştırmasını indir", comparison.to_csv(index=False).encode("utf-8-sig"),
                                   "esik_karsilastirmasi.csv", "text/csv", on_click="ignore")
                groups = {
                    "Kapsamdan çıkan": matched & ~alternative_mask,
                    "Kapsama giren": alternative_mask & ~matched,
                    "Her iki eşikte eşleşen": matched & alternative_mask,
                    **groups,
                }
            st.markdown("#### Kayıtlar ve diğer senaryolar")
            st.caption("Diğer senaryoların kapsamı, test edilen senaryonun bütün sürümleri hariç tutularak hesaplanır.")
            group_key = f"coverage_group_{editor_key}"
            coverage_key = f"coverage_filter_{editor_key}"
            if st.session_state.get(group_key) not in groups:
                st.session_state[group_key] = next(iter(groups))
            group = st.radio("İncelenecek kayıt grubu", list(groups), horizontal=True, key=group_key,
                             format_func=lambda label: f"{label} ({int(groups[label].sum())})")
            mask = groups[group]
            filters = {"Tümü": mask, "Başka senaryoda da var": mask & covered,
                       "Başka senaryo yakalamıyor": mask & ~covered}
            choice = st.radio("Diğer senaryolarla örtüşme", list(filters), horizontal=True, key=coverage_key,
                              format_func=lambda label: f"{label} ({int(filters[label].sum())})")
            review = active_df.loc[filters[choice], [active_id,"risk_score","risk_level"]].copy()
            review["Diğer risk gerekçeleri"] = other_reasons.loc[review.index].where(covered.loc[review.index], "Yok").map(tr_text)
            review = review.sort_values(["risk_score", active_id], ascending=[False,True], kind="stable")
            if review.empty:
                st.info("Bu seçimde incelenecek kayıt yok.")
            else:
                review["risk_level"] = review.risk_level.map(RISK_LABELS)
                display = review.rename(columns={active_id:field_label(active_id), "risk_score":"Mevcut puan","risk_level":"Risk seviyesi"})
                st.caption("Vaka detayını açmak için satırı seçin.")
                prefixes = ("cond_", "studio_picker_", "studio_version_", "template_", "condition_count_",
                            "name_", "desc_", "logic_", "points_", "reason_", "action_", "compare_", "alternative_", "coverage_")
                st.session_state.studio_return_fields = [k for k in st.session_state if k.startswith(prefixes)]
                case_table(review, display, f"studio_review_{active_process}", "Senaryo stüdyosu", 350)
            affected = matched | difference.ne(0) | high_after.ne(high_before)
            if affected.any():
                details = pd.DataFrame({
                    field_label(active_id): active_df[active_id],
                    "Mevcut puan": active_df.risk_score, "Öngörülen puan": simulated.risk_score,
                    "Puan farkı": difference, "Mevcut seviye": active_df.risk_level.map(RISK_LABELS),
                    "Öngörülen seviye": simulated.risk_level.map(RISK_LABELS)})
                ordered = difference[affected].abs().sort_values(ascending=False, kind="stable").index
                st.caption(f"Eşleşen veya sonucu değişen {int(affected.sum())} kayıttan en yüksek puan farkına göre ilk 50 kayıt gösterilir.")
                st.dataframe(details.loc[ordered].head(50), hide_index=True, width="stretch")
            else:
                st.info("Bu veri setinde koşullara uyan veya puanı değişen kayıt bulunamadı.")
        if draft_clicked:
            try:
                key=candidate_key;version=save_dynamic_scenario(key,active_process,name,description,logic,conditions,points,reason,action,user["username"],False);st.session_state.pop(new_key_slot,None);st.session_state.studio_selection=key;st.session_state.studio_notice=f"{name} · v{version} taslak olarak kaydedildi. Güncel dosyayı indirebilirsiniz.";st.rerun()
            except Exception as e:st.error(str(e))
        if current is not None:
            st.subheader("Kaydedilmiş sürüm için onay talebi")
            change = "Durdur" if current["active"] else "Etkinleştir"
            st.caption(f"{current['name']} · v{current['version']} · {change}. Formdaki düzenlemeleri kullanmak için önce yeni bir taslak kaydedin.")
            justification = st.text_input("Değişiklik gerekçesi", key=f"justification_{current['id']}")
            if st.button("Etkiyi test et ve onaya gönder", disabled=changed or not justification.strip() or source_pending):
                others = published_scenarios[published_scenarios.scenario_key != selected_key]
                proposed = others if current["active"] else pd.concat([others,current.to_frame().T],ignore_index=True).sort_values("scenario_key")
                try:
                    result = apply_dynamic_scenarios(base_scores, proposed)
                    evidence = {"Veri kaynağı":source_label, "Taranan kayıt":len(result),
                                "Puanı değişen":int(result.risk_score.ne(active_df.risk_score).sum()),
                                "Önce yüksek risk":int(active_df.risk_level.eq("YUKSEK").sum()),
                                "Sonra yüksek risk":int(result.risk_level.eq("YUKSEK").sum())}
                    request_review(int(current["id"]), change, justification, evidence, user["username"])
                    st.session_state.studio_notice = "Talep gönderildi. İkinci hesap Operasyon merkezinden karar verebilir."
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        st.markdown("#### Sürüm geçmişi")
        if len(scenario_rows):
            version_table=scenario_rows[["name","version","logic","points","status","active","created_by","created_at"]].copy();version_table.columns=["Senaryo","Sürüm","Bağlantı","Puan","Durum","Aktif","Oluşturan","Tarih"];version_table["Aktif"]=version_table["Aktif"].map({1:"Evet",0:"Hayır"});st.dataframe(version_table,hide_index=True,width="stretch")
        else:st.info("Bu süreç için henüz dinamik senaryo oluşturulmadı.")
        st.markdown("#### Senaryo performansı")
        performance=scenario_performance(active_df)
        st.caption("Karar kapsamı, eşleşen kayıtların ne kadarında risk doğrulandı veya yanlış alarm kararı verildiğini gösterir. Yanlış alarm yüzdesi yalnızca bu kararlar üzerinden hesaplanır. Bir vaka birden fazla senaryoda yer alabilir.")
        if len(performance):st.dataframe(performance,hide_index=True,width="stretch")
    if page=="Kural yönetimi":
        st.warning("Değişiklikler yeni analizleri etkiler ve denetim izine kaydedilir.")
        rule_process=active_process
        st.info(f"Düzenlenen süreç: {tr_text(rule_process)}. Burada kaydedilen değişiklikler aynı sürecin Risk Panosu, İşlem Listesi ve Vaka Detayı sonuçlarına otomatik uygulanır.")
        if rule_process=="Para Transferleri":
            st.subheader("Para transferi eşikleri")
            with st.form("rules"):
                c1,c2,c3=st.columns(3);new=rules.copy();new["inactivity_days_threshold"]=c1.number_input("Hareketsizlik günü",1,3650,int(rules["inactivity_days_threshold"]));new["high_amount"]=c2.number_input("Yüksek tutar",0,100000000,int(rules["high_amount"]),step=10000);new["daily_amount"]=c3.number_input("Günlük tutar",0,100000000,int(rules["daily_amount"]),step=10000);new["daily_count"]=c1.number_input("Günlük adet",1,10000,int(rules["daily_count"]));new["elderly_daily_age"]=c2.number_input("İleri yaş",18,110,int(rules["elderly_daily_age"]));new["elderly_daily_amount"]=c3.number_input("İleri yaş günlük tutar",0,100000000,int(rules["elderly_daily_amount"]),step=10000);new["high_sla_hours"]=c1.number_input("Yüksek SLA saati",1,720,int(rules["high_sla_hours"]));new["medium_sla_hours"]=c2.number_input("Orta SLA saati",1,2160,int(rules["medium_sla_hours"]));
                if st.form_submit_button("Kuralları kaydet",type="primary",width="stretch"):save_rules(new,user["username"]);st.cache_data.clear();st.rerun()
            st.info("Elle eklenen transfer senaryoları mevcut özel kural alanından yönetilmeye devam eder.")
        else:
            base_rules=PROCESS_DEFINITIONS[rule_process]["rules"];saved={int(x["rule_index"]):x for x in process_overrides(rule_process)}
            st.subheader(f"{tr_text(rule_process)} senaryoları")
            st.caption("Bir senaryo seçin; adını, risk puanını, kontrol aksiyonunu ve aktiflik durumunu düzenleyin.")
            rule_index=st.selectbox("Senaryo",range(len(base_rules)),format_func=lambda i:tr_text(saved.get(i,{}).get("name",base_rules[i][0])),key="process_rule_index")
            default_name,default_points,default_action=base_rules[rule_index];current=saved.get(rule_index,{})
            with st.form("process_rule_editor"):
                active_rule=st.checkbox("Senaryo aktif",value=bool(current.get("active",1)))
                edited_name=st.text_input("Senaryo adı",value=tr_text(current.get("name",default_name)))
                edited_points=st.slider("Risk puanı",1,100,int(current.get("points",default_points)))
                edited_action=st.text_area("Önerilen kontrol aksiyonu",value=tr_text(current.get("action",default_action)),height=100)
                if st.form_submit_button("Senaryo değişikliklerini kaydet",type="primary",width="stretch"):
                    try:save_process_rule_override(rule_process,rule_index,active_rule,edited_name,edited_points,edited_action,user["username"]);st.cache_data.clear();st.success("Senaryo güncellendi.");st.rerun()
                    except Exception as e:st.error(str(e))
            rows=[]
            for idx,(name,points,action) in enumerate(base_rules):
                item=saved.get(idx,{});rows.append({"Senaryo":tr_text(item.get("name",name)),"Aktif":"Evet" if bool(item.get("active",1)) else "Hayır","Risk puanı":int(item.get("points",points)),"Kontrol aksiyonu":tr_text(item.get("action",action))})
            st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
    if page=="Sistem yönetimi":
        if tenant_id=="default":
            st.subheader("Kurum çalışma alanları")
            st.caption("Yeni kurum, kendi yöneticisi ve diğer kurumlardan tamamen ayrılmış veri alanıyla oluşturulur.")
            with st.form("new_organization"):
                to1,to2,to3=st.columns(3);tenant_name=to1.text_input("Yeni kurum adı");tenant_admin=to2.text_input("Kurum yöneticisi kullanıcı adı");tenant_password=to3.text_input("Geçici parola (en az 12 karakter)",type="password")
                if st.form_submit_button("İzole kurum çalışma alanı oluştur",type="primary",width="stretch"):
                    try:new_tenant=create_organization(tenant_name,tenant_admin,tenant_password,user["username"]);st.success(f"Kurum oluşturuldu. Çalışma alanı kodu: {new_tenant}");st.rerun()
                    except Exception as e:st.error(str(e))
            organizations=list_organizations();organizations=organizations.rename(columns={"tenant_id":"Çalışma alanı kodu","name":"Kurum","active":"Aktif","created_at":"Oluşturulma tarihi"});organizations["Aktif"]=organizations["Aktif"].map({1:"Evet",0:"Hayır"});st.dataframe(organizations,hide_index=True,width="stretch")
        st.subheader("Kurum görünümü")
        with st.form("organization_settings"):
            os1,os2=st.columns(2);org_name=os1.text_input("Kurum / platform adı",value=organization["organization_name"]);org_color=os2.color_picker("Ana vurgu rengi",value=organization["accent_color"]);org_logo=st.file_uploader("Kurum logosu (PNG veya JPG)",type=["png","jpg","jpeg"])
            if st.form_submit_button("Kurum görünümünü kaydet",type="primary",width="stretch"):
                try:save_organization_settings(org_name,org_color,org_logo.getvalue() if org_logo else None,org_logo.type if org_logo else None,user["username"]);st.rerun()
                except Exception as e:st.error(str(e))
        l,r=st.columns(2)
        with l:
            st.subheader("Kullanıcı oluştur")
            with st.form("new_user_form"):
                nu=st.text_input("Kullanıcı adı");np=st.text_input("Geçici parola (en az 12 karakter)",type="password");nr=st.selectbox("Rol",ROLES,format_func=tr_text)
                if st.form_submit_button("Olustur"):
                    try:create_user(nu,np,nr,user["username"]);st.rerun()
                    except Exception as e:st.error(str(e))
            st.dataframe(list_users(),hide_index=True,width="stretch")
        with r:
            st.subheader("Yedekleme")
            if tenant_id=="default":st.download_button("Tüm platform veritabanı yedeğini indir",backup_bytes(),f"platform_yedek_{datetime.now():%Y%m%d}.db",width="stretch")
            else:st.info("Kurum yedekleri platform yöneticisi tarafından şifreli ve kurum bazında yönetilir. Bu çalışma alanından diğer kurumların bulunduğu veritabanı indirilemez.")
        audit=get_audit();st.subheader("Denetim izi");st.dataframe(audit,hide_index=True,width="stretch",height=350);st.download_button("Denetim izini indir",audit.to_csv(index=False).encode("utf-8-sig"),"denetim_izi.csv")
st.caption("V15 Güvenlik ve KVKK Kontrol Katmanı • MFA • Şifreli kalıcı veri • Oturum ve kilitleme politikaları • Denetlenebilir güvenlik olayları")
