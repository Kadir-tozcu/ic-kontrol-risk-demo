"""Expanded transaction taxonomy and cross-signal scenarios for every process."""
from __future__ import annotations

import numpy as np
import pandas as pd


COMMON_OPTIONAL_FIELDS=["transaction_type","source_channel","branch_id","first_time_counterparty","out_of_hours","approval_override","document_age_days","related_event_count","cross_border","third_party_account"]

PROCESS_TAXONOMY={
    "Para Transferleri":(["Havale","EFT","FAST","SWIFT","Virman","Nakit transfer","Düzenli ödeme","Toplu ödeme","İade/ters işlem","Kripto platformuna transfer"],["SWIFT","Nakit transfer","Toplu ödeme","İade/ters işlem","Kripto platformuna transfer"]),
    "Krediler":(["Bireysel ihtiyaç kredisi","Konut kredisi","Taşıt kredisi","Ticari kredi","Rotatif kredi","Proje finansmanı","Limit artışı","Yeniden yapılandırma"],["Proje finansmanı","Limit artışı","Yeniden yapılandırma"]),
    "Musteri Edinimi / KYC":(["Gerçek kişi edinimi","Tüzel kişi edinimi","Uzaktan edinim","Yabancı müşteri","Vakıf/dernek","Yüksek riskli müşteri güncellemesi","Gerçek faydalanıcı değişikliği"],["Uzaktan edinim","Yabancı müşteri","Vakıf/dernek","Gerçek faydalanıcı değişikliği"]),
    "Kart ve Odeme":(["Fiziki POS","E-ticaret","Temassız ödeme","ATM nakit çekim","Yurt dışı işlem","Dijital cüzdan","Karttan karta transfer","İade/ters ibraz"],["Yurt dışı işlem","Dijital cüzdan","Karttan karta transfer","İade/ters ibraz"]),
    "Muhasebe Kayitlari":(["Manuel yevmiye","Otomatik yevmiye","Masraf tahakkuku","Gelir tahakkuku","Dönem sonu düzeltme","Ters kayıt","Askıda hesap kapama","Grup içi kayıt","Kur farkı kaydı"],["Manuel yevmiye","Dönem sonu düzeltme","Ters kayıt","Askıda hesap kapama","Grup içi kayıt"]),
    "Satin Alma / Tedarikci":(["Mal alımı","Hizmet alımı","Danışmanlık","Tek kaynak alım","Acil alım","Doğrudan temin","Çerçeve sözleşme","Avans ödemesi","Tedarikçi değişikliği"],["Danışmanlık","Tek kaynak alım","Acil alım","Doğrudan temin","Avans ödemesi"]),
    "Personel / Ucret":(["Normal ücret","Prim/ikramiye","Fazla mesai","Masraf iadesi","Avans","Kıdem/ihbar","Manuel bordro düzeltmesi","Banka hesabı değişikliği"],["Prim/ikramiye","Masraf iadesi","Avans","Manuel bordro düzeltmesi","Banka hesabı değişikliği"]),
    "BT / Siber Guvenlik":(["Kullanıcı erişimi","Ayrıcalıklı erişim","Canlı ortam değişikliği","Yama işlemi","Veri aktarımı","Yedek geri dönüş","Güvenlik olayı","Üçüncü taraf bağlantısı","Bulut yapılandırması"],["Ayrıcalıklı erişim","Canlı ortam değişikliği","Veri aktarımı","Güvenlik olayı","Üçüncü taraf bağlantısı"]),
    "Hazine / Piyasa":(["Spot döviz","Forward","Swap","Opsiyon","Tahvil/bono","Repo/ters repo","Türev değerleme","Teminat çağrısı","Grup içi işlem"],["Opsiyon","Türev değerleme","Teminat çağrısı","Grup içi işlem"]),
    "Sube / Operasyon":(["Nakit yatırma","Nakit çekme","Kasa transferi","Müşteri talimatı","Manuel düzeltme","Yetki aşımı","Kiralık kasa erişimi","Gün sonu kapama"],["Kasa transferi","Manuel düzeltme","Yetki aşımı","Kiralık kasa erişimi"]),
    "Uyum / AML":(["Nakit işlem","Yurt dışı transfer","Muhabir banka işlemi","Kripto varlık bağlantısı","Ticaret finansmanı","Bağış/yardım","PEP işlemi","Yaptırım taraması","Fon kaynağı incelemesi"],["Yurt dışı transfer","Muhabir banka işlemi","Kripto varlık bağlantısı","Ticaret finansmanı","Bağış/yardım","PEP işlemi"]),
    "Veri Gizliligi":(["Kayıt görüntüleme","Toplu dışa aktarım","E-posta paylaşımı","Bulut paylaşımı","Yetki değişikliği","Silme/yok etme","Yedek kopyalama","Üçüncü tarafa aktarım"],["Toplu dışa aktarım","E-posta paylaşımı","Bulut paylaşımı","Yedek kopyalama","Üçüncü tarafa aktarım"]),
    "Musteri Sikayetleri":(["Ürün şikâyeti","Hizmet şikâyeti","Ücret/komisyon itirazı","Dolandırıcılık bildirimi","Erişilebilirlik talebi","Kırılgan müşteri başvurusu","Yasal başvuru","Tekrarlanan şikâyet"],["Dolandırıcılık bildirimi","Kırılgan müşteri başvurusu","Yasal başvuru","Tekrarlanan şikâyet"]),
    "Tahsilat / Takip":(["Gecikme araması","Ödeme sözü","Yapılandırma","Teminat nakde çevirme","Manuel feragat","Hukuki takip","Varlık satışı","İlişkili taraf tahsilatı"],["Yapılandırma","Teminat nakde çevirme","Manuel feragat","Hukuki takip","İlişkili taraf tahsilatı"]),
}

PROCESS_ACTIONS={
    "Para Transferleri":"Müşteri iradesini, alıcı ilişkisini, cihaz/oturum bilgisini, fon kaynağını ve işlem amacını doğrula",
    "Krediler":"Kredi tahsis gerekçesini, yetki matrisini ve geri ödeme kapasitesini ikinci gözle incele",
    "Musteri Edinimi / KYC":"Kimlik, gerçek faydalanıcı, coğrafya ve müşteri risk sınıfını geliştirilmiş incelemeye al",
    "Kart ve Odeme":"Cihaz, oturum, üye işyeri ve müşteri iradesini doğrula; gerekirse işlemi geçici durdur",
    "Muhasebe Kayitlari":"Dayanak belge, hesap eşleştirmesi, dönem etkisi ve oluşturan-onaylayan ayrımını incele",
    "Satin Alma / Tedarikci":"İhtiyaç, teklif, fiyat emsali, tedarikçi bağlantısı ve onay zincirini doğrula",
    "Personel / Ucret":"Bordro dayanağı, personel teyidi, IBAN değişikliği ve yönetici onayını doğrula",
    "BT / Siber Guvenlik":"Erişim/değişiklik kaydını doğrula, olayı sınırla ve bağımsız güvenlik incelemesi başlat",
    "Hazine / Piyasa":"Yetki, limit, bağımsız fiyat, karşı taraf ve teyit kayıtlarını incele",
    "Sube / Operasyon":"Talimat, kamera/log, kasa mutabakatı ve maker-checker ayrımını doğrula",
    "Uyum / AML":"Müşteri/karşı taraf, fon kaynağı, ekonomik amaç, coğrafya ve yaptırım bulgularını incele",
    "Veri Gizliligi":"İş amacı, veri minimizasyonu, alıcı, hukuki dayanak ve erişim kayıtlarını doğrula",
    "Musteri Sikayetleri":"Müşteri etkisini, yasal süreyi, kök nedeni ve telafi aksiyonunu öncelikli incele",
    "Tahsilat / Takip":"Yetki, müşteri ödeme kapasitesi, teminat, feragat ve hukuki takip kararını incele",
}


def optional_fields(process):return list(COMMON_OPTIONAL_FIELDS) if process in PROCESS_TAXONOMY else []
def transaction_types(process):return list(PROCESS_TAXONOMY.get(process,([],[]))[0])


def enrich_process_demo(data: pd.DataFrame, process: str, seed=42) -> pd.DataFrame:
    if process not in PROCESS_TAXONOMY:return data
    result=data.copy();r=np.random.default_rng(seed+17);n=len(result);types,_=PROCESS_TAXONOMY[process]
    result["transaction_type"]=r.choice(types,n);result["source_channel"]=r.choice(["Şube","Mobil","İnternet","Operasyon","API","Toplu dosya"],n,p=[.18,.2,.2,.18,.12,.12]);result["branch_id"]=[f"BR-{x:04d}" for x in r.integers(1,180,n)]
    result["first_time_counterparty"]=r.random(n)<.11;result["out_of_hours"]=r.random(n)<.09;result["approval_override"]=r.random(n)<.045;result["document_age_days"]=r.integers(0,100,n);result["related_event_count"]=r.integers(0,9,n);result["cross_border"]=r.random(n)<.12;result["third_party_account"]=r.random(n)<.06
    return result


def _bool(series):return series.fillna(False).astype(str).str.strip().str.casefold().isin(["true","1","evet","e","yes"])


def apply_expanded_scenarios(data: pd.DataFrame, process: str) -> pd.DataFrame:
    if process not in PROCESS_TAXONOMY or data.empty:return data
    result=data.copy();types,high_types=PROCESS_TAXONOMY[process];idx=result.index
    text=result.get("transaction_type",pd.Series("",index=idx)).astype(str);override=_bool(result.get("approval_override",pd.Series(False,index=idx)));offhours=_bool(result.get("out_of_hours",pd.Series(False,index=idx)));first=_bool(result.get("first_time_counterparty",pd.Series(False,index=idx)));cross=_bool(result.get("cross_border",pd.Series(False,index=idx)));third=_bool(result.get("third_party_account",pd.Series(False,index=idx)));related=pd.to_numeric(result.get("related_event_count",pd.Series(0,index=idx)),errors="coerce").fillna(0);doc_age=pd.to_numeric(result.get("document_age_days",pd.Series(0,index=idx)),errors="coerce").fillna(0)
    high=text.isin(high_types);rules=[(high&override,35,"Yüksek hassasiyetli işlem türünde yetki aşımı"),(high&offhours,25,"Hassas işlem türü mesai dışında gerçekleşti"),(first&cross,25,"İlk kez çalışılan karşı tarafla sınır ötesi işlem"),(third&override,30,"Üçüncü taraf hesabı ve yetki aşımı birlikte gerçekleşti"),(related>=5,20,"Kısa dönemde yoğun bağlantılı işlem örüntüsü"),(high&(doc_age>=30),20,"Hassas işlem türünde eski/gecikmiş dayanak belge")]
    action=PROCESS_ACTIONS[process]
    for mask,points,reason in rules:
        mask=mask.fillna(False)
        if not mask.any():continue
        result.loc[mask,"risk_score"]=(pd.to_numeric(result.loc[mask,"risk_score"],errors="coerce").fillna(0)+points).clip(upper=100)
        result.loc[mask,"risk_reasons"]=result.loc[mask,"risk_reasons"].map(lambda x:f"{x} | +{points}: {reason}" if x and not str(x).startswith("Tetiklenen") else f"+{points}: {reason}")
        result.loc[mask,"recommended_actions"]=result.loc[mask,"recommended_actions"].map(lambda x:str(x) if action in str(x) else (f"{x} | {action}" if x and not str(x).startswith("Standart") else action))
    result["risk_level"]=np.select([result.risk_score>=70,result.risk_score>=40],["YUKSEK","ORTA"],default="DUSUK")
    return result


def scenario_catalog(process: str) -> pd.DataFrame:
    if process not in PROCESS_TAXONOMY:return pd.DataFrame()
    _,high_types=PROCESS_TAXONOMY[process];rows=[
        ("Hassas tür + yetki aşımı",35,f"İşlem türü {', '.join(high_types)} ve yetki aşımı"),
        ("Hassas tür + mesai dışı",25,"Hassas işlem türü ve mesai dışı gerçekleşme"),
        ("Yeni karşı taraf + sınır ötesi",25,"İlk işlem yapılan karşı taraf ve sınır ötesi hareket"),
        ("Üçüncü taraf hesabı + yetki aşımı",30,"Üçüncü taraf hesabı kullanımı ve istisnai onay"),
        ("Bağlantılı işlem yoğunluğu",20,"İlişkili olay/işlem sayısı 5 veya üzeri"),
        ("Hassas tür + eski belge",20,"Dayanak belge yaşı 30 gün veya üzeri"),
    ]
    return pd.DataFrame(rows,columns=["Senaryo","Puan","Koşul"])
