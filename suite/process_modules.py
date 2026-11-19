"""Additional internal-control process modules with explainable rules."""
from __future__ import annotations

import numpy as np
import pandas as pd
from suite.data_dictionary import field_label, normalize_columns

PROCESS_DEFINITIONS = {
    "Krediler": {
        "fields": ["record_id","event_date","customer_id","loan_amount","collateral_value","monthly_income","debt_ratio","credit_score","exception_flag","rapid_default_days","related_party"],
        "rules": [
            ("Teminat orani %90 uzerinde",25,"Ek teminat ve ikinci seviye kredi onayi iste"),
            ("Borc/gelir orani %60 uzerinde",20,"Gelir belgelerini ve geri odeme kapasitesini dogrula"),
            ("Dusuk kredi skoru ile yuksek kredi",25,"Kredi komitesi istisna onayi iste"),
            ("Politika istisnasi kullanildi",20,"Istisna gerekcesi ve onay yetkisini incele"),
            ("Ilk 90 gunde temerrut",30,"Tahsis surecini ve olasi suistimali incele"),
            ("Iliskili taraf kredisi",35,"Cikar catismasi ve emsallere uygunluk kontrolu yap"),
        ],
    },
    "Musteri Edinimi / KYC": {
        "fields": ["record_id","event_date","customer_id","risk_country","pep","missing_documents","identity_retry_count","beneficial_owner_missing","address_mismatch","remote_onboarding"],
        "rules": [
            ("Yuksek riskli ulke",30,"Gelistirilmis musteri incelemesi uygula"),
            ("PEP musteri",30,"Ust yonetim onayi ve servet kaynagi incelemesi yap"),
            ("Eksik belge",20,"Hesap aktivasyonundan once belgeleri tamamla"),
            ("Kimlik dogrulama tekrari 3+",20,"Kimlik sahteciligi gostergelerini incele"),
            ("Gercek faydalanici eksik",35,"Gercek faydalaniciyi tespit etmeden sureci durdur"),
            ("Adres uyusmazligi ve uzaktan edinim",25,"Adres ve kimligi bagimsiz kaynaktan dogrula"),
        ],
    },
    "Kart ve Odeme": {
        "fields": ["record_id","event_date","customer_id","amount","historical_avg","transaction_hour","country","new_device","card_present","merchant_risk","attempts_10m"],
        "rules": [
            ("Tutar gecmis ortalamanin 5+ kati",25,"Musteri teyidi ve harcama deseni kontrolu yap"),
            ("10 dakikada 5+ deneme",30,"Karti gecici olarak izlemeye al"),
            ("Yeni cihaz ve kart mevcut degil",25,"Cihaz ve oturum dogrulamasi yap"),
            ("Yuksek riskli uye isyeri",25,"Uye isyeri ve islem amacini incele"),
            ("Gece yurtdisi islemi",20,"Musteri konumu ve islem iradesini dogrula"),
        ],
    },
    "Muhasebe Kayitlari": {
        "fields": ["record_id","event_date","customer_id","journal_amount","manual_entry","weekend_entry","same_creator_approver","suspense_days","period_end","missing_description","reversal_24h"],
        "rules": [
            ("Yuksek tutarli manuel kayit",25,"Dayanak belge ve hesap eslestirmesini incele"),
            ("Kaydi giren ve onaylayan ayni",35,"Gorevler ayriligi ihlalini incele"),
            ("Askida hesapta 30+ gun",25,"Askida bakiyeyi kapatma planina bagla"),
            ("Donem sonu hafta sonu kaydi",20,"Donem sonu yonetim kaydi riskini incele"),
            ("Aciklamasiz kayit",15,"Belge ve aciklama tamamlanmadan onaylama"),
            ("24 saat icinde ters kayit",20,"Ilk kaydin amacini ve hatali kayit ihtimalini incele"),
        ],
    },
    "Satin Alma / Tedarikci": {
        "fields": ["record_id","event_date","customer_id","invoice_amount","approval_limit","bids_count","vendor_age_days","vendor_employee_match","duplicate_invoice","split_count","single_source"],
        "rules": [
            ("Onay limitinin hemen altinda fatura",25,"Bolunmus satin alma ihtimalini incele"),
            ("Teklif sayisi 3 altinda",15,"Rekabet ve teklif gerekcesini kontrol et"),
            ("Yeni tedarikciye yuksek odeme",25,"Tedarikci durum tespiti ve banka hesabi teyidi yap"),
            ("Tedarikci-personel eslesmesi",40,"Cikar catismasi incelemesi baslat"),
            ("Mukerrer fatura",40,"Odemeyi durdur ve fatura eslestirmesi yap"),
            ("Bolunmus siparis 3+",25,"Limit asimi ve onaydan kacinma ihtimalini incele"),
            ("Tek kaynak satin alma",15,"Tek kaynak gerekcesi ve fiyat emsalini kontrol et"),
        ],
    },
    "Personel / Ucret": {
        "fields": ["record_id","event_date","customer_id","payment_amount","monthly_salary","duplicate_iban_count","terminated_employee","overtime_hours","manager_approval","employee_vendor_match","payroll_change_days"],
        "rules": [
            ("Odeme maasin 2+ kati",25,"Bordro farki ve ek odeme belgesini incele"),
            ("Ayni IBAN 2+ personelde",35,"Hayali personel ve yanlis hesap ihtimalini incele"),
            ("Isten ayrilan personele odeme",40,"Odemeyi durdur ve cikis kaydini dogrula"),
            ("80 saat uzeri fazla mesai",20,"Puantaj ve yonetici onayini incele"),
            ("Yonetici onayi yok",20,"Odeme oncesi yetkili onayi al"),
            ("Personel-tedarikci eslesmesi",40,"Cikar catismasi incelemesi baslat"),
            ("Bordrodan 3 gun once hesap degisikligi",25,"IBAN degisikligini personelden teyit et"),
        ],
    },
    "BT / Siber Guvenlik": {
        "fields": ["record_id","event_date","customer_id","critical_asset","critical_vulnerability_count","patch_age_days","privileged_account","dormant_account_days","failed_logins_10m","unapproved_change","backup_test_age_days","incident_open_hours"],
        "rules": [("Kritik varlikta kritik acik",40,"Acigi onceliklendir, varligi izole et ve duzeltme plani ac"),("Yama 30+ gun gecikmis",25,"Yama istisnasini ve telafi edici kontrolleri incele"),("Ayricalikli hesap 90+ gun hareketsiz",35,"Hesabi kapat veya yetkisini yeniden onayla"),("10 dakikada 10+ basarisiz giris",30,"Hesabi kilitle ve olay incelemesi baslat"),("Onaysiz canli ortam degisikligi",40,"Degisikligi geri al ve acil degisiklik surecini incele"),("Yedek geri donus testi 180+ gun",25,"Geri donus testi planla ve sonucu kaydet"),("Kritik olay 24+ saattir acik",35,"Olay eskalasyonu ve kriz yonetimini etkinlestir")],
    },
    "Hazine / Piyasa": {
        "fields": ["record_id","event_date","customer_id","deal_amount","dealer_limit","counterparty_exposure","counterparty_limit","off_market_bps","same_dealer_approver","confirmation_delay_hours","unusual_pnl","manual_price"],
        "rules": [("Dealer limiti %90+ kullanildi",25,"Limit ve yetki onayini incele"),("Karsi taraf limiti asildi",40,"Yeni islemi durdur ve limit istisnasini eskale et"),("Piyasa fiyatindan 50+ baz puan sapma",30,"Bagimsiz fiyat dogrulamasi yap"),("Dealer ve onaylayan ayni",40,"Gorevler ayriligi ihlalini incele"),("Teyit 24+ saat gecikmis",20,"Karsi taraf teyidini tamamla"),("Olagandisi kar/zarar",30,"Pozisyon ve fiyatlama kayitlarini incele"),("Manuel fiyat kullanildi",20,"Fiyat kaynagi ve istisna onayini dogrula")],
    },
    "Sube / Operasyon": {
        "fields": ["record_id","event_date","customer_id","cash_difference","override_count","same_maker_checker","unresolved_eod_items","manual_correction_count","vault_access_offhours","document_missing","customer_wait_days"],
        "rules": [("Kasa farki 1000 TL+",30,"Kasa sayimi ve kamera/log kontrolu yap"),("Gunluk 10+ yetki asimi",25,"Override gerekcelerini ve kullanici desenini incele"),("Islemi yapan ve kontrol eden ayni",40,"Gorevler ayriligi ihlalini incele"),("Gun sonu 5+ acik kalem",20,"Acik kalemleri sorumlu ve terminle kapat"),("Gunluk 5+ manuel duzeltme",25,"Kok neden ve personel bazli yogunlasmayi incele"),("Mesai disi kasa erisimi",35,"Fiziksel erisim ve kamera kayitlarini incele"),("Eksik islem belgesi",20,"Belge tamamlanana kadar vakayi kapatma")],
    },
    "Uyum / AML": {
        "fields": ["record_id","event_date","customer_id","amount","cash_transaction","high_risk_country","sanctions_match_score","kyc_expired_days","structuring_count","pep","source_of_funds_missing","alert_age_days"],
        "rules": [("Yaptirim eslesme skoru %85+",50,"Islemi durdur ve yaptirim incelemesine yonlendir"),("Yuksek riskli ulkeye transfer",30,"Gelistirilmis inceleme ve islem amaci kontrolu yap"),("Nakit islem 500.000 TL+",25,"Fon kaynagi ve ekonomik amaci dogrula"),("Limit alti yapilandirma 3+",35,"Baglantili islemleri tek vaka olarak incele"),("KYC 90+ gun gecikmis",25,"Musteri bilgilerini guncelle"),("PEP ve fon kaynagi eksik",40,"Ust yonetim onayi ve servet/fon kaynagi incelemesi yap"),("AML alarmi 72+ saat acik",25,"Vaka SLA eskalasyonu yap")],
    },
    "Veri Gizliligi": {
        "fields": ["record_id","event_date","customer_id","sensitive_record_count","bulk_export","off_hours_access","business_purpose_missing","external_share","retention_exceeded_days","unencrypted_file","access_role_mismatch"],
        "rules": [("1000+ hassas kayda erisim",30,"Erisim amaci ve kullanici yetkisini incele"),("Toplu veri disari aktarimi",40,"Aktarimi durdur ve veri sizintisi incelemesi baslat"),("Mesai disi erisim",20,"Kullanici ve oturum kayitlarini dogrula"),("Is amaci kaydi yok",25,"Isleme amaci ve hukuki dayanagi dogrula"),("Kurum disi paylasim",40,"Alici, aktarim dayanagi ve guvenlik tedbirlerini incele"),("Saklama suresi 90+ gun asildi",25,"Silme/yok etme surecini baslat"),("Sifresiz hassas dosya",35,"Dosyayi sifrele ve erisimleri incele"),("Rol-yetki uyusmazligi",35,"Yetkiyi kaldir ve periyodik erisim gozden gecirmesi yap")],
    },
    "Musteri Sikayetleri": {
        "fields": ["record_id","event_date","customer_id","open_days","repeat_complaint_count","vulnerable_customer","financial_loss","regulatory_deadline_days","root_cause_missing","compensation_amount","product_suitability_issue"],
        "rules": [("Sikayet 15+ gundur acik",20,"Sorumlu ata ve cozum terminini eskale et"),("Ayni konuda 3+ tekrar",25,"Kok neden analizi ve kalici aksiyon ac"),("Kirılgan musteri sikayeti",25,"Oncelikli ve uygun iletisimle ele al"),("Musteri zarari 10.000 TL+",30,"Tazmin ve kontrol zafiyeti incelemesi yap"),("Yasal son tarihe 2 gun kaldi",35,"Uyum/hukuk eskalasyonu yap"),("Kok neden kaydi yok",15,"Kok neden ve duzeltici faaliyet kaydet"),("Uygun olmayan urun satisi",40,"Urun uygunlugu ve satis surecini incele")],
    },
    "Tahsilat / Takip": {
        "fields": ["record_id","event_date","customer_id","overdue_days","exposure_amount","restructure_count","manual_waiver_amount","collateral_expired","same_collector_approver","promise_broken_count","legal_action_delay_days","related_party"],
        "rules": [("90+ gun gecikme ve yuksek risk",35,"Takip stratejisini ve karsilik durumunu incele"),("3+ yeniden yapilandirma",25,"Odeme kapasitesi ve istisna onayini incele"),("100.000 TL+ manuel feragat",35,"Feragat yetkisi ve gerekcesini dogrula"),("Teminat suresi dolmus",35,"Teminati yenile veya risk azaltici aksiyon al"),("Tahsilatci ve onaylayan ayni",40,"Gorevler ayriligi ihlalini incele"),("3+ bozulan odeme sozu",20,"Tahsilat stratejisini eskale et"),("Hukuki takip 30+ gun gecikmis",30,"Hukuk surecini baslat ve gecikme nedenini incele"),("Iliskili taraf takibi",30,"Emsallere uygunluk ve cikar catismasini incele")],
    },
}

def _b(s): return s.astype(str).str.lower().isin(["true","1","yes","evet","e"])

def validate_process(df, process):
    data=normalize_columns(df,PROCESS_DEFINITIONS[process]["fields"])
    missing=[c for c in PROCESS_DEFINITIONS[process]["fields"] if c not in data.columns]
    if missing: raise ValueError("Eksik zorunlu sütunlar: "+", ".join(field_label(c) for c in missing))
    data["event_date"]=pd.to_datetime(data["event_date"],errors="coerce",dayfirst=True,format="mixed")
    if data["event_date"].isna().any(): raise ValueError("Kayıt Tarihi alanında geçersiz veya boş tarih var")
    return data

def score_process(df, process, overrides=None):
    d=validate_process(df,process);score=np.zeros(len(d),dtype=int);reasons=[[] for _ in range(len(d))];actions=[[] for _ in range(len(d))]
    def apply(mask,points,reason,action):
        active=mask.fillna(False).to_numpy(bool);score[active]+=points
        for i in np.flatnonzero(active):reasons[i].append(f"+{points}: {reason}");actions[i].append(action)
    num=lambda c:pd.to_numeric(d[c],errors="coerce")
    if process=="Krediler":
        masks=[num("loan_amount")/num("collateral_value").replace(0,np.nan)>.9,num("debt_ratio")>.6,(num("credit_score")<500)&(num("loan_amount")>=500000),_b(d.exception_flag),num("rapid_default_days")<=90,_b(d.related_party)]
    elif process=="Musteri Edinimi / KYC":
        masks=[d.risk_country.str.upper().isin(["YUKSEK","HIGH"]),_b(d.pep),_b(d.missing_documents),num("identity_retry_count")>=3,_b(d.beneficial_owner_missing),_b(d.address_mismatch)&_b(d.remote_onboarding)]
    elif process=="Kart ve Odeme":
        masks=[num("amount")>=5*num("historical_avg").replace(0,np.nan),num("attempts_10m")>=5,_b(d.new_device)&~_b(d.card_present),d.merchant_risk.str.upper().isin(["YUKSEK","HIGH"]),num("transaction_hour").between(0,6)&(d.country.str.upper()!="TR")]
    elif process=="Muhasebe Kayitlari":
        masks=[_b(d.manual_entry)&(num("journal_amount")>=500000),_b(d.same_creator_approver),num("suspense_days")>=30,_b(d.period_end)&_b(d.weekend_entry),_b(d.missing_description),_b(d.reversal_24h)]
    elif process=="Satin Alma / Tedarikci":
        ratio=num("invoice_amount")/num("approval_limit").replace(0,np.nan);masks=[ratio.between(.90,.9999),num("bids_count")<3,(num("vendor_age_days")<90)&(num("invoice_amount")>=500000),_b(d.vendor_employee_match),_b(d.duplicate_invoice),num("split_count")>=3,_b(d.single_source)]
    elif process=="Personel / Ucret":
        masks=[num("payment_amount")>=2*num("monthly_salary").replace(0,np.nan),num("duplicate_iban_count")>=2,_b(d.terminated_employee),num("overtime_hours")>80,~_b(d.manager_approval),_b(d.employee_vendor_match),num("payroll_change_days")<=3]
    elif process=="BT / Siber Guvenlik":
        masks=[_b(d.critical_asset)&(num("critical_vulnerability_count")>=1),num("patch_age_days")>=30,_b(d.privileged_account)&(num("dormant_account_days")>=90),num("failed_logins_10m")>=10,_b(d.unapproved_change),num("backup_test_age_days")>=180,num("incident_open_hours")>=24]
    elif process=="Hazine / Piyasa":
        masks=[num("deal_amount")>=.9*num("dealer_limit"),num("counterparty_exposure")>num("counterparty_limit"),num("off_market_bps").abs()>=50,_b(d.same_dealer_approver),num("confirmation_delay_hours")>=24,_b(d.unusual_pnl),_b(d.manual_price)]
    elif process=="Sube / Operasyon":
        masks=[num("cash_difference").abs()>=1000,num("override_count")>=10,_b(d.same_maker_checker),num("unresolved_eod_items")>=5,num("manual_correction_count")>=5,_b(d.vault_access_offhours),_b(d.document_missing)]
    elif process=="Uyum / AML":
        masks=[num("sanctions_match_score")>=85,_b(d.high_risk_country),_b(d.cash_transaction)&(num("amount")>=500000),num("structuring_count")>=3,num("kyc_expired_days")>=90,_b(d.pep)&_b(d.source_of_funds_missing),num("alert_age_days")>=72]
    elif process=="Veri Gizliligi":
        masks=[num("sensitive_record_count")>=1000,_b(d.bulk_export),_b(d.off_hours_access),_b(d.business_purpose_missing),_b(d.external_share),num("retention_exceeded_days")>=90,_b(d.unencrypted_file),_b(d.access_role_mismatch)]
    elif process=="Musteri Sikayetleri":
        masks=[num("open_days")>=15,num("repeat_complaint_count")>=3,_b(d.vulnerable_customer),num("financial_loss")>=10000,num("regulatory_deadline_days")<=2,_b(d.root_cause_missing),_b(d.product_suitability_issue)]
    elif process=="Tahsilat / Takip":
        masks=[(num("overdue_days")>=90)&(num("exposure_amount")>=500000),num("restructure_count")>=3,num("manual_waiver_amount")>=100000,_b(d.collateral_expired),_b(d.same_collector_approver),num("promise_broken_count")>=3,num("legal_action_delay_days")>=30,_b(d.related_party)]
    else: raise ValueError("Bilinmeyen surec")
    override_map={int(x["rule_index"]):x for x in (overrides or [])}
    for idx,(mask,(reason,points,action)) in enumerate(zip(masks,PROCESS_DEFINITIONS[process]["rules"])):
        override=override_map.get(idx)
        if override:
            if not bool(override.get("active",1)):continue
            reason=str(override.get("name") or reason);points=int(override.get("points",points));action=str(override.get("action") or action)
        apply(mask,points,reason,action)
    d["risk_score"]=np.minimum(score,100);d["risk_level"]=np.select([d.risk_score>=70,d.risk_score>=40],["YUKSEK","ORTA"],default="DUSUK");d["risk_reasons"]=[" | ".join(x) if x else "Tetiklenen risk kurali yok" for x in reasons];d["recommended_actions"]=[" | ".join(dict.fromkeys(x)) if x else "Standart kontrole devam et" for x in actions];d["process_type"]=process
    return d

def generate_process_demo(process,n=1500,seed=42):
    r=np.random.default_rng(seed);ids=[f"{process[:3].upper()}-{i:06d}" for i in range(1,n+1)];base={"record_id":ids,"event_date":pd.Timestamp("2026-08-01")+pd.to_timedelta(r.integers(0,30,n),unit="D"),"customer_id":[f"CUST-{x:05d}" for x in r.integers(1,n//2+2,n)]}
    if process=="Krediler":base|={"loan_amount":r.lognormal(13,1,n).round(2),"collateral_value":r.lognormal(13.1,1,n).round(2),"monthly_income":r.lognormal(10.5,.6,n).round(2),"debt_ratio":r.uniform(.1,.9,n).round(2),"credit_score":r.integers(300,900,n),"exception_flag":r.random(n)<.08,"rapid_default_days":r.integers(30,800,n),"related_party":r.random(n)<.02}
    elif process=="Musteri Edinimi / KYC":base|={"risk_country":r.choice(["DUSUK","ORTA","YUKSEK"],n,p=[.75,.2,.05]),"pep":r.random(n)<.03,"missing_documents":r.random(n)<.08,"identity_retry_count":r.integers(0,6,n),"beneficial_owner_missing":r.random(n)<.04,"address_mismatch":r.random(n)<.1,"remote_onboarding":r.random(n)<.6}
    elif process=="Kart ve Odeme":base|={"amount":r.lognormal(9,1.2,n).round(2),"historical_avg":r.lognormal(8.5,.8,n).round(2),"transaction_hour":r.integers(0,24,n),"country":r.choice(["TR","US","DE","GB"],n,p=[.8,.07,.07,.06]),"new_device":r.random(n)<.12,"card_present":r.random(n)<.55,"merchant_risk":r.choice(["DUSUK","ORTA","YUKSEK"],n,p=[.8,.15,.05]),"attempts_10m":r.integers(1,8,n)}
    elif process=="Muhasebe Kayitlari":base|={"journal_amount":r.lognormal(12,1.3,n).round(2),"manual_entry":r.random(n)<.3,"weekend_entry":r.random(n)<.08,"same_creator_approver":r.random(n)<.03,"suspense_days":r.integers(0,90,n),"period_end":r.random(n)<.15,"missing_description":r.random(n)<.05,"reversal_24h":r.random(n)<.06}
    elif process=="Satin Alma / Tedarikci":base|={"invoice_amount":r.lognormal(12,1,n).round(2),"approval_limit":r.choice([100000,500000,1000000],n),"bids_count":r.integers(1,6,n),"vendor_age_days":r.integers(1,3000,n),"vendor_employee_match":r.random(n)<.02,"duplicate_invoice":r.random(n)<.03,"split_count":r.integers(1,6,n),"single_source":r.random(n)<.12}
    elif process=="Personel / Ucret":base|={"payment_amount":r.lognormal(10.5,.5,n).round(2),"monthly_salary":r.lognormal(10.3,.35,n).round(2),"duplicate_iban_count":r.integers(1,4,n),"terminated_employee":r.random(n)<.02,"overtime_hours":r.integers(0,120,n),"manager_approval":r.random(n)>.08,"employee_vendor_match":r.random(n)<.02,"payroll_change_days":r.integers(0,180,n)}
    elif process=="BT / Siber Guvenlik":base|={"critical_asset":r.random(n)<.35,"critical_vulnerability_count":r.integers(0,5,n),"patch_age_days":r.integers(0,120,n),"privileged_account":r.random(n)<.15,"dormant_account_days":r.integers(0,240,n),"failed_logins_10m":r.integers(0,20,n),"unapproved_change":r.random(n)<.04,"backup_test_age_days":r.integers(1,365,n),"incident_open_hours":r.integers(0,96,n)}
    elif process=="Hazine / Piyasa":base|={"deal_amount":r.lognormal(15,1,n).round(2),"dealer_limit":r.choice([5e6,1e7,2e7],n),"counterparty_exposure":r.lognormal(15,1,n).round(2),"counterparty_limit":r.choice([5e6,1e7,2e7],n),"off_market_bps":r.normal(0,40,n).round(1),"same_dealer_approver":r.random(n)<.02,"confirmation_delay_hours":r.integers(0,72,n),"unusual_pnl":r.random(n)<.05,"manual_price":r.random(n)<.1}
    elif process=="Sube / Operasyon":base|={"cash_difference":r.normal(0,1500,n).round(2),"override_count":r.integers(0,20,n),"same_maker_checker":r.random(n)<.03,"unresolved_eod_items":r.integers(0,12,n),"manual_correction_count":r.integers(0,10,n),"vault_access_offhours":r.random(n)<.03,"document_missing":r.random(n)<.07,"customer_wait_days":r.integers(0,20,n)}
    elif process=="Uyum / AML":base|={"amount":r.lognormal(12,1.3,n).round(2),"cash_transaction":r.random(n)<.2,"high_risk_country":r.random(n)<.06,"sanctions_match_score":r.integers(0,101,n),"kyc_expired_days":r.integers(0,240,n),"structuring_count":r.integers(0,6,n),"pep":r.random(n)<.03,"source_of_funds_missing":r.random(n)<.1,"alert_age_days":r.integers(0,168,n)}
    elif process=="Veri Gizliligi":base|={"sensitive_record_count":r.integers(1,5000,n),"bulk_export":r.random(n)<.05,"off_hours_access":r.random(n)<.12,"business_purpose_missing":r.random(n)<.08,"external_share":r.random(n)<.04,"retention_exceeded_days":r.integers(0,365,n),"unencrypted_file":r.random(n)<.06,"access_role_mismatch":r.random(n)<.05}
    elif process=="Musteri Sikayetleri":base|={"open_days":r.integers(0,45,n),"repeat_complaint_count":r.integers(0,6,n),"vulnerable_customer":r.random(n)<.12,"financial_loss":r.lognormal(8,1.5,n).round(2),"regulatory_deadline_days":r.integers(0,20,n),"root_cause_missing":r.random(n)<.25,"compensation_amount":r.lognormal(7,1,n).round(2),"product_suitability_issue":r.random(n)<.06}
    elif process=="Tahsilat / Takip":base|={"overdue_days":r.integers(0,365,n),"exposure_amount":r.lognormal(13,1.2,n).round(2),"restructure_count":r.integers(0,6,n),"manual_waiver_amount":r.lognormal(10,1.5,n).round(2),"collateral_expired":r.random(n)<.08,"same_collector_approver":r.random(n)<.03,"promise_broken_count":r.integers(0,6,n),"legal_action_delay_days":r.integers(0,90,n),"related_party":r.random(n)<.03}
    else:raise ValueError("Bilinmeyen surec")
    return pd.DataFrame(base)
