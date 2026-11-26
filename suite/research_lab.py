"""Research Lab: reproducible synthetic benchmarks and local Berka profiling."""
import time
import json
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
from suite.adaptive_ai import api_available, model_name, rule_from_text, run_rule

SCENARIOS = {
    "Dormant account": ("inactivity_days en az 365 ve amount 10000 veya daha fazla değil; iki koşul birlikte: amount en az 10000", [("inactivity_days",">=",365),("amount",">=",10000)]),
    "Authorization limit": ("amount en az 20000 ve approval_missing değeri 1 olan kayıtları bul", [("amount",">=",20000),("approval_missing","==",1)]),
    "Unusual timing": ("out_of_hours değeri 1 ve amount en az 15000 olan kayıtları bul", [("out_of_hours","==",1),("amount",">=",15000)]),
}
SCENARIOS["Dormant account"]=("inactivity_days en az 365 ve amount en az 10000 olan kayıtları bul",SCENARIOS["Dormant account"][1])

def generate(n, seed):
    rng=np.random.default_rng(seed)
    return pd.DataFrame({"amount":rng.integers(1,40000,n),"inactivity_days":rng.integers(0,500,n),
        "approval_missing":rng.binomial(1,.025,n),"out_of_hours":rng.binomial(1,.04,n)})

def reference(data, conditions):
    mask=np.ones(len(data),dtype=bool)
    for field,op,value in conditions:
        mask &= (data[field].to_numpy()>=value if op==">=" else data[field].to_numpy()==value)
    return mask

def metrics(truth,pred,coverage):
    tp=int(np.sum(truth & pred)); fp=int(np.sum(~truth & pred))
    fn=int(np.sum(truth & ~pred)); tn=int(np.sum(~truth & ~pred))
    return dict(coverage_pct=100*coverage, TP=tp,FP=fp,FN=fn,TN=tn,
        precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
        f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
        false_positive_rate=fp/(fp+tn) if fp+tn else None)

def benchmark(n, sample_pct, repeats, use_ai):
    rows=[]; rules=[]
    schema=generate(0,0)
    for name,(prompt,conditions) in SCENARIOS.items():
        rule=None; error=None; start=time.perf_counter()
        if use_ai:
            try:
                rule=rule_from_text(prompt,schema,"Research Lab",filter_only=True)
            except Exception as exc:
                error=type(exc).__name__
        setup=time.perf_counter()-start
        rules.append({"scenario":name,"prompt":prompt,"reference":conditions,"generated":rule,"error":error,"ai_setup_seconds":setup if use_ai else None})
        for seed in range(42,42+repeats):
            data=generate(n,seed); truth=reference(data,conditions)
            rng=np.random.default_rng(seed+1000)
            k=max(1,int(n*sample_pct/100)); ix=rng.choice(n,k,replace=False)
            start=time.perf_counter(); pred=np.zeros(n,dtype=bool);pred[ix]=reference(data.iloc[ix],conditions)
            rows.append(dict(scenario=name,seed=seed,method="A: sample + oracle rule",n=n,scan_seconds=time.perf_counter()-start,**metrics(truth,pred,k/n)))
            start=time.perf_counter(); pred=reference(data,conditions)
            rows.append(dict(scenario=name,seed=seed,method="B: full scan + reference rule",n=n,scan_seconds=time.perf_counter()-start,**metrics(truth,pred,1)))
            if rule is not None:
                start=time.perf_counter()
                try:
                    pred=run_rule(data,rule).to_numpy(dtype=bool)
                    rows.append(dict(scenario=name,seed=seed,method="C: full scan + LLM rule",n=n,scan_seconds=time.perf_counter()-start,**metrics(truth,pred,1)))
                except Exception as exc:
                    rules[-1]["error"]=type(exc).__name__
    return pd.DataFrame(rows),rules

def render():
    st.subheader("Research Lab | Akademik araştırma")
    from suite.berka_verified import render_verified
    render_verified()
    st.divider()
    st.subheader("Sentetik teknik test (akademik gerçek veri bulgularından ayrı)")
    from suite.research_sources import render_sources
    with st.expander("Açık veri kaynakları", expanded=True):
        render_sources()
    st.info("Sentetik veride etiketler referans koşullardan üretilir. B modeli ideal referanstır; C modelinin görevi doğal dili doğru kurala çevirmektir. Bu deney gerçek suistimal tespiti değildir.")
    n=st.selectbox("İşlem sayısı",[10000,100000,1000000],index=1,key="lab_n")
    sample=st.slider("Örneklem oranı (%)",1,20,5,key="lab_sample")
    repeats=st.slider("Tekrar sayısı",1,5,3,key="lab_repeats")
    use_ai=st.checkbox("Gerçek LLM çağrısını etkinleştir (API maliyeti doğabilir)",disabled=not api_available(),key="lab_ai")
    if not api_available():st.warning("API anahtarı yok. C modeli çalıştırılamaz; yerel ayrıştırıcı AI olarak raporlanmaz.")
    all_scales=st.checkbox("Üç veri ölçeğini birlikte test et",value=True,key="lab_all_scales")
    if st.button("Deneyi çalıştır",type="primary",key="lab_run"):
        with st.spinner("Deneyler çalıştırılıyor"):
            frames=[]; rules=[]
            for scale in ([10000,100000,1000000] if all_scales else [n]):
                frame,protocol=benchmark(scale,sample,repeats,use_ai)
                frames.append(frame);rules.extend([dict(item,n=scale) for item in protocol])
            result=pd.concat(frames,ignore_index=True)
            st.session_state["lab_result"]=(result,rules,{"scales":[10000,100000,1000000] if all_scales else [n],"sample_pct":sample,"repeats":repeats,"model":model_name() if use_ai else None})
    if "lab_result" in st.session_state:
        result,rules,meta=st.session_state["lab_result"]
        st.json(meta)
        st.dataframe(result,hide_index=True)
        summary=result.groupby(["n","method"])[["recall","precision","f1","coverage_pct","scan_seconds"]].agg(["mean","std"])
        st.dataframe(summary)
        st.line_chart(result.groupby(["n","method"]).scan_seconds.mean().unstack())
        st.download_button("Özet istatistikler CSV",summary.to_csv().encode("utf-8-sig"),"research_summary.csv","text/csv")
        st.bar_chart(result.groupby("method")[["recall","precision","f1"]].mean())
        st.download_button("Deney sonuçları CSV",result.to_csv(index=False).encode("utf-8-sig"),"research_results.csv","text/csv")
        st.download_button("Deney protokolü ve üretilen kurallar",json.dumps({"settings":meta,"rules":rules},ensure_ascii=False,indent=2),"research_protocol.json","application/json")
        for r in rules:
            if r["error"]:st.warning(r["scenario"]+": "+r["error"])
    st.divider()
    st.subheader("Berka | Gerçek kaynaklı tarihsel veri")
    st.markdown("[CTU Financial veri kaynağı](https://relational.fel.cvut.cz/dataset/Financial)")
    st.caption("Ham veri depoya yazılmaz veya LLM'e gönderilmez. Bu bölüm yalnızca işlem tutarı, bakiye ve tarihsel kapsam özetini üretir; gerçek ihlal etiketleri yoktur.")
    allowed=st.checkbox("Bu dosyayı bu sunucuda araştırma amacıyla işleme iznim var",key="lab_berka_permission")
    if allowed:
        f=st.file_uploader("Berka trans.asc / CSV (yalnızca yetkili açık araştırma verisi)",type=["asc","csv"],key="lab_berka")
        if f is not None and st.button("Berka profilini çıkar",key="lab_berka_run"):
            try:
                start=time.perf_counter()
                d=pd.read_csv(f,sep=";" if f.name.lower().endswith(".asc") else ",",usecols=lambda c:c.strip().lower() in {"amount","balance","date"})
                d.columns=[c.strip().lower() for c in d.columns]
                if not {"amount","balance","date"}.issubset(d.columns):raise ValueError("amount, balance, date sütunları gerekli")
                a=pd.to_numeric(d.amount,errors="coerce"); b=pd.to_numeric(d.balance,errors="coerce")
                summary={"rows":len(d),"valid_amount":int(a.notna().sum()),"valid_balance":int(b.notna().sum()),"negative_balance_count":int((b<0).sum()),"amount_median":float(a.median()),"date_min":str(d.date.min()),"date_max":str(d.date.max()),"seconds":time.perf_counter()-start,"sha256":hashlib.sha256(f.getvalue()).hexdigest()}
                st.session_state["lab_berka_summary"]=summary
            except Exception as exc:st.error("Berka dosyası işlenemedi: "+type(exc).__name__)
        if "lab_berka_summary" in st.session_state:
                summary=st.session_state["lab_berka_summary"]
                st.json(summary)
                st.download_button("Berka özetini indir",json.dumps(summary,indent=2),"berka_profile.json","application/json")
