"""Turkish field labels and upload-column aliases used by every process."""
from __future__ import annotations

import re
import pandas as pd

FIELD_LABELS = {
    "transaction_id":"İşlem Numarası","record_id":"Kayıt Numarası","customer_id":"Müşteri Numarası",
    "transaction_datetime":"İşlem Tarihi ve Saati","event_date":"Kayıt Tarihi","inactivity_days":"Hareketsizlik Gün Sayısı",
    "age":"Müşteri Yaşı","transaction_amount":"İşlem Tutarı","historical_avg_amount":"Müşterinin Tarihsel Ortalama Tutarı",
    "new_recipient":"Yeni Alıcı mı?","transaction_hour":"İşlem Saati","transaction_count_after_reactivation":"Yeniden Aktivasyon Sonrası İşlem Adedi",
    "loan_amount":"Kredi Tutarı","collateral_value":"Teminat Değeri","monthly_income":"Aylık Gelir","debt_ratio":"Borç / Gelir Oranı",
    "credit_score":"Kredi Risk Skoru","exception_flag":"Politika İstisnası","rapid_default_days":"Temerrüde Kadar Geçen Gün","related_party":"İlişkili Taraf mı?",
    "amount":"Tutar","historical_avg":"Tarihsel Ortalama Tutar","country":"Ülke","risk_country":"Ülke Risk Seviyesi",
    "pep":"PEP Müşteri mi?","missing_documents":"Eksik Belge Var mı?","identity_retry_count":"Kimlik Doğrulama Deneme Sayısı",
    "beneficial_owner_missing":"Gerçek Faydalanıcı Eksik mi?","address_mismatch":"Adres Uyumsuzluğu","remote_onboarding":"Uzaktan Müşteri Edinimi",
    "journal_amount":"Muhasebe Kayıt Tutarı","invoice_amount":"Fatura Tutarı","approval_limit":"Onay Limiti","payment_amount":"Ödeme Tutarı",
    "monthly_salary":"Aylık Ücret","deal_amount":"İşlem / Anlaşma Tutarı","exposure_amount":"Risk Tutarı","financial_loss":"Finansal Kayıp",
    "risk_score":"Risk Skoru","risk_level":"Risk Seviyesi","risk_reasons":"Risk Gerekçeleri","recommended_actions":"Önerilen Kontrol Aksiyonları",
    "transaction_date":"İşlem Tarihi","daily_transfer_total":"Günlük Toplam Transfer Tutarı","daily_transaction_count":"Günlük İşlem Adedi",
    "age_band":"Yaş Grubu","amount_vs_average":"Tutarın Tarihsel Ortalamaya Oranı","risk_reasons_json":"Risk Gerekçeleri Teknik Verisi","recommended_actions_json":"Kontrol Aksiyonları Teknik Verisi",
    "case_status":"Vaka Durumu","process_type":"Süreç Türü",
    "transaction_type":"İşlem Türü","source_channel":"Kaynak Kanal","branch_id":"Şube/Birim Numarası","first_time_counterparty":"Karşı Tarafla İlk İşlem mi?","out_of_hours":"Mesai Dışı mı?","approval_override":"Yetki/Onay Aşımı Var mı?","document_age_days":"Dayanak Belge Yaşı (Gün)","related_event_count":"Bağlantılı İşlem/Olay Sayısı","cross_border":"Sınır Ötesi İşlem mi?","third_party_account":"Üçüncü Taraf Hesabı mı?",
}
FIELD_LABELS.update({
    "recipient_id":"Alıcı Numarası","account_balance_before":"İşlem Öncesi Hesap Bakiyesi","device_id":"Cihaz Numarası","ip_address":"IP Adresi","channel":"İşlem Kanalı","currency":"Para Birimi","destination_country":"Hedef Ülke","transaction_status":"İşlem Durumu","original_transaction_id":"Bağlantılı İlk İşlem Numarası","employee_id":"Personel Numarası","new_currency_or_country":"Yeni Para Birimi veya Ülke",
    "new_device":"Yeni Cihaz mı?","card_present":"Kart Fiziksel Olarak Mevcut mu?","merchant_risk":"Üye İşyeri Risk Seviyesi","attempts_10m":"Son 10 Dakikadaki Deneme Sayısı",
    "manual_entry":"Manuel Kayıt mı?","weekend_entry":"Hafta Sonu Kaydı mı?","same_creator_approver":"Kaydı Oluşturan ve Onaylayan Aynı mı?","suspense_days":"Askıda Hesapta Bekleme Günü","period_end":"Dönem Sonu Kaydı mı?","missing_description":"Açıklama Eksik mi?","reversal_24h":"24 Saat İçinde Ters Kayıt mı?",
    "bids_count":"Teklif Sayısı","vendor_age_days":"Tedarikçi Yaşı (Gün)","vendor_employee_match":"Tedarikçi–Personel Eşleşmesi","duplicate_invoice":"Mükerrer Fatura mı?","split_count":"Bölünmüş Sipariş Sayısı","single_source":"Tek Kaynak Satın Alma mı?",
    "duplicate_iban_count":"Aynı IBAN'ı Kullanan Personel Sayısı","terminated_employee":"İşten Ayrılan Personel mi?","overtime_hours":"Fazla Mesai Saati","manager_approval":"Yönetici Onayı Var mı?","employee_vendor_match":"Personel–Tedarikçi Eşleşmesi","payroll_change_days":"Son Bordro Değişikliğinden Geçen Gün",
    "critical_asset":"Kritik Varlık mı?","critical_vulnerability_count":"Kritik Zafiyet Sayısı","patch_age_days":"Yama Gecikme Süresi (Gün)","privileged_account":"Ayrıcalıklı Hesap mı?","dormant_account_days":"Hesabın Hareketsiz Kaldığı Gün","failed_logins_10m":"Son 10 Dakikadaki Başarısız Giriş","unapproved_change":"Onaysız Değişiklik mi?","backup_test_age_days":"Son Yedek Dönüş Testinden Geçen Gün","incident_open_hours":"Olayın Açık Kaldığı Saat",
    "dealer_limit":"İşlemci Limiti","counterparty_exposure":"Karşı Taraf Risk Tutarı","counterparty_limit":"Karşı Taraf Limiti","off_market_bps":"Piyasa Fiyatından Sapma (Baz Puan)","same_dealer_approver":"İşlemci ve Onaylayan Aynı mı?","confirmation_delay_hours":"Teyit Gecikmesi (Saat)","unusual_pnl":"Olağandışı Kâr / Zarar mı?","manual_price":"Manuel Fiyat mı?",
    "cash_difference":"Kasa Farkı","override_count":"Yetki Aşımı Sayısı","same_maker_checker":"İşlemi Yapan ve Kontrol Eden Aynı mı?","unresolved_eod_items":"Çözümlenmemiş Gün Sonu Kalemleri","manual_correction_count":"Manuel Düzeltme Sayısı","vault_access_offhours":"Mesai Dışı Kasa Erişimi","document_missing":"İşlem Belgesi Eksik mi?","customer_wait_days":"Müşteri Bekleme Süresi (Gün)",
    "cash_transaction":"Nakit İşlem mi?","high_risk_country":"Yüksek Riskli Ülke mi?","sanctions_match_score":"Yaptırım Eşleşme Skoru","kyc_expired_days":"KYC Güncelleme Gecikmesi (Gün)","structuring_count":"Limit Altı Yapılandırılmış İşlem Sayısı","source_of_funds_missing":"Fon Kaynağı Eksik mi?","alert_age_days":"Alarmın Açık Kaldığı Gün",
    "sensitive_record_count":"Erişilen Hassas Kayıt Sayısı","bulk_export":"Toplu Veri Aktarımı mı?","off_hours_access":"Mesai Dışı Erişim mi?","business_purpose_missing":"İş Amacı Eksik mi?","external_share":"Kurum Dışı Paylaşım mı?","retention_exceeded_days":"Saklama Süresi Aşımı (Gün)","unencrypted_file":"Şifresiz Dosya mı?","access_role_mismatch":"Rol–Yetki Uyumsuzluğu",
    "open_days":"Şikâyetin Açık Kaldığı Gün","repeat_complaint_count":"Tekrarlanan Şikâyet Sayısı","vulnerable_customer":"Kırılgan Müşteri mi?","regulatory_deadline_days":"Yasal Son Tarihe Kalan Gün","root_cause_missing":"Kök Neden Kaydı Eksik mi?","compensation_amount":"Tazminat Tutarı","product_suitability_issue":"Ürün Uygunluğu Sorunu mu?",
    "overdue_days":"Gecikme Süresi (Gün)","restructure_count":"Yeniden Yapılandırma Sayısı","manual_waiver_amount":"Manuel Feragat Tutarı","collateral_expired":"Teminat Süresi Dolmuş mu?","same_collector_approver":"Tahsilatçı ve Onaylayan Aynı mı?","promise_broken_count":"Bozulan Ödeme Sözü Sayısı","legal_action_delay_days":"Hukuki Takip Gecikmesi (Gün)"
})

TOKEN_LABELS = {
    "access":"erişim","role":"rol","mismatch":"uyumsuzluğu","address":"adres","alert":"alarm","age":"yaş","days":"gün",
    "approval":"onay","limit":"limiti","attempts":"deneme sayısı","backup":"yedek","test":"testi","beneficial":"gerçek faydalanıcı",
    "owner":"sahibi","missing":"eksik","bids":"teklif","count":"sayısı","bulk":"toplu","export":"dışa aktarım","business":"iş",
    "purpose":"amacı","card":"kart","present":"mevcut","cash":"nakit","difference":"farkı","transaction":"işlem","collateral":"teminat",
    "expired":"süresi dolmuş","compensation":"tazminat","confirmation":"teyit","delay":"gecikme","hours":"saat","counterparty":"karşı taraf",
    "exposure":"risk tutarı","country":"ülke","critical":"kritik","asset":"varlık","vulnerability":"zafiyet","customer":"müşteri","wait":"bekleme",
    "dealer":"işlemci","debt":"borç","ratio":"oranı","document":"belge","dormant":"hareketsiz","account":"hesap","duplicate":"mükerrer",
    "iban":"IBAN","employee":"personel","vendor":"tedarikçi","event":"kayıt","date":"tarihi","exception":"istisna","external":"kurum dışı",
    "share":"paylaşım","failed":"başarısız","logins":"giriş","financial":"finansal","loss":"kayıp","high":"yüksek","risk":"risk",
    "historical":"tarihsel","avg":"ortalama","identity":"kimlik doğrulama","retry":"tekrar","incident":"olay","open":"açık","invoice":"fatura",
    "journal":"muhasebe kaydı","kyc":"KYC","legal":"hukuki","action":"takip","loan":"kredi","manager":"yönetici","manual":"manuel",
    "correction":"düzeltme","entry":"kayıt","price":"fiyat","waiver":"feragat","merchant":"üye işyeri","description":"açıklama",
    "documents":"belgeler","monthly":"aylık","income":"gelir","salary":"ücret","new":"yeni","device":"cihaz","off":"mesai dışı",
    "market":"piyasa","bps":"baz puan","overdue":"gecikme","override":"yetki aşımı","overtime":"fazla mesai","patch":"yama","payment":"ödeme",
    "payroll":"bordro","change":"değişiklik","period":"dönem sonu","privileged":"ayrıcalıklı","product":"ürün","suitability":"uygunluk sorunu",
    "promise":"ödeme sözü","broken":"bozulan","rapid":"erken","default":"temerrüt","regulatory":"yasal","deadline":"son tarih",
    "remote":"uzaktan","onboarding":"müşteri edinimi","repeat":"tekrar","complaint":"şikâyet","restructure":"yeniden yapılandırma",
    "retention":"saklama süresi","exceeded":"aşımı","reversal":"ters kayıt","root":"kök","cause":"neden","same":"aynı kişi",
    "collector":"tahsilatçı","creator":"oluşturan","approver":"onaylayan","maker":"işlemi yapan","checker":"kontrol eden","sanctions":"yaptırım",
    "match":"eşleşme","score":"skoru","sensitive":"hassas","records":"kayıt","single":"tek","source":"kaynak","funds":"fon kaynağı",
    "split":"bölünmüş işlem","structuring":"yapılandırma","suspense":"askıda hesap","terminated":"işten ayrılan","unapproved":"onaysız",
    "unencrypted":"şifresiz","file":"dosya","unresolved":"çözümlenmemiş","eod":"gün sonu","items":"kalem","unusual":"olağandışı",
    "pnl":"kâr / zarar","vault":"kasa","offhours":"mesai dışı erişim","vulnerable":"kırılgan",
}

def field_label(field: str) -> str:
    if field in FIELD_LABELS:return FIELD_LABELS[field]
    return " ".join(TOKEN_LABELS.get(token,token) for token in field.split("_")).strip().title()

def _key(value: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşü]+","_",str(value).strip().casefold()).strip("_")

def normalize_columns(data: pd.DataFrame, expected_fields=None) -> pd.DataFrame:
    codes=set(FIELD_LABELS)|set(expected_fields or [])
    aliases={_key(code):code for code in codes}
    aliases.update({_key(field_label(code)):code for code in codes})
    result=data.copy();result.columns=[aliases.get(_key(c),str(c).strip().lower()) for c in result.columns]
    return result

def turkish_columns(fields) -> list[str]:return [field_label(field) for field in fields]
def rename_for_display(data: pd.DataFrame) -> pd.DataFrame:return data.rename(columns={c:field_label(c) for c in data.columns})
