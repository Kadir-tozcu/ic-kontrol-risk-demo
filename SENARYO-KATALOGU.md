# Risk Ajansı genişletilmiş senaryo kataloğu

Bu sürüm, 14 süreçte 118 işlem türü ve 84 yeni birleşik risk senaryosu içerir.
Mevcut temel kurallar korunmuştur. Yeni göstergeler isteğe bağlı sütunlarla
çalıştığı için eski Excel dosyaları geçerliliğini korur.

## Yeni ortak veri göstergeleri

- İşlem Türü
- Kaynak Kanal
- Şube/Birim Numarası
- Karşı Tarafla İlk İşlem mi?
- Mesai Dışı mı?
- Yetki/Onay Aşımı Var mı?
- Dayanak Belge Yaşı (Gün)
- Bağlantılı İşlem/Olay Sayısı
- Sınır Ötesi İşlem mi?
- Üçüncü Taraf Hesabı mı?

Bu alanlar tek başına kesin usulsüzlük sonucu üretmez. Hassas işlem türü,
istisnai onay, mesai dışı hareket, yeni karşı taraf, sınır ötesi hareket,
üçüncü taraf hesabı, eski belge ve bağlantılı işlem yoğunluğu gibi göstergeler
birlikte değerlendirilir.

## Başlıca dayanaklar

- FATF Virtual Assets Red Flag Indicators: olağandışı işlem örüntüleri, tutar ve
  frekans, coğrafya, gönderen/alıcı profili ve fon/servet kaynağı.
  https://www.fatf-gafi.org/en/publications/Methodsandtrends/Virtual-assets-red-flag-indicators.html
- FATF Trade-Based Money Laundering: fiyat, miktar, kalite, ticaret ve ödeme
  yapılarının kötüye kullanılması.
  https://www.fatf-gafi.org/en/publications/Methodsandtrends/Trade-basedmoneylaundering.html
- Basel Committee, Principles for the Sound Management of Operational Risk:
  operasyonel risk, değişiklik, bilgi teknolojileri, kontrol ortamı ve izleme.
  https://www.bis.org/bcbs/publ/d515.htm
- Basel Committee, Framework for Internal Control Systems in Banking
  Organisations: sorumluluk, yetki, raporlama ve görevler ayrılığı.
  https://www.bis.org/publ/bcbs40.pdf
- NIST Cybersecurity Framework 2.0: Govern, Identify, Protect, Detect, Respond ve
  Recover; anomali, erişim, veri güvenliği ve sürekli izleme.
  https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20
- EBA Guidelines on Loan Origination and Monitoring: kredi tahsisi, borçlu
  kredibilitesi, yönetişim ve yaşam döngüsü izleme.
  https://eba.europa.eu/activities/single-rulebook/regulatory-activities/credit-risk/guidelines-loan-origination-and-monitoring
- The IIA, Internal Audit and Fraud: hile risk değerlendirmesi, kırmızı bayrakların
  izlenmesi ve proaktif veri analitiği.
  https://internalauditor.theiia.org/globalassets/site/content/guidance/recommended/supplemental/practice-guides/practice-guide-internal-audit-and-fraud-2nd-edition/pg_internal_audit_and_fraud_2nd_edition_final.pdf

## Kullanım notu

Katalog bir karar destek başlangıç setidir; mevzuatın veya kurum politikasının
yerine geçmez. Eşikler ve puanlar, kurumun ürünleri, işlem hacmi, müşteri profili,
yanlış alarm sonuçları ve risk iştahıyla kalibre edilmelidir.
