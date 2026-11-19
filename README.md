# İç Kontrol Risk Ajansı

Streamlit üzerinde çalışan 14 süreçli sentetik iç kontrol demosu. Ana ekranlar ve senaryo kataloğu, masaüstündeki BASLAT.bat ile açılan uygulamadan aktarılmıştır. Başlatmak için Python 3.12 ile `pip install -r requirements.txt` ve `streamlit run app.py` komutlarını çalıştırın.

Her ziyaretçi ayrı, geçici bir demo çalışma alanında yönetici olarak başlar. Gerçek müşteri verileri yerine sentetik veya örnek veri kullanın. Önceki yedi ekranlı sürüm ve ona ait yedekler `?view=classic` adresinde açılır. Ana sürümün veritabanı yedeği parola, API anahtarı ve MFA doğrulama kayıtlarını dışarıda bırakır.

Adaptif kontrolün yerel modu anahtarsız çalışır. Harici model için sunucu tarafında ayrıca yapılandırma gerekir. Entegrasyon ve API yönetimi ekranları örnek tanımları yönetir. BASLAT_API.bat tarafından ayrı başlatılan HTTP servisi bu Streamlit dağıtımına dahil değildir.
