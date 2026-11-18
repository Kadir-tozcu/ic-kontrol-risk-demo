# İç Kontrol Risk Ajansı

10.000 sentetik bankacılık işlemi için kural tabanlı Streamlit demosu. Önceki kurumsal arayüz esas alınarak risk motoru, veri üretimi, vaka deposu ve yönetim katmanı yeniden yazıldı.

Risk panosu, işlem listesi, vaka detayı, yönetici raporu, vaka asistanı, kural yönetimi ve sistem yönetimi aynı veri kümesini kullanır. Risk sonuçları örnek niteliğindedir. Yerel asistan şablon tabanlıdır.

Her ziyaretçi kendi geçici SQLite çalışma alanında demo yöneticisi olarak başlar. Bu alanda inceleyen ve görüntüleyen hesapları oluşturulabilir. Görüntüleyen rolü maskelenmiş müşteri kimlikleriyle çalışır. Parola doğrulamasında her kullanıcı için ayrı salt ve PBKDF2 kullanılır. Oturum sona erdiğinde kayıtlar kaybolur. Dışa aktarılan yedek parola doğrulama bilgilerini içermez.

CSV ve Excel içe aktarma, örnek veri kümesindeki transaction_id değerlerinden bir alt küme seçer. Gerçek müşteri, banka veya dış model bağlantısı kullanılmaz. Demo notlarına yalnızca örnek içerik girilmelidir.

Yerelde başlatmak için Python 3.12 ile `pip install -r requirements.txt` ve `streamlit run app.py` komutlarını çalıştırın.

## Sonraki oturumda devam etme

Sistem yönetimi sekmesinde demo veritabanı yedeğini indir. Yeni bir oturumda **Yedekten devam et** altında bu dosyayı seç, çalışma alanının değişmesini onayla ve **Yedeği geri yükle** düğmesine bas. Kurallar, vaka durumları ve notları, kullanıcı adları ve roller ile kayıtlı denetim izi geri gelir. Yedekten gelen kullanıcılar için yönetici yeni bir demo parolası belirleyebilir. Geçersiz bir yedek mevcut çalışma alanını değiştirmez.
