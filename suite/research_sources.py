"""External research datasets. No raw records are exported or sent to an LLM."""
import hashlib
import json
import time
import pandas as pd
import numpy as np
import streamlit as st

SOURCES={
 "IBM AML (sentetik)":("https://github.com/IBM/AML-Data","CDLA-Sharing-1.0"),
 "ULB Credit Card (gerçek kaynaklı)":("https://www.openml.org/search?id=1597&type=data","Kaynak kullanım şartlarını kontrol edin"),
 "Berka Financial (gerçek kaynaklı)":("https://relational.fel.cvut.cz/dataset/Financial","Yeniden dağıtım izni doğrulanmadı"),
}
IBM_URL="https://huggingface.co/datasets/OsamaMIT/IBM-AML-HI/resolve/main/HI-Small_Trans.csv"

def read_data(source, file, limit):
    if source.startswith("IBM"):
        return pd.read_csv(file if file is not None else IBM_URL,nrows=limit,usecols=["Amount Received","Amount Paid","Is Laundering"])
    if source.startswith("ULB"):
        return pd.read_csv(file,nrows=limit,usecols=["Amount","Class"])
    return pd.read_csv(file,sep=";" if file.name.lower().endswith(".asc") else ",",nrows=limit,usecols=["amount","balance","date"])

def analyze(source,d):
    if source.startswith("Berka"):
        a=pd.to_numeric(d.amount,errors="coerce"); b=pd.to_numeric(d.balance,errors="coerce")
        return {"rows":len(d),"median_amount":float(a.median()),"negative_balance":int((b<0).sum()),"date_min":str(d.date.min()),"date_max":str(d.date.max())},None
    amount="Amount Received" if source.startswith("IBM") else "Amount"
    target="Is Laundering" if source.startswith("IBM") else "Class"
    a=pd.to_numeric(d[amount],errors="raise").to_numpy(); y=pd.to_numeric(d[target],errors="raise").to_numpy()
    if len(y)<100 or not np.isin(y,[0,1]).all() or not np.isfinite(a).all():raise ValueError("Veri veya etiketler geçersiz")
    # First 20% calibration, remaining 80% held-out evaluation. Threshold is label-free.
    split=len(y)//5; threshold=float(np.quantile(a[:split],.99)); a=a[split:]; y=y[split:].astype(bool)
    rows=[]
    for seed in (42,43,44):
        for method in ("A: %5 rastgele örneklem","B: tüm kayıtlar"):
            start=time.perf_counter(); inspected=np.ones(len(y),dtype=bool)
            if method.startswith("A"):
                inspected[:]=False; inspected[np.random.default_rng(seed).choice(len(y),max(1,len(y)//20),replace=False)]=True
            pred=(a>=threshold)&inspected
            tp=int((pred&y).sum()); fp=int((pred&~y).sum()); fn=int((~pred&y).sum()); tn=int((~pred&~y).sum())
            rows.append(dict(method=method,seed=seed,n=len(y),coverage=float(inspected.mean()),TP=tp,FP=fp,FN=fn,TN=tn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,seconds=time.perf_counter()-start))
    return {"rows":len(d),"calibration_rows":split,"evaluation_rows":len(y),"positive_labels":int(y.sum()),"threshold":threshold,"rule":"amount >= calibration 99th percentile","note":"Baseline only; no AI model evaluated"},pd.DataFrame(rows)

def render_sources():
    st.subheader("Açık veri kaynakları")
    source=st.selectbox("Araştırma veri seti",list(SOURCES),key="ext_source")
    url,license_note=SOURCES[source]
    st.markdown(f"[Veri kaynağı]({url}) · {license_note}")
    st.caption("Yalnızca izinli araştırma verileri. Ham kayıtlar GitHub'a yazılmaz, LLM'e gönderilmez; sadece özet ve ölçümler indirilir.")
    limit=st.selectbox("İlk N kayıt",[10000,100000,300000,1000000],index=1,key="ext_limit")
    permission=st.checkbox("Verinin bu sunucuda işlenmesine ilişkin kullanım şartlarını kabul ediyorum",key="ext_permission_"+source)
    if not permission:return
    file=st.file_uploader("CSV / ASC dosyası (IBM için isteğe bağlı)",type=["csv","asc"],key="ext_file_"+source)
    if source.startswith("IBM"):st.caption("Dosya seçilmezse açık Hugging Face IBM HI-Small aynasından ilk N kayıt okunur. Kaynak erişimi başarısız olursa otomatik veri ikamesi yapılmaz.")
    if st.button("Veriyi analiz et",key="ext_run",disabled=file is None and not source.startswith("IBM")):
        try:
            with st.spinner("Veri okunuyor"):
                start=time.perf_counter(); d=read_data(source,file,limit); summary,rows=analyze(source,d)
                summary.update(source=source,source_url=url,download_url=IBM_URL if file is None else None,license=license_note,requested_rows=limit,elapsed_seconds=time.perf_counter()-start,data_fingerprint=hashlib.sha256(pd.util.hash_pandas_object(d,index=False).values.tobytes()).hexdigest())
                st.session_state["ext_result"]=(source,summary,rows)
        except Exception as exc:
            st.session_state.pop("ext_result",None);st.error("Veri analizi başarısız: "+type(exc).__name__)
    if "ext_result" in st.session_state and st.session_state["ext_result"][0]==source:
        _,summary,rows=st.session_state["ext_result"];st.json(summary)
        st.download_button("Veri özeti JSON",json.dumps(summary,ensure_ascii=False,indent=2),"external_summary.json","application/json",key="ext_json")
        if rows is not None:
            st.warning("Bu sonuçlar dolandırıcılık / AML etiketleriyle tutar eşiği karşılaştırmasıdır; iç denetim ihlali ya da yapay zekâ başarısı değildir.")
            st.dataframe(rows,hide_index=True)
            st.download_button("Karşılaştırma CSV",rows.to_csv(index=False),"external_baseline.csv","text/csv",key="ext_csv")
