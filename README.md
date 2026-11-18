# İç Kontrol Risk Ajansı — Herkese Açık Demo

Bu proje **gerçek müşteri verisi içermez**. 10.000 tamamen sentetik işlem üzerinden kural tabanlı risk puanlaması yapan, paylaşılabilir bir Streamlit demosudur. Mevcut kurumsal V3–V6 uygulamasının güvenli tanıtım amacıyla sadeleştirilmiş **ayrı bir sürümüdür**; ML veya LLM entegrasyonu bulunduğu iddia edilmez.

## Yerelde çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud'da yayımlama

1. GitHub'da yeni bir depo oluşturun (ör. `ic-kontrol-risk-demo`).
2. Bu klasördeki `app.py` ve `requirements.txt` dosyalarını depoya yükleyin. Gerçek banka verisi, parola, `.env`, veritabanı veya erişim anahtarı yüklemeyin.
3. https://share.streamlit.io/ adresinden GitHub hesabınızla oturum açın.
4. **Create app** → GitHub deposunu seçin → Branch `main`, main file path `app.py` → Deploy.
5. Verilen `*.streamlit.app` bağlantısını paylaşın. Herkese açık bağlantı arama motorları ve üçüncü kişiler tarafından görülebilir.

## Güvenlik kapsamı

- Uygulama gerçek veriye bağlanmaz, dosya yükletmez, kullanıcı yönetmez, kalıcı vaka kaydı tutmaz.
- CSV indirme yalnızca sentetik veriyi kapsar.
- Risk puanları örnek kural ağırlıklarından hesaplanır; gerçek suistimal tespiti veya üretim kullanımı için doğrulanmamıştır.
- Herkese açık depoya gizli anahtar veya gerçek veri yüklemeyin.
