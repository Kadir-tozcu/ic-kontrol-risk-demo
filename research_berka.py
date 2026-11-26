"""Berka public research database: transaction controls and loan-risk pilot.
Only aggregate outputs are retained. No raw rows or IDs are sent to an LLM.
"""
import os, json, time
import numpy as np
import pandas as pd
import pymysql
from openai import OpenAI

def main():
    started=time.perf_counter()
    db=pymysql.connect(host="relational.fel.cvut.cz",port=3306,user="guest",password="relational",database="financial",connect_timeout=25,read_timeout=180)
    counts={}
    with db:
        with db.cursor() as cur:
            for table in ("account","client","disp","card","loan","order","trans","district"):
                cur.execute("SELECT COUNT(*) FROM `"+table+"`")
                counts[table]=int(cur.fetchone()[0])
        trans=pd.read_sql("SELECT account_id, date, trans_id, amount, balance, type FROM trans",db)
        loan=pd.read_sql("SELECT account_id,date,amount,duration,payments,status FROM loan",db)
    print("BERKA_COUNTS",json.dumps(counts),flush=True)
    def dates(series):
        s=series.astype(str)
        if s.str.fullmatch(r"\d{6}").all():return pd.to_datetime(s,format="%y%m%d")
        return pd.to_datetime(series)
    trans["date"]=dates(trans.date);loan["date"]=dates(loan.date)
    for col in ("amount","balance"):trans[col]=pd.to_numeric(trans[col])
    trans=trans.sort_values(["account_id","date","trans_id"])
    trans["gap_days"]=trans.groupby("account_id").date.diff().dt.days
    t=time.perf_counter()
    indicators={"negative_balance":int((trans.balance<0).sum()),"gap_at_least_90_days":int((trans.gap_days>=90).sum()),"large_amount_top_1pct":int((trans.amount>=trans.amount.quantile(.99)).sum()),"transaction_rows":len(trans),"transaction_coverage":1.0}
    indicators["scan_seconds"]=time.perf_counter()-t
    print("BERKA_INDICATORS",json.dumps(indicators),flush=True)
    # Loan covariates only from transactions strictly before origination, no post-loan information.
    records=[]
    groups={k:g for k,g in trans.groupby("account_id",sort=False)}
    for l in loan.itertuples():
        g=groups.get(l.account_id)
        if g is None:continue
        prior=g[(g.date<l.date)&(g.date>=l.date-pd.Timedelta(days=90))]
        if prior.empty:continue
        records.append(dict(date=l.date, status=str(l.status),amount=float(l.amount),duration=float(l.duration),payments=float(l.payments),prior_min_balance=float(prior.balance.min()),prior_mean_balance=float(prior.balance.mean()),prior_count=len(prior),payment_to_balance=float(l.payments)/max(1.,float(prior.balance.mean()))))
    d=pd.DataFrame(records)
    # A/B are completed loans; C/D are ongoing, excluded from final repayment endpoint.
    d=d[d.status.isin(["A","B"])].sort_values("date").reset_index(drop=True)
    y=d.status.eq("B").to_numpy(); cut=len(d)//2
    train=d.iloc[:cut];test=d.iloc[cut:];yt=y[:cut];truth=y[cut:]
    if min(int(yt.sum()),int(truth.sum()))==0:raise ValueError("No positive loans in one split")
    fields=["amount","duration","payments","prior_min_balance","prior_mean_balance","prior_count","payment_to_balance"]
    options=[]
    for field in fields:
        for q in (.1,.25,.75,.9):
            value=float(train[field].quantile(q));op="<=" if q<.5 else ">="
            p=(train[field]<=value if q<.5 else train[field]>=value).to_numpy()
            options.append(dict(id=len(options),field=field,op=op,threshold=value,tp=int((p&yt).sum()),fp=int((p&~yt).sum())))
    best=max(options,key=lambda o:2*o["tp"]/(int(yt.sum())+o["tp"]+o["fp"]))
    def mask(o):
        return (test[o["field"]]<=o["threshold"] if o["op"]=="<=" else test[o["field"]]>=o["threshold"]).to_numpy()
    rules=None; error=None; setup=None; model=None
    try:
        start=time.perf_counter()
        resp=OpenAI(timeout=60,max_retries=0).responses.create(model="gpt-4.1-mini",store=False,max_output_tokens=300,input="Choose 1-3 predicate IDs and AND or OR for loan repayment risk triage, maximizing expected F1. Use only calibration aggregates. Output JSON object with ids and logic. Positive count "+str(int(yt.sum()))+" candidates "+json.dumps(options))
        setup=time.perf_counter()-start;model=resp.model
        p=json.loads(resp.output_text.strip().removeprefix("```json").removesuffix("```").strip())
        ids=p["ids"];logic=p["logic"]
        assert isinstance(ids,list) and 1<=len(ids)<=3 and len(set(ids))==len(ids) and all(type(i)==int and 0<=i<len(options) for i in ids) and logic in ("AND","OR")
        rules={"ids":ids,"logic":logic}
    except Exception as e:error=type(e).__name__
    rows=[]
    for seed in range(42,47):
        for method in (["sample","fixed","llm"] if rules else ["sample","fixed"]):
            t=time.perf_counter();inspected=np.ones(len(test),dtype=bool)
            if method=="sample":
                inspected[:]=False;inspected[np.random.default_rng(seed).choice(len(test),max(1,len(test)//20),replace=False)]=True
                pred=np.zeros(len(test),dtype=bool);s=test.loc[inspected,best["field"]]
                pred[inspected]=(s<=best["threshold"] if best["op"]=="<=" else s>=best["threshold"]).to_numpy()
            elif method=="fixed":pred=mask(best)
            else:pred=(np.logical_and.reduce if rules["logic"]=="AND" else np.logical_or.reduce)([mask(options[i]) for i in rules["ids"]])
            elapsed=time.perf_counter()-t
            tp=int((pred&truth).sum());fp=int((pred&~truth).sum());fn=int((~pred&truth).sum());tn=int((~pred&~truth).sum())
            rows.append(dict(method=method,seed=seed,n=len(test),coverage=float(inspected.mean()),tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn),scan_seconds=elapsed))
    result=pd.DataFrame(rows);result.to_csv("berka_loan_results.csv",index=False)
    meta=dict(source="https://relational.fel.cvut.cz/dataset/Financial",counts=counts,indicators=indicators,loan_eligible=len(d),train_n=cut,test_n=len(test),train_positive=int(yt.sum()),test_positive=int(truth.sum()),model=model,llm_error=error,llm_setup_seconds=setup,fixed=best,llm_rules=rules,selected_predicates=[options[i] for i in rules["ids"]] if rules else [],elapsed_seconds=time.perf_counter()-started,note="Completed loan repayment status B is risk proxy, not confirmed audit violation. Transaction indicators unlabelled. No raw data exported.")
    with open("berka_protocol.json","w") as f:json.dump(meta,f,indent=2)
    print("BERKA_PROTOCOL",json.dumps(meta),flush=True)
    print(result.groupby("method")[["coverage","precision","recall","f1","scan_seconds"]].mean().to_string(),flush=True)

if __name__=="__main__":main()
