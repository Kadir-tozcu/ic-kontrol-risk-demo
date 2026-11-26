import json,time,itertools
import numpy as np
import pandas as pd
from openai import OpenAI
from sklearn.model_selection import StratifiedKFold

def validate(d, indicators, hashes):
    fields=["amount","duration","payments","prior_min_balance","prior_mean_balance","prior_count","payment_to_balance"]
    y=d.status.eq("B").to_numpy()
    rows=[]; protocols=[]
    client=OpenAI(timeout=60,max_retries=0)
    for fold,(a,b) in enumerate(StratifiedKFold(5,shuffle=True,random_state=2026).split(d,y)):
        train=d.iloc[a]; test=d.iloc[b]; yt=y[a]; truth=y[b]
        opts=[]; tm=[]; vm=[]
        for field in fields:
            for q in (.1,.25,.75,.9):
                v=float(train[field].quantile(q)); op="<=" if q<.5 else ">="
                opts.append(dict(field=field,threshold=v,op=op))
                tm.append((train[field]<=v if q<.5 else train[field]>=v).to_numpy())
                vm.append((test[field]<=v if q<.5 else test[field]>=v).to_numpy())
        def pred(m,ids,logic):
            return (np.logical_and.reduce if logic=="AND" else np.logical_or.reduce)([m[i] for i in ids])
        def score(p):
            tp=int((p&yt).sum()); fp=int((p&~yt).sum())
            return dict(tp=tp,fp=fp,f1=2*tp/(int(yt.sum())+int(p.sum())))
        candidates=[]
        for k in (1,2,3):
            for ids in itertools.combinations(range(len(opts)),k):
                if len({opts[i]["field"] for i in ids})!=k:continue
                for logic in (["AND"] if k==1 else ["AND","OR"]):
                    candidates.append(dict(ids=list(ids),logic=logic,**score(pred(tm,ids,logic))))
        best=max(candidates,key=lambda z:(z["f1"],-len(z["ids"])))
        single=max((z for z in candidates if len(z["ids"])==1),key=lambda z:z["f1"])
        catalog=[dict(id=i,**o,**score(tm[i])) for i,o in enumerate(opts)]
        schema={"type":"object","properties":{"ids":{"type":"array","items":{"type":"integer","enum":list(range(len(opts)))}},"logic":{"type":"string","enum":["AND","OR"]}},"required":["ids","logic"],"additionalProperties":False}
        feedback=[]; accepted=[]; model=None; elapsed=0
        for turn in range(3):
            start=time.perf_counter()
            try:
                resp=client.responses.create(model="gpt-4.1-mini",store=False,max_output_tokens=400,text={"format":{"type":"json_schema","name":"risk_rule","strict":True,"schema":schema}},input="Select 1-3 predicates on DISTINCT fields for loan risk triage. Maximize calibration F1. Previous attempts include exact calibration feedback; propose a different combination. No holdout data available. Positive count "+str(int(yt.sum()))+" Catalog "+json.dumps(catalog)+" Feedback "+json.dumps(feedback))
                model=resp.model; z=json.loads(resp.output_text); ids=z["ids"]; logic=z["logic"]
                if not 1<=len(ids)<=3 or len({opts[i]["field"] for i in ids})!=len(ids):raise ValueError("duplicate fields or invalid length")
                z.update(score(pred(tm,ids,logic)));feedback.append(z);accepted.append(z)
            except Exception as e:feedback.append({"error":type(e).__name__})
            elapsed+=time.perf_counter()-start
        chosen=max(accepted,key=lambda z:z["f1"]) if accepted else None
        methods={"single":single,"matched_exhaustive":best}
        if chosen:methods["validated_llm"]=chosen
        for name,z in methods.items():
            p=pred(vm,z["ids"],z["logic"]);tp=int((p&truth).sum());fp=int((p&~truth).sum());fn=int((~p&truth).sum());tn=int((~p&~truth).sum())
            rows.append(dict(fold=fold,method=name,n=len(b),tp=tp,fp=fp,fn=fn,tn=tn,coverage=1.0))
        rng=np.random.default_rng(42+fold);ix=rng.choice(len(b),max(1,int(len(b)*.05)),replace=False);p=np.zeros(len(b),bool);p[ix]=pred(vm,single["ids"],single["logic"])[ix]
        rows.append(dict(fold=fold,method="sample",n=len(b),tp=int((p&truth).sum()),fp=int((p&~truth).sum()),fn=int((~p&truth).sum()),tn=int((~p&~truth).sum()),coverage=len(ix)/len(b)))
        protocols.append(dict(fold=fold,model=model,llm_seconds=elapsed,feedback=feedback,chosen=chosen,matched=best,train_n=len(a),test_n=len(b)))
    result=pd.DataFrame(rows);result.to_csv("berka_validation.csv",index=False)
    totals=result.groupby("method")[["n","tp","fp","fn","tn"]].sum()
    totals["precision"]=totals.tp/(totals.tp+totals.fp);totals["recall"]=totals.tp/(totals.tp+totals.fn);totals["f1"]=2*totals.tp/(2*totals.tp+totals.fp+totals.fn)
    totals["folds"]=result.groupby("method").size()
    totals.to_csv("berka_validation_summary.csv")
    with open("berka_validation_protocol.json","w") as f:json.dump(dict(note="Exploratory five-fold internal validation; dataset previously inspected; not external validation. Loan repayment proxy, not audit violation. Matched search uses same rule family.",indicators=indicators,hashes=hashes,folds=protocols),f,indent=2)
    print("VALIDATION_SUMMARY",totals.to_json(),flush=True)
