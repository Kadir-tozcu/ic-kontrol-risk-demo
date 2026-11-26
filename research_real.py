"""Real-data pilot. No raw transactions or secrets are sent to the LLM."""
import json, os, time
import numpy as np
import pandas as pd
from sklearn.datasets import fetch_openml
from openai import OpenAI

def main():
    data=fetch_openml(data_id=1597,as_frame=True)
    x=data.data.copy(); y=pd.to_numeric(data.target).astype(int)
    x.columns=[str(c).lower() for c in x.columns]
    x=x.apply(pd.to_numeric)
    assert len(x)==284807 and int(y.sum())==492
    # Chronological split, stable sorting. Holdout labels never enter prompt.
    order=np.argsort(x["time"].to_numpy(),kind="stable")
    x=x.iloc[order].reset_index(drop=True);y=y.iloc[order].reset_index(drop=True)
    cut=len(x)//2; train=x.iloc[:cut]; tr=y.iloc[:cut]; test=x.iloc[cut:]; truth=y.iloc[cut:].to_numpy()==1
    fields=[c for c in x if c.startswith("v") or c=="amount"]
    # All models use same calibration data. Fixed univariate anomaly rule vs LLM selection of up to three predicates.
    options=[]
    for field in fields:
        for q in (.01,.05,.95,.99):
            threshold=float(train[field].quantile(q)); op="<=" if q<.5 else ">="
            p=(train[field]<=threshold if q<.5 else train[field]>=threshold).to_numpy()
            tp=int((p & (tr.to_numpy()==1)).sum()); fp=int((p & (tr.to_numpy()==0)).sum())
            options.append(dict(id=len(options),field=field,op=op,threshold=threshold,tp=tp,fp=fp))
    def rank(o):
        return 2*o["tp"]/(int(tr.sum())+o["tp"]+o["fp"])
    best=max(options,key=rank)
    model=os.getenv("OPENAI_MODEL","gpt-4.1-mini")
    start=time.perf_counter()
    response=OpenAI(timeout=60,max_retries=0).responses.create(model=model,store=False,max_output_tokens=300,input="Select 1 to 3 candidate predicate IDs to combine using OR or AND for fraud triage. Aim for good F1 based on calibration aggregates only. Return JSON with ids and logic, no explanation. Calibration positives: "+str(int(tr.sum()))+"; candidates: "+json.dumps(options))
    setup=time.perf_counter()-start
    parsed=json.loads(response.output_text.strip().removeprefix("```json").removesuffix("```").strip())
    ids=parsed["ids"]; logic=parsed["logic"]
    assert isinstance(ids,list) and 1<=len(ids)<=3 and all(type(i)==int and 0<=i<len(options) for i in ids) and len(set(ids))==len(ids) and logic in ("OR","AND")
    def mask(o):
        return (test[o["field"]]<=o["threshold"] if o["op"]=="<=" else test[o["field"]]>=o["threshold"]).to_numpy()
    rows=[]
    for seed in (42,43,44,45,46):
        for method in ("sample","fixed","llm"):
            t=time.perf_counter(); inspected=np.ones(len(test),dtype=bool)
            if method=="sample":
                inspected[:]=False; inspected[np.random.default_rng(seed).choice(len(test),len(test)//20,replace=False)]=True
                # Evaluate the predicate only on sampled records.
                pred=np.zeros(len(test),dtype=bool); subset=test.loc[inspected,best["field"]]
                pred[inspected]=(subset<=best["threshold"] if best["op"]=="<=" else subset>=best["threshold"]).to_numpy()
            elif method=="fixed":pred=mask(best)
            else:pred=(np.logical_or.reduce if logic=="OR" else np.logical_and.reduce)([mask(options[i]) for i in ids])
            seconds=time.perf_counter()-t
            tp=int((pred&truth).sum());fp=int((pred&~truth).sum());fn=int((~pred&truth).sum());tn=int((~pred&~truth).sum())
            rows.append(dict(method=method,seed=seed,n=len(test),coverage=float(inspected.mean()),tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn),scan_seconds=seconds))
    result=pd.DataFrame(rows);result.to_csv("real_results.csv",index=False)
    meta=dict(dataset="OpenML 1597 ULB creditcard",rows=len(x),calibration=cut,calibration_positive=int(tr.sum()),evaluation=len(test),evaluation_positive=int(truth.sum()),model=response.model,llm_setup_seconds=setup,fixed=best,llm=[options[i] for i in ids],logic=logic,license=data.details.get("licence"),note="Fraud triage pilot, not internal audit violations. One LLM call; repeated scans not independent model generations.")
    with open("real_protocol.json","w") as f:json.dump(meta,f,indent=2)
    print(json.dumps(meta));print(result.groupby("method")[["coverage","precision","recall","f1","scan_seconds"]].mean().to_string())

if __name__=="__main__":main()
