"""Immutable aggregate results verified from GitHub Actions run 45791607378."""
import pandas as pd
import streamlit as st
import json

DATA=json.loads("{\"source\":\"https://github.com/Kadir-tozcu/ic-kontrol-risk-demo/actions/runs/45791607378\",\"artifact\":\"https://github.com/Kadir-tozcu/ic-kontrol-risk-demo/actions/runs/45791607378/artifacts/15103695057\",\"transactions\":1056320,\"loans\":682,\"eligible\":234,\"positive\":31,\"indicators\":{\"negative_balance\":2999,\"gap_90_days\":30,\"top_1_percent\":10564},\"methods\":[{\"method\":\"Örnekleme\",\"tp\":0,\"fp\":0,\"fn\":31,\"tn\":203},{\"method\":\"Tek kural\",\"tp\":12,\"fp\":22,\"fn\":19,\"tn\":181},{\"method\":\"Algoritmik\",\"tp\":18,\"fp\":34,\"fn\":13,\"tn\":169},{\"method\":\"Geri bildirimli YZ\",\"tp\":8,\"fp\":5,\"fn\":23,\"tn\":198}]}")
def results():
    d=pd.DataFrame(DATA["methods"])
    d["precision"]=d.tp/(d.tp+d.fp)
    d["recall"]=d.tp/(d.tp+d.fn)
    d["f1"]=2*d.tp/(2*d.tp+d.fp+d.fn)
    return d

def render_verified():
    st.subheader("Berka | Doğrulanmış gerçek veri deneyi")
    st.caption("26.11.2026 — GitHub Actions 45791607378; kaydedilmiş sonuçlar, canlı tarama değildir.")
    cols=st.columns(4)
    for col,(label,key) in zip(cols,[("İşlem","transactions"),("Kredi","loans"),("Uygun kredi","eligible"),("Sorunlu kredi","positive")]):
        col.metric(label,format(DATA[key],",").replace(",","."))
    d=results()
    st.dataframe(d,hide_index=True)
    st.bar_chart(d.set_index("method")[["precision","recall","f1"]])
    st.json(DATA["indicators"])
    st.warning("Keşifsel iç doğrulama; kredi geri ödeme durumu iç denetim ihlali değildir. İşlem göstergeleri etiketsizdir. Dağıtık işlem ve bağımsız dış doğrulama yapılmamıştır.")
    st.markdown("[Deney kaydı]("+DATA["source"]+") · [Sonuç arşivi]("+DATA["artifact"]+")")
    st.download_button("Doğrulanmış karşılaştırma CSV",d.to_csv(index=False).encode("utf-8-sig"),"berka_verified.csv","text/csv")
    render_external()

EXTERNAL=json.loads("{\"source\":\"https://github.com/Kadir-tozcu/ic-kontrol-risk-demo/actions/runs/45792740530\",\"artifact\":\"https://github.com/Kadir-tozcu/ic-kontrol-risk-demo/actions/runs/45792740530/artifacts/15103860840\",\"methods\":[{\"method\":\"Örnekleme\",\"tp\":11,\"fp\":15,\"fn\":289,\"tn\":685},{\"method\":\"Tek kural\",\"tp\":191,\"fp\":359,\"fn\":109,\"tn\":341},{\"method\":\"Algoritmik\",\"tp\":203,\"fp\":257,\"fn\":97,\"tn\":443},{\"method\":\"Geri bildirimli YZ\",\"tp\":110,\"fp\":148,\"fn\":190,\"tn\":552}]}")
def render_external():
    st.subheader("South German Credit | Bağımsız yöntem tekrarı")
    st.caption("1000 tarihsel kredi, 300 olumsuz geri ödeme etiketi; beş katlı yerel kalibrasyon. Sabit Berka modelinin transfer testi değildir.")
    d=pd.DataFrame(EXTERNAL["methods"])
    d["precision"]=d.tp/(d.tp+d.fp)
    d["recall"]=d.tp/(d.tp+d.fn)
    d["f1"]=2*d.tp/(2*d.tp+d.fp+d.fn)
    st.dataframe(d,hide_index=True)
    st.bar_chart(d.set_index("method")[["precision","recall","f1"]])
    st.markdown("[Deney kaydı]("+EXTERNAL["source"]+") · [Sonuç arşivi]("+EXTERNAL["artifact"]+")")
    st.download_button("Bağımsız deney CSV",d.to_csv(index=False).encode("utf-8-sig"),"german_verified.csv","text/csv")
